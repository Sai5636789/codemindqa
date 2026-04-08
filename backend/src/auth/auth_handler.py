import os
import time
from typing import Dict, Optional
import jwt
import bcrypt
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-me-in-production")
JWT_ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    """Hashes a plaintext password."""
    salt = bcrypt.gensalt()
    pwd_bytes = password.encode('utf-8')
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a hashed one."""
    pwd_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)

def sign_jwt(user_id: str) -> Dict[str, str]:
    """Generates a JWT token valid for 24 hours."""
    payload = {
        "user_id": user_id,
        "expires": time.time() + 86400  # 24 hours
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": token}

def decode_jwt(token: str) -> Optional[Dict]:
    """Decodes a JWT token and returns payload if valid and not expired."""
    try:
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if decoded_token["expires"] >= time.time():
            return decoded_token
        return None
    except Exception:
        return None
