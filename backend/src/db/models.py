import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    repos = relationship("Repository", back_populates="owner", cascade="all, delete-orphan")
    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    repo_name = Column(String, index=True, nullable=False)
    repo_url = Column(String, nullable=False)
    is_private = Column(Boolean, default=False)
    github_pat = Column(String, nullable=True) # Optional Personal Access Token for this repo
    last_commit_hash = Column(String, nullable=True) # Used for incremental indexing
    last_indexed_at = Column(DateTime, nullable=True)
    
    owner = relationship("User", back_populates="repos")
    sessions = relationship("ChatSession", back_populates="repo", cascade="all, delete-orphan")

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    repo_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="sessions")
    repo = relationship("Repository", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String, nullable=False) # "user" or "assistant"
    content = Column(Text, nullable=False)
    citations = Column(Text, nullable=True) # Stored as JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")
