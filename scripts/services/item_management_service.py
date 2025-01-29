import traceback
from fastapi import APIRouter, Depends, HTTPException
import os
import shutil
from datetime import datetime, timezone

from app_constants.url import Routes, ItemsAPI
from scripts.models.user_management import User
from scripts.handlers.user_management_handler import get_current_user
from app_constants.log_module import logger
from app_constants.connectors import postgres_util, SessionLocal
from scripts.models.folder_management import Folder
from app_constants.app_configurations import STORAGE_PATH
from scripts.models.file_management import FileMetadata
from scripts.models.common_models import DeleteRequest, ItemType, MoveRequest, RenameRequest, CopyRequest


router = APIRouter(prefix=Routes.items)

@router.delete(ItemsAPI.delete)
async def delete_item(
        delete_request: DeleteRequest,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        logger.info(f"Deleting item....")
        if delete_request.item_type == ItemType.FILE:
            file = db.query(FileMetadata).filter(
                FileMetadata.id == delete_request.item_id,
                FileMetadata.owner_id == current_user.id
            ).first()

            if not file:
                raise HTTPException(status_code=404, detail="File not found")

            # Delete physical file
            if os.path.exists(file.filepath):
                logger.info(f"Deleting file: {file.filename}")
                os.remove(file.filepath)

            db.delete(file)

        else:  # FOLDER
            folder = db.query(Folder).filter(
                Folder.id == delete_request.item_id,
                Folder.owner_id == current_user.id
            ).first()

            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")

            # Get full folder path from parent relationship
            folder_path = os.path.join(STORAGE_PATH, str(current_user.id), folder.name)

            # Delete physical folder and contents
            if os.path.exists(folder_path):
                logger.info(f"Deleting folder: {folder_path}")
                shutil.rmtree(folder_path)

            # Delete all files in the folder and subfolders
            def delete_folder_contents(folder_id):
                # Delete files in current folder
                db.query(FileMetadata).filter(FileMetadata.folder_id == folder_id).delete()

                # Get subfolders and recursively delete their contents
                subfolders = db.query(Folder).filter(Folder.parent_id == folder_id).all()
                for subfolder in subfolders:
                    delete_folder_contents(subfolder.id)
                    db.delete(subfolder)

            delete_folder_contents(folder.id)
            db.delete(folder)

        db.commit()
        return {"message": f"{delete_request.item_type} deleted successfully"}

    except Exception as e:
        db.rollback()
        logger.debug(f"Failed to delete the item: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error deleting {delete_request.item_type}: {str(e)}")


@router.put(ItemsAPI.move)
async def move_item(
    move_request: MoveRequest,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        logger.info(f"Moving item...!")
        # Determine destination folder
        dest_folder = None
        if move_request.destination_folder_id is not None:
            dest_folder = db.query(Folder).filter(
                Folder.id == move_request.destination_folder_id,
                Folder.owner_id == current_user.id
            ).first()
            if not dest_folder:
                logger.info(f"Destination folder not found")
                raise HTTPException(status_code=404, detail="Destination folder not found")

        if move_request.item_type == ItemType.FILE:
            file = db.query(FileMetadata).filter(
                FileMetadata.id == move_request.item_id,
                FileMetadata.owner_id == current_user.id
            ).first()

            if not file:
                logger.info(f"File not found...!")
                raise HTTPException(status_code=404, detail="File not found")

            # Get new file path
            if dest_folder:
                new_file_path = os.path.join(STORAGE_PATH, str(current_user.id), dest_folder.name, file.filename)
            else:
                new_file_path = os.path.join(STORAGE_PATH, str(current_user.id), file.filename)

            # Move physical file
            os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
            logger.info(f"Moving file from {file.filepath} to {new_file_path}")
            shutil.move(file.filepath, new_file_path)

            # Update database
            file.filepath = new_file_path
            file.folder_id = move_request.destination_folder_id  # None for root

        else:  # FOLDER
            folder = db.query(Folder).filter(
                Folder.id == move_request.item_id,
                Folder.owner_id == current_user.id
            ).first()

            if not folder:
                logger.info(f"Folder not found..")
                raise HTTPException(status_code=404, detail="Folder not found")

            # Prevent moving folder into itself or its subdirectories
            if move_request.destination_folder_id is not None:
                current_parent = dest_folder
                while current_parent:
                    if current_parent.id == move_request.item_id:
                        logger.info("Cannot move a folder into itself or its subdirectories")
                        raise HTTPException(
                            status_code=400,
                            detail="Cannot move a folder into itself or its subdirectories"
                        )
                    current_parent = db.query(Folder).filter_by(id=current_parent.parent_id).first()

            # Move physical folder
            old_path = os.path.join(STORAGE_PATH, str(current_user.id), folder.name)
            if dest_folder:
                new_path = os.path.join(STORAGE_PATH, str(current_user.id), dest_folder.name, folder.name)
            else:
                new_path = os.path.join(STORAGE_PATH, str(current_user.id), folder.name)

            if os.path.exists(old_path):
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                logger.info(f"Moving folder from {old_path} to {new_path}")
                shutil.move(old_path, new_path)

            # Update database
            folder.parent_id = move_request.destination_folder_id  # None for root

        db.commit()
        return {"message": f"{move_request.item_type} moved successfully"}

    except Exception as e:
        db.rollback()
        logger.debug(f"Failed to move the item: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error moving {move_request.item_type}: {str(e)}")


@router.put(ItemsAPI.copy)
async def copy_item(
    copy_request: CopyRequest,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        logger.info(f"copying item...!")
        # Determine destination folder
        dest_folder = None
        if copy_request.destination_folder_id is not None:
            dest_folder = db.query(Folder).filter(
                Folder.id == copy_request.destination_folder_id,
                Folder.owner_id == current_user.id
            ).first()
            if not dest_folder:
                logger.info(f"Destination folder not found")
                raise HTTPException(status_code=404, detail="Destination folder not found")

        if copy_request.item_type == ItemType.FILE:
            file = db.query(FileMetadata).filter(
                FileMetadata.id == copy_request.item_id,
                FileMetadata.owner_id == current_user.id
            ).first()

            if not file:
                logger.info(f"File not found...!")
                raise HTTPException(status_code=404, detail="File not found")

            # Check if a file with the same name exists in the destination folder
            existing_file = db.query(FileMetadata).filter(
                FileMetadata.folder_id == copy_request.destination_folder_id,
                FileMetadata.filename == file.filename
            ).first()

            if existing_file:
                # Generate a unique name for the copy
                base_name, extension = os.path.splitext(file.filename)
                counter = 1
                new_filename = f"{base_name}_copy{extension}"

                while db.query(FileMetadata).filter(
                    FileMetadata.folder_id == copy_request.destination_folder_id,
                    FileMetadata.filename == new_filename
                ).first():
                    new_filename = f"{base_name}_copy_{counter}{extension}"
                    counter += 1
            else:
                new_filename = file.filename

            # Copy physical file
            if dest_folder:
                new_file_path = os.path.join(STORAGE_PATH, str(current_user.id), dest_folder.name, new_filename)
            else:
                new_file_path = os.path.join(STORAGE_PATH, str(current_user.id), new_filename)

            os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
            logger.info(f"Copying file from {file.filepath} to {new_file_path}")
            shutil.copy2(file.filepath, new_file_path)

            # Create new file metadata
            new_file = FileMetadata(
                filename=new_filename,
                filepath=new_file_path,
                mimetype=file.mimetype,
                size=os.path.getsize(new_file_path),
                is_public=False,  # Reset public status for the copy
                folder_id=copy_request.destination_folder_id,  # None for root
                owner_id=current_user.id,
                uploaded_at=datetime.now(timezone.utc)
            )
            db.add(new_file)

        else:  # FOLDER
            source_folder = db.query(Folder).filter(
                Folder.id == copy_request.item_id,
                Folder.owner_id == current_user.id
            ).first()

            if not source_folder:
                raise HTTPException(status_code=404, detail="Folder not found")

            def copy_folder_recursive(src_folder, dest_parent_id):
                try:
                    # Check if a folder with the same name exists in the destination
                    existing_folder = db.query(Folder).filter(
                        Folder.parent_id == dest_parent_id,
                        Folder.name == src_folder.name
                    ).first()

                    if existing_folder:
                        # Generate a unique name for the copy
                        new_name = f"{src_folder.name}_copy"
                        ctr = 1
                        while db.query(Folder).filter(
                            Folder.parent_id == dest_parent_id,
                            Folder.name == new_name
                        ).first():
                            new_name = f"{src_folder.name}_copy_{ctr}"
                            ctr += 1
                    else:
                        new_name = src_folder.name

                    # Create new folder in the database
                    new_folder = Folder(
                        name=new_name,
                        parent_id=dest_parent_id,
                        owner_id=current_user.id,
                        created_at=datetime.now(timezone.utc)
                    )
                    db.add(new_folder)
                    db.flush()

                    # Create physical folder
                    if dest_parent_id is not None:
                        dest_folder = db.query(Folder).filter(Folder.id == dest_parent_id).first()
                        new_folder_path = os.path.join(STORAGE_PATH, str(current_user.id), dest_folder.name, new_name)
                    else:
                        new_folder_path = os.path.join(STORAGE_PATH, str(current_user.id), new_name)

                    os.makedirs(new_folder_path, exist_ok=True)

                    # Copy files
                    files = db.query(FileMetadata).filter(
                        FileMetadata.folder_id == src_folder.id
                    ).all()

                    for file in files:
                        new_file_path = os.path.join(new_folder_path, file.filename)
                        logger.info(f"Copying file from {file.filepath} to {new_file_path}")
                        shutil.copy2(file.filepath, new_file_path)

                        new_file = FileMetadata(
                            filename=file.filename,
                            filepath=new_file_path,
                            mimetype=file.mimetype,
                            size=file.size,
                            is_public=False,  # Reset public status for the copy
                            folder_id=new_folder.id,
                            owner_id=current_user.id,
                            uploaded_at=datetime.now(timezone.utc)
                        )
                        db.add(new_file)

                    # Recursively copy subfolders
                    subfolders = db.query(Folder).filter(
                        Folder.parent_id == src_folder.id
                    ).all()

                    for subfolder in subfolders:
                        copy_folder_recursive(subfolder, new_folder.id)

                    return new_folder
                except Exception as e:
                    logger.debug(f"Failed to copy the folder: {e}")
                    traceback.print_exc()

            copy_folder_recursive(source_folder, copy_request.destination_folder_id)

        db.commit()
        return {"message": f"{copy_request.item_type} copied successfully"}

    except Exception as e:
        db.rollback()
        logger.debug(f"Failed to copy item: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error copying {copy_request.item_type}: {str(e)}")


@router.put(ItemsAPI.rename)
async def rename_item(
        rename_request: RenameRequest,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        logger.info(f"Renaming item...!")
        if rename_request.item_type == ItemType.FILE:
            file = db.query(FileMetadata).filter(
                FileMetadata.id == rename_request.item_id,
                FileMetadata.owner_id == current_user.id
            ).first()

            if not file:
                logger.info(f"Renaming file not found in db (file id): {rename_request.item_id}")
                raise HTTPException(status_code=404, detail="File not found")

            # Check for name conflicts
            if db.query(FileMetadata).filter(
                    FileMetadata.folder_id == file.folder_id,
                    FileMetadata.filename == rename_request.new_name,
                    FileMetadata.id != file.id
            ).first():
                logger.info("A file with this name already exists")
                raise HTTPException(status_code=400, detail="A file with this name already exists")

            # Rename physical file
            new_filepath = os.path.join(os.path.dirname(file.filepath), rename_request.new_name)
            os.rename(file.filepath, new_filepath)

            # Update database
            file.filename = rename_request.new_name
            file.filepath = new_filepath

        else:  # FOLDER
            folder = db.query(Folder).filter(
                Folder.id == rename_request.item_id,
                Folder.owner_id == current_user.id
            ).first()

            if not folder:
                logger.info(f"Renaming folder not found in db (folder id): {rename_request.item_id}")
                raise HTTPException(status_code=404, detail="Folder not found")

            # Check for name conflicts
            if db.query(Folder).filter(
                    Folder.parent_id == folder.parent_id,
                    Folder.name == rename_request.new_name,
                    Folder.id != folder.id
            ).first():
                logger.info("A folder with this name already exists")
                raise HTTPException(status_code=400, detail="A folder with this name already exists")

            # Rename physical folder
            old_path = os.path.join(STORAGE_PATH, str(current_user.id), folder.name)
            new_path = os.path.join(STORAGE_PATH, str(current_user.id), rename_request.new_name)

            if os.path.exists(old_path):
                logger.info(f"Renaming folder from {folder.name} to {rename_request.new_name}")
                os.rename(old_path, new_path)

            # Update database
            folder.name = rename_request.new_name

            # Update all file paths in this folder and subfolders
            def update_file_paths(folder_id, old_path_part, new_path_part):
                files = db.query(FileMetadata).filter(
                    FileMetadata.folder_id == folder_id
                ).all()

                for file in files:
                    file.filepath = file.filepath.replace(old_path_part, new_path_part)

                subfolders = db.query(Folder).filter(
                    Folder.parent_id == folder_id
                ).all()

                for subfolder in subfolders:
                    update_file_paths(subfolder.id, old_path_part, new_path_part)

            update_file_paths(folder.id, old_path, new_path)

        db.commit()
        logger.info(f"{rename_request.item_type} renamed successfully")
        return {"message": f"{rename_request.item_type} renamed successfully"}

    except Exception as e:
        db.rollback()
        logger.debug(f"Failed to rename the item: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error renaming {rename_request.item_type}: {str(e)}")
