from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import List, Optional

from app_constants.connectors import Base

class FileMetadata(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    filepath = Column(String)
    mimetype = Column(String)
    size = Column(Integer)
    is_public = Column(Boolean, default=False)
    share_token = Column(String, nullable=True)
    share_expiry = Column(DateTime, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.now(timezone.utc))
    folder_id = Column(Integer, ForeignKey("folders.id"))
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="files")
    folder = relationship("Folder", back_populates="files")


class FileInfo(BaseModel):
    name: str
    path: str
    type: str = "file"
    size: int
    modified_at: datetime
    mime_type: Optional[str]
    is_public: bool = False
    owner_id: int
    id: int  # file id from database


class FileShare(BaseModel):
    file_id: int
    expires_in_hours: Optional[int] = 24
