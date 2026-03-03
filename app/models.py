import enum
import uuid
from datetime import datetime, date
from sqlalchemy import (
    String, Text, DateTime, Date, Boolean, Integer, Float,
    ForeignKey, UniqueConstraint, Enum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def _uuid():
    return str(uuid.uuid4())

class ClubRole(str, enum.Enum):
    MEMBER = "MEMBER"
    ADMIN = "ADMIN"

class ReqStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"

class LocationLevel(str, enum.Enum):
    ITALY = "ITALY"
    REGION = "REGION"
    PROVINCE = "PROVINCE"
    CITY = "CITY"

class SeriesRole(str, enum.Enum):
    PARTICIPANT = "PARTICIPANT"
    ADMIN = "ADMIN"

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class Cineclub(Base):
    __tablename__ = "cineclubs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    location_level: Mapped[LocationLevel] = mapped_column(Enum(LocationLevel), default=LocationLevel.ITALY, nullable=False)
    location_label: Mapped[str] = mapped_column(String(120), default="Italia", nullable=False)
    join_requests_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class ClubMembership(Base):
    __tablename__ = "club_memberships"
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    club_id: Mapped[str] = mapped_column(String, ForeignKey("cineclubs.id"), primary_key=True)
    role: Mapped[ClubRole] = mapped_column(Enum(ClubRole), default=ClubRole.MEMBER, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class ClubJoinRequest(Base):
    __tablename__ = "club_join_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    club_id: Mapped[str] = mapped_column(String, ForeignKey("cineclubs.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True, nullable=False)
    status: Mapped[ReqStatus] = mapped_column(Enum(ReqStatus), default=ReqStatus.PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)

    __table_args__ = (UniqueConstraint("club_id", "user_id", name="uq_club_req_user"),)

class ClubInvite(Base):
    __tablename__ = "club_invites"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    club_id: Mapped[str] = mapped_column(String, ForeignKey("cineclubs.id"), index=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class ScreeningSeries(Base):
    __tablename__ = "series"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    club_id: Mapped[str] = mapped_column(String, ForeignKey("cineclubs.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    theme: Mapped[str] = mapped_column(Text, default="", nullable=False)
    num_films: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class SeriesParticipant(Base):
    __tablename__ = "series_participants"
    series_id: Mapped[str] = mapped_column(String, ForeignKey("series.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    role: Mapped[SeriesRole] = mapped_column(Enum(SeriesRole), default=SeriesRole.PARTICIPANT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class SeriesJoinRequest(Base):
    __tablename__ = "series_join_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    series_id: Mapped[str] = mapped_column(String, ForeignKey("series.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True, nullable=False)
    status: Mapped[ReqStatus] = mapped_column(Enum(ReqStatus), default=ReqStatus.PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)

    __table_args__ = (UniqueConstraint("series_id", "user_id", name="uq_series_req_user"),)

class Film(Base):
    __tablename__ = "films"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    poster_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class SeriesFilm(Base):
    __tablename__ = "series_films"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    series_id: Mapped[str] = mapped_column(String, ForeignKey("series.id"), index=True, nullable=False)
    film_id: Mapped[str] = mapped_column(String, ForeignKey("films.id"), index=True, nullable=False)
    is_voting_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("series_id", "film_id", name="uq_series_film"),)

class RatingCriterion(Base):
    __tablename__ = "criteria"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    series_id: Mapped[str] = mapped_column(String, ForeignKey("series.id"), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(60), nullable=False)     # es "overall", "direction"
    label: Mapped[str] = mapped_column(String(80), nullable=False)   # es "Voto film", "Regia"
    min_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_value: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    step: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("series_id", "key", name="uq_series_criterion_key"),)

class Vote(Base):
    __tablename__ = "votes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    series_film_id: Mapped[str] = mapped_column(String, ForeignKey("series_films.id"), index=True, nullable=False)
    criterion_id: Mapped[str] = mapped_column(String, ForeignKey("criteria.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("series_film_id", "criterion_id", "user_id", name="uq_vote"),)
    
class AppSetting(Base):
    """
    Key/value settings controllabili dal superadmin.
    Esempi: feature flags, limiti, moderazione, ecc.
    """
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)