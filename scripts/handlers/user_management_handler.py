from fastapi import Depends, HTTPException
import jwt

from app_constants.app_configurations import Constants
from scripts.models.user_management import User
from app_constants.connectors import postgres_util, SessionLocal

async def get_current_user(token: str = Depends(Constants.oauth2_scheme), db: SessionLocal = Depends(postgres_util.get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, Constants.SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user