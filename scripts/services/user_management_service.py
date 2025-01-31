import copy
import traceback
from typing import List
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta, datetime, timezone

from app_constants.log_module import logger
from app_constants.url import Routes, UserAPI
from scripts.models.user_management import User, Token, UserCreate, UserResponse, UserUpdate
from app_constants.connectors import postgres_util, SessionLocal
from app_constants.app_configurations import Constants
from scripts.utils.common_utils import create_jwt_token
from scripts.handlers.user_management_handler import get_current_user
from scripts.models.file_management import FileMetadata
from app_constants.json_keys import user_privileges


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

@router.get(UserAPI.list_users, response_model=List[UserResponse])
async def list_users(db: SessionLocal = Depends(postgres_util.get_db)):
    try:
        logger.info("Fetching list of users")
        users = db.query(User).all()
        return users
    except Exception as e:
        logger.error(f"Failed to fetch users: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# API to edit user details
@router.put(UserAPI.update_user, response_model=UserResponse)
async def edit_user(user_id: int, user_update: UserUpdate, db: SessionLocal = Depends(postgres_util.get_db)):
    try:
        logger.info(f"Editing user with ID: {user_id}")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user_update.username:
            user.username = user_update.username
        if user_update.email:
            user.email = user_update.email
        if user_update.is_admin is not None:
            user.is_admin = user_update.is_admin
        if user_update.privilege:
            user.privilege = user_update.privilege

        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        logger.error(f"Failed to edit user: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# API to get user metadata
@router.get(UserAPI.user_metadata, response_model=List[dict])
async def get_user_metadata():
    try:
        logger.info("Fetching user metadata")
        user_privileges_cp =copy.deepcopy(user_privileges)
        return user_privileges_cp
    except Exception as e:
        logger.error(f"Failed to fetch user metadata: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.delete(UserAPI.delete_user, status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: SessionLocal = Depends(postgres_util.get_db)):
    try:
        logger.info(f"Deleting user with ID: {user_id}")
        user = db.query(User).filter(User.id == user_id).first()

        # Check if the user exists
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Delete the user
        db.delete(user)
        db.commit()

        logger.info(f"User with ID {user_id} deleted successfully")
        return None  # Return 204 No Content on successful deletion

    except Exception as e:
        logger.error(f"Failed to delete user: {e}")
        db.rollback()  # Rollback the transaction in case of an error
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")

