from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..db.database import get_db
from ..db.models import User
from ..auth.auth_handler import hash_password, verify_password, sign_jwt
from ..auth.auth_bearer import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class UserSchema(BaseModel):
    username: str
    email: Optional[str] = None
    password: str

class UserLoginSchema(BaseModel):
    username: str
    password: str
    
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user: UserSchema, db: Session = Depends(get_db)):
    # Convert empty strings to None for optional fields so they don't collide
    email_val = user.email.strip() if user.email else None

    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if email_val and db.query(User).filter(User.email == email_val).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        username=user.username,
        email=email_val,
        hashed_password=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return sign_jwt(new_user.id)

@router.post("/login", response_model=TokenResponse)
def login(user: UserLoginSchema, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = sign_jwt(db_user.id)
    return {
        "access_token": token["access_token"],
        "token_type": "bearer",
        "username": db_user.username
    }

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email
    }
