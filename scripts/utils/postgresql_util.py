from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import create_engine
from contextlib import contextmanager
from typing import Generator

from app_constants.app_configurations import DATABASE_URL
from app_constants.log_module import logger


class PostgresUtil:
    def __init__(self):
        self.database_url = DATABASE_URL
        logger.info(f"Creating db connection: {self.database_url}")
        self.engine = create_engine(self.database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.Base = declarative_base()

    def create_tables(self) -> None:
        self.Base.metadata.create_all(bind=self.engine)

    def drop_tables(self) -> None:
        self.Base.metadata.drop_all(bind=self.engine)

    @contextmanager
    def get_db_context(self) -> Generator:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def get_db(self):
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def get_db_dependency(self) -> Generator:
        """FastAPI dependency for database sessions"""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

