import traceback
from fastapi import APIRouter, UploadFile, Depends, HTTPException, File, Form
from fastapi.responses import FileResponse
import json
import os
import shutil
import mimetypes
from datetime import datetime, timedelta, timezone

from app_constants.url import Routes, FilesAPI
from scripts.models.user_management import User
from scripts.handlers.user_management_handler import get_current_user
from app_constants.log_module import logger
from app_constants.connectors import postgres_util, SessionLocal
from scripts.models.file_management import UploadFileModel, FileShare, FileInfo
from scripts.models.folder_management import Folder
from app_constants.app_configurations import Storage
from scripts.models.file_management import FileMetadata
from scripts.utils.common_utils import create_jwt_token


router = APIRouter(prefix=Routes.files)

@router.post(FilesAPI.upload)
async def upload_file(file: UploadFile = File(...),
                      upload_file_model: str = Form(...),
                      current_user: User = Depends(get_current_user),
                      db: SessionLocal =Depends(postgres_util.get_db)):
    try:
        logger.info(f"Uploading file...!")
        logger.info(f"File name: {file.filename}")
        item = UploadFileModel(**json.loads(upload_file_model)) if upload_file_model else None
        folder_id = item.folder_id if item else None

        # Handle root folder vs specific folder
        # folder = None
        folder_path_parts = []
        if folder_id is not None:
            # Retrieve folder details from the database
            folder = db.query(Folder).filter_by(id=folder_id, owner_id=current_user.id).first()
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found.")

            # Construct the folder path for non-root folder
            current_folder = folder
            while current_folder:
                folder_path_parts.append(current_folder.name)
                current_folder = db.query(Folder).filter_by(id=current_folder.parent_id).first()
            folder_path_parts.reverse()

        # Construct the final path (root or nested folder)
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
            folder_id=folder_id,  # Will be None for root folder
            owner_id=current_user.id,
        )
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
        return db_file

    except json.JSONDecodeError as e:
        logger.debug(f"Failed to decode the json: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {e}")
    except Exception as e:
        logger.debug(f"Failed to upload file: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Error processing request: {e}")

@router.post(FilesAPI.share)
async def share_file(
        file_id: int,
        share_data: FileShare,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        logger.info(f"Sharing file...!")
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
    except Exception as e:
        logger.debug(f"Failed to share the file: {e}")
        traceback.print_exc()

@router.get(FilesAPI.preview)
async def preview_file(
        file_id: int,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    try:
        logger.info(f"Running preview file service...!")
        # Retrieve file metadata from the database
        file_metadata = db.query(FileMetadata).filter(
            FileMetadata.id == file_id,
            FileMetadata.owner_id == current_user.id
        ).first()

        if not file_metadata:
            raise HTTPException(status_code=404, detail="File not found or access denied.")

        # Ensure the file exists on disk
        if not os.path.exists(file_metadata.filepath):
            raise HTTPException(status_code=404, detail="File does not exist on the server.")

        # Return the file content as a response
        return FileResponse(
            file_metadata.filepath,
            media_type=file_metadata.mimetype,
            headers={
                "Content-Disposition": f"inline; filename={file_metadata.filename}"
            }
        )
    except Exception as e:
        logger.error(f"Error previewing file {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while previewing the file.")

