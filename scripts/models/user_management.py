from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from pydantic import BaseModel

from app_constants.connectors import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False)
    privilege = Column(String, default="user")
    files = relationship("FileMetadata", back_populates="owner")
    folders = relationship("Folder", back_populates="owner")


class Token(BaseModel):
    access_token: str
    token_type: str


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    is_admin: bool
    privilege: str
