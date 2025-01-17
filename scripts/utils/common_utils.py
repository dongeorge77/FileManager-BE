import os
from datetime import datetime, timedelta, timezone
from itertools import count
from typing import Optional
import jwt
import mimetypes

from app_constants.app_configurations import STORAGE_PATH, SECRET_KEY
from scripts.models.file_management import FileMetadata
from scripts.models.folder_management import Folder
from scripts.utils.postgresql_util import PostgresUtil


def create_jwt_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt



def sync_directory_with_db(user_id: int, db, base_path: Optional[str] = None) -> None:
    print(f"Base path: {base_path}")
    if base_path is None:
        base_path = os.path.join(STORAGE_PATH, str(user_id))

    # Create user directory if it doesn't exist
    os.makedirs(base_path, exist_ok=True)

    # Get existing database records for comparison
    existing_files = {
        f.filepath: f for f in db.query(FileMetadata).filter(FileMetadata.owner_id == user_id).all()
    }
    print(f"Existing Files: {existing_files}")
    existing_folders = {
        os.path.join(STORAGE_PATH, str(user_id), f.name): f
        for f in db.query(Folder).filter(Folder.owner_id == user_id).all()
    }
    print(f"Existing Folders: {existing_folders}")

    # Walk through the directory
    ctr: int = 1
    for root, dirs, files in os.walk(base_path):
        print(f"{ctr} :::::> {root} {dirs} {files}")
        ctr += 1
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            if dir_path not in existing_folders:
                # Create new folder record
                parent_path = os.path.dirname(dir_path)
                parent_folder = existing_folders.get(parent_path)

                new_folder = Folder(
                    name=dir_name,
                    parent_id=parent_folder.id if parent_folder else None,
                    owner_id=user_id,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(new_folder)
                db.flush()  # Get the ID without committing
                existing_folders[dir_path] = new_folder

        # Handle files
        for file_name in files:
            file_path = os.path.join(root, file_name)
            if file_path not in existing_files:
                # Get parent folder
                parent_path = os.path.dirname(file_path)
                parent_folder = existing_folders.get(parent_path)

                # Create new file record
                mime_type = mimetypes.guess_type(file_name)[0]
                file_size = os.path.getsize(file_path)

                new_file = FileMetadata(
                    filename=file_name,
                    filepath=file_path,
                    mimetype=mime_type,
                    size=file_size,
                    owner_id=user_id,
                    folder_id=parent_folder.id if parent_folder else None,
                    uploaded_at=datetime.now(timezone.utc)
                )
                db.add(new_file)
                existing_files[file_path] = new_file

    # Remove records for files/folders that no longer exist
    for file_path, file_record in existing_files.items():
        if not os.path.exists(file_path):
            db.delete(file_record)

    for folder_path, folder_record in existing_folders.items():
        if not os.path.exists(folder_path):
            db.delete(folder_record)

    db.commit()
    print(f"Sync Completed.........!")