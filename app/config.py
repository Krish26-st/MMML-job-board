import os
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from dotenv import load_dotenv

load_dotenv()


def _ensure_rediss_cert_reqs(url: str) -> str:
    """redis-py refuses to even start with a rediss:// URL unless
    ssl_cert_reqs is explicitly present in the query string -- it won't
    assume a default. Rather than rely on whoever sets REDIS_URL to
    remember that query param, add it automatically (CERT_REQUIRED, i.e.
    verify the server's TLS cert normally) whenever it's missing.
    """
    if not url.startswith("rediss://"):
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "ssl_cert_reqs" not in query:
        query["ssl_cert_reqs"] = ["CERT_REQUIRED"]
        parsed = parsed._replace(query=urlencode(query, doseq=True))
        url = urlunparse(parsed)
    return url


class Settings:
    _raw_db_url = os.getenv("DATABASE_URL", "sqlite:///./job_board.db")
    # Render/Railway/Heroku-style providers hand out "postgres://", but
    # SQLAlchemy 2.x requires the "postgresql://" scheme.
    DATABASE_URL: str = _raw_db_url.replace("postgres://", "postgresql://", 1)

    REDIS_URL: str = _ensure_rediss_cert_reqs(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    ALLOWED_ORIGINS: list[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")


settings = Settings()
