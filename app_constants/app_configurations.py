from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer


# Constants
SECRET_KEY = "f53b328f-8c52-4778-a715-6e5dc69f69d0"
STORAGE_PATH = "C:\\Users\\DGeorge2\\Downloads\\Robot Image"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
DATABASE_URL = "postgresql://admin:admin%40123@don.i2clabs.in:5432/file_server"