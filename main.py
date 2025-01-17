import traceback
import uvicorn
from fastapi import FastAPI, UploadFile, Depends, HTTPException, BackgroundTasks
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
from scripts.models.folder_management import Folder, FolderCreate, DirectoryListing, FolderInfo
from scripts.models.file_management import FileMetadata, FileShare, FileInfo
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


# File Management Endpoints
@app.post("/upload_file/")
async def upload_file(
        file: UploadFile,
        folder_id: Optional[int] = None,
        current_user: User = Depends(get_current_user),
        db = Depends(postgres_util.get_db)
):
    # Create user directory if it doesn't exist
    user_path = os.path.join(STORAGE_PATH, str(current_user.id))
    os.makedirs(user_path, exist_ok=True)

    # Save file
    file_path = os.path.join(user_path, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Create file metadata
    mime_type = mimetypes.guess_type(file.filename)[0]
    file_size = os.path.getsize(file_path)

    db_file = FileMetadata(
        filename=file.filename,
        filepath=file_path,
        mimetype=mime_type,
        size=file_size,
        folder_id=folder_id,
        owner_id=current_user.id
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file


class ListFiles:
    folder_id: Optional[int] = None
    search: Optional[str] = None

# @app.get("/list_files")
# async def list_files(req_data: ListFiles,
#                      current_user: User = Depends(get_current_user),
#                      db: SessionLocal = Depends(get_db)):
#     query = db.query(FileMetadata).filter(FileMetadata.owner_id == current_user.id)
#
#     if req_data.folder_id is not None:
#         query = query.filter(FileMetadata.folder_id == req_data.folder_id)
#     if req_data.search:
#         query = query.filter(FileMetadata.filename.ilike(f"%{req_data.search}%"))
#
#     return query.all()


@app.post("/folders/")
async def create_folder(
        folder: FolderCreate,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    db_folder = Folder(
        name=folder.name,
        parent_id=folder.parent_id,
        owner_id=current_user.id
    )
    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)
    return db_folder


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
        folder_id: Optional[int] = None,
        current_user: User = Depends(get_current_user),
        db: SessionLocal = Depends(postgres_util.get_db)
):
    print(f"Sync directory in the background")
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)