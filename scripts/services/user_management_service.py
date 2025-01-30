import traceback

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta, datetime, timezone

from app_constants.log_module import logger
from app_constants.url import Routes, UserAPI
from scripts.models.user_management import User, Token, UserCreate
from app_constants.connectors import postgres_util, SessionLocal
from app_constants.app_configurations import Constants
from scripts.utils.common_utils import create_jwt_token
from scripts.handlers.user_management_handler import get_current_user
from scripts.models.file_management import FileMetadata


router = APIRouter(prefix=Routes.user)

@router.post(UserAPI.login, response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: SessionLocal = Depends(postgres_util.get_db)):
    try:
        logger.info(f"Running login service")
        user = db.query(User).filter(User.username == form_data.username).first()
        if not user or not Constants.pwd_context.verify(form_data.password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        access_token_expires = timedelta(minutes=Constants.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_jwt_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        logger.debug(f"Failed to login: {e}")
        traceback.print_exc()
        return None

@router.post(UserAPI.create_user, response_model=Token)
async def create_user(user: UserCreate, db: SessionLocal = Depends(postgres_util.get_db)):
    try:
        logger.info(f"Running create user service")
        db_user = User(
            username=user.username,
            email=user.email,
            hashed_password=Constants.pwd_context.hash(user.password),
            is_admin=user.is_admin,
            privilege=user.privilege
        )
        logger.info(f"Creating user: {db_user.username}")
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        access_token = create_jwt_token(data={"sub": user.username})
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        traceback.print_exc()
        logger.debug(f"Failed to create user: {e}")

@router.get(UserAPI.profile, response_model=dict)
async def user_profile(current_user: User = Depends(get_current_user)):
    try:
        logger.info(f"Fetching user profile")
        return {
            "username": current_user.username,
            "email": current_user.email,
            "privilege": current_user.privilege
        }
    except Exception as e:
        traceback.print_exc()
        logger.debug(f"Failed to get User profile")
        raise HTTPException(status_code=500, detail=f"Error retrieving user profile: {str(e)}")


@router.get("/shared/{share_token}")
async def get_shared_file(share_token: str, db: SessionLocal = Depends(postgres_util.get_db)):
    try:
        payload = jwt.decode(share_token, Constants.SECRET_KEY, algorithms=["HS256"])
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




