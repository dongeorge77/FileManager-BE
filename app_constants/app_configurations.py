from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
import configparser

config = configparser.ConfigParser()
config.read('conf/application.conf')


# ---------- VAR DECLARATIONS -----------
LOG_CONFIG_SECTION = "LOG"
MONGO_DB = "MONGODB"


# Constants
SECRET_KEY = "f53b328f-8c52-4778-a715-6e5dc69f69d0"
STORAGE_PATH = "C:\\Users\\DGeorge2\\Downloads\\file_manager_root_dir"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
DATABASE_URL = "postgresql://admin:admin%40123@don.i2clabs.in:5432/file_server"

# -----------LOGGING--------------
LOG_BASE_PATH = config.get(LOG_CONFIG_SECTION, 'base_path')
LOG_LEVEL = config.get(LOG_CONFIG_SECTION, 'level')
FILE_BACKUP_COUNT = config.get(LOG_CONFIG_SECTION, 'file_backup_count')
FILE_BACKUP_SIZE = config.get(LOG_CONFIG_SECTION, 'max_log_file_size')
FILE_NAME = LOG_BASE_PATH + config.get(LOG_CONFIG_SECTION, 'file_name')
LOG_HANDLERS = config.get(LOG_CONFIG_SECTION, 'handlers')