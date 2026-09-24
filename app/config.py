import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    _raw_db_url = os.getenv("DATABASE_URL", "sqlite:///./job_board.db")
    # Render/Railway/Heroku-style providers hand out "postgres://", but
    # SQLAlchemy 2.x requires the "postgresql://" scheme.
    DATABASE_URL: str = _raw_db_url.replace("postgres://", "postgresql://", 1)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    ALLOWED_ORIGINS: list[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")


settings = Settings()
