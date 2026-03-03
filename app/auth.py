from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, status
from .db import settings

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGO = "HS256"

def hash_password(p: str) -> str:
    return pwd.hash(p)

def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)

def create_token(user_id: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=settings.JWT_EXP_MINUTES)
    payload = {"sub": user_id, "exp": exp}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGO)

def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGO])
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")