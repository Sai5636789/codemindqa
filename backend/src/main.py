import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import database initialization
from .db.database import Base, engine

# Import routers
from .api.auth import router as auth_router
from .api.repos import router as repos_router
from .api.chat import router as chat_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("backend.log")
    ]
)
logger = logging.getLogger("api")

load_dotenv()

# Create SQLite database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CodeMind API",
    description="Multi-user AI Codebase Q&A system",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register specialized routers
app.include_router(auth_router)
app.include_router(repos_router)
app.include_router(chat_router)

@app.get("/", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "message": "CodeMind API v2 is running"}
