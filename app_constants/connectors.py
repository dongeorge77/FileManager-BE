from scripts.utils.postgresql_util import PostgresUtil

postgres_util = PostgresUtil()
SessionLocal = postgres_util.SessionLocal
Base = postgres_util.Base
