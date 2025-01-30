from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
import configparser

config = configparser.ConfigParser()
config.read('conf/application.conf')


# ---------- VAR DECLARATIONS -----------
LOG_CONFIG_SECTION = "LOG"
SERVICE_SECTION = "SERVICE"
STORAGE_SECTION = "STORAGE"
DATABASE_SECTION = "DATABASE"
CONSTANTS_SECTION = "CONSTANTS"


# Constants
class Constants:
    SECRET_KEY = "f53b328f-8c52-4778-a715-6e5dc69f69d0"
    ACCESS_TOKEN_EXPIRE_MINUTES = config.get(CONSTANTS_SECTION, 'ACCESS_TOKEN_EXPIRE_MINUTES')
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# -----------LOGGING--------------
class Log:
    LOG_BASE_PATH = config.get(LOG_CONFIG_SECTION, 'base_path')
    LOG_LEVEL = config.get(LOG_CONFIG_SECTION, 'level')
    FILE_BACKUP_COUNT = config.get(LOG_CONFIG_SECTION, 'file_backup_count')
    FILE_BACKUP_SIZE = config.get(LOG_CONFIG_SECTION, 'max_log_file_size')
    FILE_NAME = LOG_BASE_PATH + config.get(LOG_CONFIG_SECTION, 'file_name')
    LOG_HANDLERS = config.get(LOG_CONFIG_SECTION, 'handlers')

class Service:
    ENABLE_CORS = config.get(SERVICE_SECTION, "ENABLE_CORS")
    PORT = config.get(SERVICE_SECTION, "PORT")
    HOST = config.get(SERVICE_SECTION, "HOST")
    SECURE_COOKIE = config.get(SERVICE_SECTION, "SECURE_COOKIE")
    VERIFY_SIGNATURE = config.get(SERVICE_SECTION, "VERIFY_SIGNATURE")
    MAX_LOGIN_ATTEMPTS = config.get(SERVICE_SECTION, "MAX_LOGIN_ATTEMPTS")
    LOCK_OUT_TIME_MINS = config.get(SERVICE_SECTION, "LOCK_OUT_TIME_MINS")
    ADD_SESSION_ID = config.get(SERVICE_SECTION, "ADD_SESSION_ID")
    SECURE_ACCESS = config.get(SERVICE_SECTION, "SECURE_ACCESS")
    ROBOT_MONITOR_SERVICE = config.get(SERVICE_SECTION, "ROBOT_MONITOR_SERVICE")
    
class Storage:
    PATH = config.get(STORAGE_SECTION, "PATH")

class Database:
    POSTGRESQL: str = str(config.get(DATABASE_SECTION, "POSTGRESQL"))