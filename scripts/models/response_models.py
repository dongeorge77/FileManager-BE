from pydantic import BaseModel
from scripts.models.user_management import Token

class CreateUser(BaseModel):
    status: str
    message: str
    data: Token
