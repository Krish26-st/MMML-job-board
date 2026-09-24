from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .config import settings
from .routers import admin, public

Base.metadata.create_all(bind=engine)

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
