from enum import Enum
from pydantic import BaseModel

class ItemType(str, Enum):
    FILE = "file"
    FOLDER = "folder"

class DeleteRequest(BaseModel):
    item_type: str
    item_id: int

class MoveRequest(BaseModel):
    item_type: str
    item_id: int
    destination_folder_id: int

class CopyRequest(BaseModel):
    item_type: str
    item_id: int
    destination_folder_id: int


class RenameRequest(BaseModel):
    item_type: str
    item_id: int
    new_name: str