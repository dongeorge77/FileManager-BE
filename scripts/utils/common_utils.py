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


# def get_folder_path(db, folder_id: int, user_id: int) -> str:
#     """
#     Recursively builds the complete path by traversing parent folders
#     Returns the complete path from the base directory
#     """
#     path_components = []
#     current_folder = db.query(Folder).filter(Folder.id == folder_id).first()
#
#     while current_folder:
#         # Verify folder belongs to the user
#         if current_folder.owner_id != user_id:
#             raise ValueError("Access denied: Folder doesn't belong to the user")
#
#         path_components.append(current_folder.name)
#         if current_folder.parent_id:
#             current_folder = db.query(Folder).filter(Folder.id == current_folder.parent_id).first()
#         else:
#             break
#
#     # Reverse to get correct order (root -> leaf)
#     path_components.reverse()
#
#     # Combine with base storage path
#     return os.path.join(STORAGE_PATH, str(user_id), *path_components)


def normalize_path(path: str) -> str:
    return os.path.normpath(path)


def get_folder_path(db, folder_id: int, user_id: int) -> str | None:
    """Recursively determine the filesystem path of a folder from the database."""
    folder = db.query(Folder).filter(Folder.id == folder_id, Folder.owner_id == user_id).first()
    if not folder:
        return None

    path_parts = []
    current_folder = folder
    while current_folder:
        path_parts.insert(0, current_folder.name)
        current_folder = db.query(Folder).filter(
            Folder.id == current_folder.parent_id,
            Folder.owner_id == user_id
        ).first() if current_folder.parent_id else None

    return normalize_path(os.path.join(STORAGE_PATH, str(user_id), *path_parts))


def sync_directory_with_db(user_id: int, db, folder_id: Optional[int] = None) -> None:
    if not sync_lock.acquire(blocking=False):
        print("Sync task is already running. Skipping this request.")
        return

    try:
        print(f"Starting directory sync for user {user_id}")

        # Determine base path
        if folder_id:
            base_path = get_folder_path(db, folder_id, user_id)
            if not base_path or not os.path.exists(base_path):
                raise ValueError(f"Invalid folder_id {folder_id} for user {user_id}")
        else:
            base_path = normalize_path(os.path.join(STORAGE_PATH, str(user_id)))

        os.makedirs(base_path, exist_ok=True)

        # Fetch all user folders and files
        all_folders = db.query(Folder).filter(Folder.owner_id == user_id).all()
        all_files = db.query(FileMetadata).filter(FileMetadata.owner_id == user_id).all()

        # Build folder ID -> full path mapping
        folder_map: Dict[int, Folder] = {f.id: f for f in all_folders}
        folder_paths: Dict[int, str] = {}
        for folder in all_folders:
            path_parts = []
            current = folder
            while current:
                path_parts.insert(0, current.name)
                current = folder_map.get(current.parent_id) if current.parent_id else None
            full_path = os.path.join(STORAGE_PATH, str(user_id), *path_parts)
            folder_paths[folder.id] = normalize_path(full_path)

        # Filter folders/files within the current sync scope
        scope_folders = {
            path: folder for folder_id, path in folder_paths.items()
            if path.startswith(base_path + os.sep) or path == base_path
        }
        scope_files = {
            os.path.join(folder_paths[f.folder_id], f.filename) if f.folder_id
            else os.path.join(STORAGE_PATH, str(user_id), f.filename): f
            for f in all_files
            if (f.folder_id and folder_paths.get(f.folder_id, "").startswith(base_path))
               or (not f.folder_id and base_path == os.path.join(STORAGE_PATH, str(user_id)))
        }

        # Walk directory
        for root, dirs, files in os.walk(base_path):
            # Process directories
            for dir_name in dirs:
                dir_path = normalize_path(os.path.join(root, dir_name))
                if dir_path not in scope_folders:
                    parent_path = normalize_path(os.path.dirname(dir_path))
                    parent_folder = next(
                        (f for f in scope_folders.values() if folder_paths[f.id] == parent_path),
                        None
                    )

                    new_folder = Folder(
                        name=dir_name,
                        parent_id=parent_folder.id if parent_folder else folder_id,
                        owner_id=user_id,
                        created_at=datetime.now(timezone.utc)
                    )
                    db.add(new_folder)
                    db.flush()  # Assign ID

                    # Update mappings
                    folder_map[new_folder.id] = new_folder
                    folder_paths[new_folder.id] = dir_path
                    scope_folders[dir_path] = new_folder

            # Process files
            for file_name in files:
                file_path = normalize_path(os.path.join(root, file_name))
                if file_path not in scope_files:
                    parent_path = normalize_path(os.path.dirname(file_path))
                    parent_folder = next(
                        (f for f in scope_folders.values() if folder_paths[f.id] == parent_path),
                        None
                    )

                    mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
                    file_size = os.path.getsize(file_path)

                    new_file = FileMetadata(
                        filename=file_name,
                        filepath=file_path,
                        mimetype=mime_type,
                        size=file_size,
                        owner_id=user_id,
                        folder_id=parent_folder.id if parent_folder else folder_id,
                        uploaded_at=datetime.now(timezone.utc)
                    )
                    db.add(new_file)
                    scope_files[file_path] = new_file

        # Cleanup orphaned entries
        # Delete files not found on disk
        for file_path, file in list(scope_files.items()):
            if not os.path.exists(file_path):
                db.delete(file)

        # Delete folders from deepest first to avoid FK constraints
        sorted_folders = sorted(
            scope_folders.values(),
            key=lambda f: -len(folder_paths[f.id].split(os.sep))
        )
        for folder in sorted_folders:
            if not os.path.exists(folder_paths[folder.id]):
                db.delete(folder)

        db.commit()
        print(f"Directory sync completed for {base_path}")
    except Exception as e:
        db.rollback()
        print(f"Sync failed: {str(e)}")
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