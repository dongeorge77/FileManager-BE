from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import List, Optional

from scripts.models.file_management import FileInfo
from app_constants.connectors import Base


class Folder(Base):
    __tablename__ = "folders"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    owner = relationship("User", back_populates="folders")
    files = relationship("FileMetadata", back_populates="folder")
    subfolders = relationship("Folder")


class FolderInfo(BaseModel):
    name: str
    path: str
    type: str = "folder"
    modified_at: datetime
    owner_id: int
    folder_id: int  # folder id from database

class DirectoryListing(BaseModel):
    """
    Main response model for directory listing endpoint
    """
    path: str  # Current directory path
    files: List[FileInfo]  # List of files in current directory
    folders: List[FolderInfo]  # List of folders in current directory
    parent_folder_id: Optional[int]  # ID of parent folder (null if in root)
    total_files: int  # Total number of files in current directory
    total_size: int  # Total size of all files in current directory


class FolderCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
