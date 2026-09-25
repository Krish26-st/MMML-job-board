from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .database import Base, engine
from .config import settings
from .routers import admin, public

Base.metadata.create_all(bind=engine)


def _ensure_job_department_column():
    """create_all() only creates tables that don't exist yet -- it never
    alters an existing one. This project has no Alembic migrations set up,
    so for this one small addition (the 'department' column, added for the
    job-card UI), just try to add it and ignore the error if it's already
    there. Worth setting up real migrations if the schema keeps changing.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN department VARCHAR"))
            conn.commit()
    except Exception:
        pass  # column already exists


_ensure_job_department_column()

app = FastAPI(title="MMML Job Board")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(public.router)

# Serves frontend/admin.html at /admin.html and frontend/board.html at /board.html
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
