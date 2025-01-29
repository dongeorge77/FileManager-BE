import traceback
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app_constants.log_module import logger
from app_constants.app_configurations import Service
from scripts.services.file_management_service import router as file_management_router
from scripts.services.folder_management import router as folder_management_router
from scripts.services.item_management_service import router as item_management_router
from scripts.services.user_management_service import router as user_management_router


app = FastAPI()

app.include_router(file_management_router)
app.include_router(folder_management_router)
app.include_router(item_management_router)
app.include_router(user_management_router)

if Service.ENABLE_CORS in [True, "true", "True"]:
    app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE", "PUT"],
            allow_headers=["*"],
        )

if __name__ == "__main__":
    try:
        logger.debug("APP STARTED")
        logger.info(f"Host: {Service.HOST}, Port: {Service.PORT}")
        uvicorn.run("main:app", host=Service.HOST, port=int(Service.PORT), reload=True, workers=1)
    except Exception as e:
        traceback.print_exc()
        logger.exception(f"Exception while starting app: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Service error")