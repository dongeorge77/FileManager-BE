import traceback
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
import os
from datetime import datetime, timezone
from sqlalchemy import func

from app_constants.url import Routes, FolderAPI
from scripts.models.user_management import User
from scripts.handlers.user_management_handler import get_current_user
from app_constants.log_module import logger
from app_constants.connectors import postgres_util, SessionLocal
from scripts.models.file_management import FileInfo
from scripts.models.folder_management import (FolderCreate, Folder, DirectoryListing, ListDirectory, FolderInfo,
                                              CleanDirectory)
from app_constants.app_configurations import Storage
from scripts.models.file_management import FileMetadata
from scripts.utils.common_utils import sync_directory_with_db, get_folder_path

router = APIRouter(prefix=Routes.folders)

@router.post(FolderAPI.list_directory, response_model=DirectoryListing)
async def list_directory(
        background_tasks: BackgroundTasks,
        folder_details: ListDirectory,
        current_user: User = Depends(get_current_user),
        db = Depends(postgres_util.get_db)
):
    try:
        logger.info(f"Listing directory....!")
        # Validate folder exists and user has access
        folder_id = folder_details.folder_id
        if folder_id:
            folder = db.query(Folder).filter(
                Folder.id == folder_id,
                Folder.owner_id == current_user.id
            ).first()
            if not folder:
                raise HTTPException(404, "Folder not found")

        # Trigger sync in background
        background_tasks.add_task(sync_directory_with_db, current_user.id, db, folder_id)

        # Query immediate children only
        folders = db.query(Folder).filter(
            Folder.owner_id == current_user.id,
            Folder.parent_id == folder_id
        ).all()

        files = db.query(FileMetadata).filter(
            FileMetadata.owner_id == current_user.id,
            FileMetadata.folder_id == folder_id
        ).all()

        # Build response
        return DirectoryListing(
            path=get_folder_path(db, folder_id, current_user.id) if folder_id else os.path.join(Storage.PATH,
                                                                                                str(current_user.id)),
            files=[
                FileInfo(
                    name=f.filename,
                    path=f.filepath,
                    size=f.size,
                    modified_at=f.uploaded_at,
                    mime_type=f.mimetype,
                    is_public=f.is_public,
                    owner_id=f.owner_id,
                    id=f.id
                ) for f in files
            ],
            folders=[
                FolderInfo(
                    name=f.name,
                    path=get_folder_path(db, f.id, current_user.id),  # Fixed here
                    modified_at=f.created_at,
                    owner_id=f.owner_id,
                    folder_id=f.id
                ) for f in folders
            ],
            parent_folder_id=folder.parent_id if folder_id else None,
            total_files=len(files),
            total_size=sum(f.size for f in files)
        )
    except Exception as e:
        traceback.print_exc()
        logger.debug(f"Failed to list directory: {e}")

