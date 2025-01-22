import json
import traceback
import uvicorn
from fastapi import FastAPI, UploadFile, Depends, HTTPException, BackgroundTasks, File, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
import os
from datetime import datetime, timedelta, timezone
import jwt
import shutil
from typing import Optional
import mimetypes

from app_constants.app_configurations import STORAGE_PATH, SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, pwd_context
from scripts.models.user_management import User, Token, UserCreate
from scripts.models.folder_management import (Folder, FolderCreate, DirectoryListing, FolderInfo, ListDirectory,
                                              UploadFileModel)
from scripts.models.file_management import FileMetadata, FileShare, FileInfo
from scripts.models.common_models import DeleteRequest, ItemType, MoveRequest, RenameRequest, CopyRequest
from app_constants.connectors import postgres_util, SessionLocal
from scripts.utils.common_utils import create_jwt_token, sync_directory_with_db
from scripts.handlers.user_management_handler import get_current_user


app = FastAPI()
app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PUT"],
        allow_headers=["*"],
    )


@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: SessionLocal = Depends(postgres_util.get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_jwt_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/create_user/", response_model=Token)
async def create_user(user: UserCreate, db: SessionLocal = Depends(postgres_util.get_db)):
    try:
        db_user = User(
            username=user.username,
            email=user.email,
            hashed_password=pwd_context.hash(user.password),
            is_admin=user.is_admin,
            privilege=user.privilege
        )
        print(db_user)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        access_token = create_jwt_token(data={"sub": user.username})
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        traceback.print_exc()
        print(f"Failed to create user: {e}")


@app.post("/upload_file")
async def upload_file(file: UploadFile = File(...),
                      upload_file_model: str = Form(...),
                      current_user: User = Depends(get_current_user),
                      db = Depends(postgres_util.get_db)):
    try:
        item = UploadFileModel(**json.loads(upload_file_model)) if upload_file_model else None
        folder_id = item.folder_id

        # Retrieve folder details from the database
        folder = db.query(Folder).filter_by(id=folder_id, owner_id=current_user.id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found.")

        # Construct the folder path
        folder_path_parts = []
        current_folder = folder
        while current_folder:
            folder_path_parts.append(current_folder.name)
            current_folder = db.query(Folder).filter_by(id=current_folder.parent_id).first()

        folder_path_parts.reverse()
        folder_path = os.path.join(STORAGE_PATH, str(current_user.id), *folder_path_parts)
        os.makedirs(folder_path, exist_ok=True)

        # Check for duplicate file name in the folder
        existing_file = db.query(FileMetadata).filter(
            FileMetadata.folder_id == folder_id,
            FileMetadata.filename == file.filename,
            FileMetadata.owner_id == current_user.id,
        ).first()

        # Rename file if it already exists
        original_filename = file.filename
        if existing_file:
            base_name, extension = os.path.splitext(original_filename)
            counter = 1
            while True:
                new_filename = f"{base_name}_{counter}{extension}"
                if not db.query(FileMetadata).filter(
                        FileMetadata.folder_id == folder_id,
                        FileMetadata.filename == new_filename,
                        FileMetadata.owner_id == current_user.id,
                ).first():
                    file.filename = new_filename
                    break
                counter += 1

        # Save the file in the appropriate folder
        file_path = os.path.join(folder_path, file.filename)
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except IOError as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save file: {str(e)}"
            )
        finally:
            await file.close()

        # Create file metadata
        mime_type = mimetypes.guess_type(file.filename)[0]
        file_size = os.path.getsize(file_path)

        db_file = FileMetadata(
            filename=file.filename,
            filepath=file_path,
            mimetype=mime_type,
            size=file_size,
            folder_id=folder_id,
            owner_id=current_user.id,
        )
        db.add(db_file)
        db.commit()
        db.refresh(db_file)

        return db_file

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing request: {e}")


@app.post("/files/{file_id}/share")
async def share_file(
        file_id: int,
        share_data: FileShare,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    file = db.query(FileMetadata).filter(
        FileMetadata.id == file_id,
        FileMetadata.owner_id == current_user.id
    ).first()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    expiry = datetime.now(timezone.utc) + timedelta(hours=share_data.expires_in_hours)
    share_token = create_jwt_token({"file_id": file_id}, timedelta(hours=share_data.expires_in_hours))

    file.share_token = share_token
    file.share_expiry = expiry
    file.is_public = True

    db.commit()
    return {"share_token": share_token, "expires_at": expiry}


@app.get("/shared/{share_token}")
async def get_shared_file(share_token: str, db: SessionLocal = Depends(postgres_util.get_db)):
    try:
        payload = jwt.decode(share_token, SECRET_KEY, algorithms=["HS256"])
        file_id = payload.get("file_id")
        file = db.query(FileMetadata).filter(
            FileMetadata.id == file_id,
            FileMetadata.is_public == True,
            FileMetadata.share_expiry > datetime.now(timezone.utc)
        ).first()

        if not file:
            raise HTTPException(status_code=404, detail="File not found or share expired")

        return file
    except jwt.DecodeError:
        raise HTTPException(status_code=400, detail="Invalid share token")


@app.post(path="/list_directory", response_model=DirectoryListing)
async def list_directory(
        background_tasks: BackgroundTasks,
        folder_details: ListDirectory,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    folder_id = folder_details.folder_id
    background_tasks.add_task(sync_directory_with_db, current_user.id, db)

    # Rest of your existing list_directory code remains the same
    current_folder = None
    if folder_id:
        current_folder = db.query(Folder).filter(
            Folder.id == folder_id,
            Folder.owner_id == current_user.id
        ).first()
        if not current_folder:
            raise HTTPException(status_code=404, detail="Folder not found")

    folders_query = db.query(Folder).filter(
        Folder.owner_id == current_user.id,
        Folder.parent_id == folder_id
    )

    files_query = db.query(FileMetadata).filter(
        FileMetadata.owner_id == current_user.id,
        FileMetadata.folder_id == folder_id
    )

    folder_list = []
    for folder in folders_query.all():
        folder_path = os.path.join(STORAGE_PATH, str(current_user.id), folder.name)
        folder_list.append(FolderInfo(
            name=folder.name,
            path=folder_path,
            modified_at=folder.created_at,
            owner_id=folder.owner_id,
            folder_id=folder.id
        ))

    file_list = []
    total_size = 0
    for file in files_query.all():
        file_path = os.path.join(STORAGE_PATH, str(current_user.id), file.filename)
        file_list.append(FileInfo(
            name=file.filename,
            path=file_path,
            size=file.size,
            modified_at=file.uploaded_at,
            mime_type=file.mimetype,
            is_public=file.is_public,
            owner_id=file.owner_id,
            id=file.id
        ))
        total_size += file.size

    return DirectoryListing(
        path=os.path.join(STORAGE_PATH, str(current_user.id)),
        files=file_list,
        folders=folder_list,
        parent_folder_id=current_folder.parent_id if current_folder else None,
        total_files=len(file_list),
        total_size=total_size
    )


@app.delete("/items/delete")
async def delete_item(
        delete_request: DeleteRequest,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        if delete_request.item_type == ItemType.FILE:
            file = db.query(FileMetadata).filter(
                FileMetadata.id == delete_request.item_id,
                FileMetadata.owner_id == current_user.id
            ).first()

            if not file:
                raise HTTPException(status_code=404, detail="File not found")

            # Delete physical file
            if os.path.exists(file.filepath):
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
        raise HTTPException(status_code=500, detail=f"Error deleting {delete_request.item_type}: {str(e)}")


@app.put("/items/move")
async def move_item(
        move_request: MoveRequest,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        dest_folder = db.query(Folder).filter(
            Folder.id == move_request.destination_folder_id,
            Folder.owner_id == current_user.id
        ).first()

        if not dest_folder:
            raise HTTPException(status_code=404, detail="Destination folder not found")

        if move_request.item_type == ItemType.FILE:
            file = db.query(FileMetadata).filter(
                FileMetadata.id == move_request.item_id,
                FileMetadata.owner_id == current_user.id
            ).first()

            if not file:
                raise HTTPException(status_code=404, detail="File not found")

            # Get new file path
            new_file_path = os.path.join(STORAGE_PATH, str(current_user.id), dest_folder.name, file.filename)

            # Move physical file
            os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
            shutil.move(file.filepath, new_file_path)

            # Update database
            file.filepath = new_file_path
            file.folder_id = move_request.destination_folder_id

        else:  # FOLDER
            folder = db.query(Folder).filter(
                Folder.id == move_request.item_id,
                Folder.owner_id == current_user.id
            ).first()

            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")

            # Prevent moving folder into itself or its subdirectories
            current_parent = dest_folder
            while current_parent:
                if current_parent.id == move_request.item_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot move a folder into itself or its subdirectories"
                    )
                current_parent = db.query(Folder).filter_by(id=current_parent.parent_id).first()

            # Move physical folder
            old_path = os.path.join(STORAGE_PATH, str(current_user.id), folder.name)
            new_path = os.path.join(STORAGE_PATH, str(current_user.id), dest_folder.name, folder.name)

            if os.path.exists(old_path):
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.move(old_path, new_path)

            # Update database
            folder.parent_id = move_request.destination_folder_id

        db.commit()
        return {"message": f"{move_request.item_type} moved successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error moving {move_request.item_type}: {str(e)}")


@app.post("/items/copy")
async def copy_item(
        copy_request: CopyRequest,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        dest_folder = db.query(Folder).filter(
            Folder.id == copy_request.destination_folder_id,
            Folder.owner_id == current_user.id
        ).first()

        if not dest_folder:
            raise HTTPException(status_code=404, detail="Destination folder not found")

        if copy_request.item_type == ItemType.FILE:
            file = db.query(FileMetadata).filter(
                FileMetadata.id == copy_request.item_id,
                FileMetadata.owner_id == current_user.id
            ).first()

            if not file:
                raise HTTPException(status_code=404, detail="File not found")

            # Generate unique name for copy
            base_name, extension = os.path.splitext(file.filename)
            counter = 1
            new_filename = f"{base_name}_copy{extension}"

            while db.query(FileMetadata).filter(
                    FileMetadata.folder_id == copy_request.destination_folder_id,
                    FileMetadata.filename == new_filename
            ).first():
                new_filename = f"{base_name}_copy_{counter}{extension}"
                counter += 1

            # Copy physical file
            new_file_path = os.path.join(STORAGE_PATH, str(current_user.id), dest_folder.name, new_filename)
            os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
            shutil.copy2(file.filepath, new_file_path)

            # Create new file metadata
            new_file = FileMetadata(
                filename=new_filename,
                filepath=new_file_path,
                mimetype=file.mimetype,
                size=os.path.getsize(new_file_path),
                is_public=False,  # Reset public status for the copy
                folder_id=copy_request.destination_folder_id,
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
                # Create new folder with unique name
                new_name = f"{src_folder.name}_copy"
                ctr = 1
                while db.query(Folder).filter(
                        Folder.parent_id == dest_parent_id,
                        Folder.name == new_name
                ).first():
                    new_name = f"{src_folder.name}_copy_{ctr}"
                    ctr += 1

                new_folder = Folder(
                    name=new_name,
                    parent_id=dest_parent_id,
                    owner_id=current_user.id,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(new_folder)
                db.flush()

                # Create physical folder
                new_folder_path = os.path.join(STORAGE_PATH, str(current_user.id), new_name)
                os.makedirs(new_folder_path, exist_ok=True)

                # Copy files
                files = db.query(FileMetadata).filter(
                    FileMetadata.folder_id == src_folder.id
                ).all()

                for file in files:
                    new_file_path = os.path.join(new_folder_path, file.filename)
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

            copy_folder_recursive(source_folder, copy_request.destination_folder_id)

        db.commit()
        return {"message": f"{copy_request.item_type} copied successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error copying {copy_request.item_type}: {str(e)}")


@app.put("/items/rename")
async def rename_item(
        rename_request: RenameRequest,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        if rename_request.item_type == ItemType.FILE:
            file = db.query(FileMetadata).filter(
                FileMetadata.id == rename_request.item_id,
                FileMetadata.owner_id == current_user.id
            ).first()

            if not file:
                raise HTTPException(status_code=404, detail="File not found")

            # Check for name conflicts
            if db.query(FileMetadata).filter(
                    FileMetadata.folder_id == file.folder_id,
                    FileMetadata.filename == rename_request.new_name,
                    FileMetadata.id != file.id
            ).first():
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
                raise HTTPException(status_code=404, detail="Folder not found")

            # Check for name conflicts
            if db.query(Folder).filter(
                    Folder.parent_id == folder.parent_id,
                    Folder.name == rename_request.new_name,
                    Folder.id != folder.id
            ).first():
                raise HTTPException(status_code=400, detail="A folder with this name already exists")

            # Rename physical folder
            old_path = os.path.join(STORAGE_PATH, str(current_user.id), folder.name)
            new_path = os.path.join(STORAGE_PATH, str(current_user.id), rename_request.new_name)

            if os.path.exists(old_path):
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
        return {"message": f"{rename_request.item_type} renamed successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error renaming {rename_request.item_type}: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)