from sqlalchemy import func
import traceback
from typing import Optional

from app_constants.log_module import logger
from app_constants.connectors import SessionLocal
from scripts.models.file_management import FileMetadata
from scripts.models.folder_management import Folder
from app_constants.constants import CommonConstants

async def clean_directory(current_user_id: int, db: SessionLocal, current_folder_id: Optional[int | None] = None) -> dict:
    response_data: dict = {CommonConstants.message: "Failed to clean the directory",
                           CommonConstants.status: CommonConstants.failed}
    try:
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
                    FileMetadata.owner_id == current_user_id
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
                    FileMetadata.owner_id == current_user_id
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
                        FileMetadata.owner_id == current_user_id
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
                    Folder.owner_id == current_user_id
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
                    Folder.owner_id == current_user_id
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
                        Folder.owner_id == current_user_id
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
                    Folder.owner_id == current_user_id
                )
                .all()
            )

            for subfolder in subfolders:
                clean_folder_recursive(subfolder.id)

        # Start cleaning from the specified folder (or root if folder_id is None)
        clean_folder_recursive(current_folder_id)
        db.commit()
        logger.info("Directory cleaned successfully")
        response_data[CommonConstants.message] = "Directory cleaned successfully"
        response_data[CommonConstants.status] = CommonConstants.success
    except Exception as e:
        traceback.print_exc()
        logger.debug(f"Failed to run clean directory handler: {e}")
    return response_data