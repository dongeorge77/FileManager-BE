import os
import traceback
from datetime import datetime, timedelta, timezone
from itertools import count
from typing import Optional
import jwt
import mimetypes
import psutil
import threading

from app_constants.app_configurations import STORAGE_PATH, SECRET_KEY
from scripts.models.file_management import FileMetadata
from scripts.models.folder_management import Folder
from scripts.utils.postgresql_util import PostgresUtil

sync_lock = threading.Lock()


def create_jwt_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def get_folder_path(db, folder_id: int, user_id: int) -> str:
    """
    Recursively builds the complete path by traversing parent folders
    Returns the complete path from the base directory
    """
    path_components = []
    current_folder = db.query(Folder).filter(Folder.id == folder_id).first()

    while current_folder:
        # Verify folder belongs to the user
        if current_folder.owner_id != user_id:
            raise ValueError("Access denied: Folder doesn't belong to the user")

        path_components.append(current_folder.name)
        if current_folder.parent_id:
            current_folder = db.query(Folder).filter(Folder.id == current_folder.parent_id).first()
        else:
            break

    # Reverse to get correct order (root -> leaf)
    path_components.reverse()

    # Combine with base storage path
    return os.path.join(STORAGE_PATH, str(user_id), *path_components)


def sync_directory_with_db(user_id: int, db, folder_id: Optional[int] = None) -> None:
    if not sync_lock.acquire(blocking=False):
        print("Sync task is already running. Skipping this request.")
        return

    try:
        print(f"Starting the directory sync")

        # Determine the base path based on folder_id
        if folder_id:
            base_path = get_folder_path(db, folder_id, user_id)
        else:
            base_path = os.path.join(STORAGE_PATH, str(user_id))

        # Create directory if it doesn't exist
        os.makedirs(base_path, exist_ok=True)

        # Get existing database records for comparison
        # If folder_id is provided, only get records under that folder
        files_query = db.query(FileMetadata).filter(FileMetadata.owner_id == user_id)
        folders_query = db.query(Folder).filter(Folder.owner_id == user_id)

        if folder_id:
            files_query = files_query.filter(FileMetadata.folder_id == folder_id)
            folders_query = folders_query.filter(Folder.parent_id == folder_id)

        existing_files = {
            f.filepath: f for f in files_query.all()
        }
        existing_folders = {
            os.path.join(STORAGE_PATH, str(user_id), f.name): f
            for f in folders_query.all()
        }

        # Walk through the directory
        for root, dirs, files in os.walk(base_path):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                if dir_path not in existing_folders:
                    # Create new folder record
                    parent_path = os.path.dirname(dir_path)
                    parent_folder = existing_folders.get(parent_path)

                    new_folder = Folder(
                        name=dir_name,
                        parent_id=parent_folder.id if parent_folder else folder_id,  # Use provided folder_id as parent
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
                        folder_id=parent_folder.id if parent_folder else folder_id,  # Use provided folder_id
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
        print(f"Directory Sync Completed.")
    except Exception as e:
        print(f"Failed to sync the directory: {e}")
        traceback.print_exc()
    finally:
        sync_lock.release()


def is_file_accessible(filepath):
    try:
        with open(filepath, 'rb'):
            return True
    except IOError:
        return False


def get_process_locking_file(filepath):
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for file in proc.open_files():
                if file.path == filepath:
                    return proc
        except Exception:
            pass
    return None