from enum import Enum
from pydantic import BaseModel
from typing import Optional

class ItemType(str, Enum):
    FILE = "file"
    FOLDER = "folder"

class DeleteRequest(BaseModel):
    item_type: str
    item_id: int

class MoveRequest(BaseModel):
    item_type: str
    item_id: int
    destination_folder_id: Optional[int | None] = None

class CopyRequest(BaseModel):
    item_type: str
    item_id: int
    destination_folder_id: Optional[int | None] = None


class RenameRequest(BaseModel):
    item_type: str
    item_id: int
    new_name: str