@router.post(FolderAPI.create, response_model=FolderInfo)
async def create_folder(
    folder: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        logger.info(f"Running create folder..!")
        # Check if parent folder exists (if specified)
        if folder.parent_id:
            parent_folder = db.query(Folder).filter(
                Folder.id == folder.parent_id,
                Folder.owner_id == current_user.id
            ).first()
            if not parent_folder:
                raise HTTPException(status_code=404, detail="Parent folder not found")

        # Check for duplicate folder name in the same parent folder
        existing_folder = db.query(Folder).filter(
            Folder.name == folder.name,
            Folder.parent_id == folder.parent_id,
            Folder.owner_id == current_user.id
        ).first()
        if existing_folder:
            raise HTTPException(status_code=400, detail="A folder with this name already exists")

        # Create the folder in database
        new_folder = Folder(
            name=folder.name,
            parent_id=folder.parent_id,
            owner_id=current_user.id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(new_folder)
        db.flush()  # Get the new folder's ID

        # Create physical folder on disk
        folder_path = os.path.join(Storage.PATH, str(current_user.id), folder.name)
        os.makedirs(folder_path, exist_ok=True)

        db.commit()

        return FolderInfo(
            name=new_folder.name,
            path=folder_path,
            modified_at=new_folder.created_at,
            owner_id=new_folder.owner_id,
            folder_id=new_folder.id
        )

    except Exception as e:
        db.rollback()
        logger.debug(f"Failed to create the folder: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating folder: {str(e)}")

@router.post(FolderAPI.clean_directory, response_model=dict)
async def clean_directory(
    folder_details: CleanDirectory,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        folder_id = folder_details.folder_id
        logger.info(f"Cleaning directory for folder ID: {folder_id}")

        def clean_folder_recursive(folder_id):
            # Clean duplicate files in the current folder
            duplicate_files_subquery = (
                db.query(
                    FileMetadata.filename,
                    FileMetadata.mimetype,
                    func.count().label('count')
                )
                .filter(
                    FileMetadata.folder_id == folder_id,
                    FileMetadata.owner_id == current_user.id
                )
                .group_by(FileMetadata.filename, FileMetadata.mimetype)
                .having(func.count() > 1)
                .subquery()
            )

            # Fetch full details of duplicate files
            duplicate_files = (
                db.query(FileMetadata)
                .join(
                    duplicate_files_subquery,
                    (FileMetadata.filename == duplicate_files_subquery.c.filename) &
                    (FileMetadata.mimetype == duplicate_files_subquery.c.mimetype)
                )
                .filter(
                    FileMetadata.folder_id == folder_id,
                    FileMetadata.owner_id == current_user.id
                )
                .all()
            )

            for file in duplicate_files:
                # Keep the first file and delete the rest
                files_to_delete = (
                    db.query(FileMetadata)
                    .filter(
                        FileMetadata.filename == file.filename,
                        FileMetadata.mimetype == file.mimetype,
                        FileMetadata.folder_id == folder_id,
                        FileMetadata.owner_id == current_user.id
                    )
                    .order_by(FileMetadata.uploaded_at)
                    .offset(1)
                    .all()
                )

                for file_to_delete in files_to_delete:
                    db.delete(file_to_delete)

            # Clean duplicate folders in the current folder
            duplicate_folders_subquery = (
                db.query(
                    Folder.name,
                    func.count().label('count')
                )
                .filter(
                    Folder.parent_id == folder_id,
                    Folder.owner_id == current_user.id
                )
                .group_by(Folder.name)
                .having(func.count() > 1)
                .subquery()
            )

            # Fetch full details of duplicate folders
            duplicate_folders = (
                db.query(Folder)
                .join(
                    duplicate_folders_subquery,
                    Folder.name == duplicate_folders_subquery.c.name
                )
                .filter(
                    Folder.parent_id == folder_id,
                    Folder.owner_id == current_user.id
                )
                .all()
            )

            for folder_dup in duplicate_folders:
                # Keep the first folder and delete the rest
                folders_to_delete = (
                    db.query(Folder)
                    .filter(
                        Folder.name == folder_dup.name,
                        Folder.parent_id == folder_id,
                        Folder.owner_id == current_user.id
                    )
                    .order_by(Folder.created_at)
                    .offset(1)
                    .all()
                )

                for folder_to_delete in folders_to_delete:
                    db.delete(folder_to_delete)

            # Recursively clean subfolders
            subfolders = (
                db.query(Folder)
                .filter(
                    Folder.parent_id == folder_id,
                    Folder.owner_id == current_user.id
                )
                .all()
            )

            for subfolder in subfolders:
                clean_folder_recursive(subfolder.id)

        # Start cleaning from the specified folder (or root if folder_id is None)
        clean_folder_recursive(folder_id)

        db.commit()
        logger.info("Directory cleaned successfully")
        return {"message": "Directory cleaned successfully"}

    except Exception as e:
        db.rollback()
        logger.debug(f"Failed to clean directory: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error cleaning directory: {str(e)}")
