from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .auth_handler import decode_jwt
from ..db.database import get_db
from ..db.models import User

class JWTBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super(JWTBearer, self).__init__(auto_error=auto_error)

    async def __call__(self, request: Request, db: Session = Depends(get_db)):
        credentials: HTTPAuthorizationCredentials = await super(JWTBearer, self).__call__(request)
        if credentials:
            if not credentials.scheme == "Bearer":
                raise HTTPException(status_code=403, detail="Invalid authentication scheme.")
            
            decoded = decode_jwt(credentials.credentials)
            if not decoded:
                raise HTTPException(status_code=403, detail="Invalid token or expired token.")
            
            user_id = decoded.get("user_id")
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=403, detail="User not found.")
            
            # Attach user to request state globally for access in route handlers
            request.state.user = user
            return credentials.credentials
        else:
            raise HTTPException(status_code=403, detail="Invalid authorization code.")

# Helper dependency to easily get the current user in endpoint functions
def get_current_user(request: Request, _=Security(JWTBearer())):
    return request.state.user
