from sqlalchemy import Column, Integer, String, Boolean, event
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._sync_admin_status()

    def _sync_admin_status(self):
        self.is_admin = (self.privilege == "administrator")

@event.listens_for(User.privilege, 'set')
def sync_admin_status(target, value, oldvalue, initiator):
    target._sync_admin_status()


class Token(BaseModel):
    access_token: str
    token_type: str


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    is_admin: bool
    privilege: str

class UserUpdate(BaseModel):
    username: str = None
    email: str = None
    is_admin: bool = None
    privilege: str = None

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_admin: bool
    privilege: str
