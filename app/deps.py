from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select
from .db import get_db
from .auth import decode_token
from .models import User, ClubMembership, ClubRole, SeriesParticipant, SeriesRole

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2)) -> User:
    uid = decode_token(token)
    user = db.scalar(select(User).where(User.id == uid))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_superadmin(user: User):
    if not user.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")

def require_club_admin(club_id: str, db: Session, user: User):
    m = db.scalar(select(ClubMembership).where(
        ClubMembership.club_id == club_id,
        ClubMembership.user_id == user.id
    ))
    if not m or m.role != ClubRole.ADMIN:
        raise HTTPException(status_code=403, detail="Club admin required")

def require_series_admin(series_id: str, db: Session, user: User):
    p = db.scalar(select(SeriesParticipant).where(
        SeriesParticipant.series_id == series_id,
        SeriesParticipant.user_id == user.id
    ))
    if not p or p.role != SeriesRole.ADMIN:
        raise HTTPException(status_code=403, detail="Series admin required")