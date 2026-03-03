from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal

# ---------- AUTH ----------
class RegisterIn(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=1)  # come richiesto: nessuna restrizione ora

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MeOut(BaseModel):
    id: str
    email: EmailStr
    username: str
    is_superadmin: bool

# ---------- COMMON ----------
class DecisionIn(BaseModel):
    approve: bool

# ---------- CLUB ----------
class ClubCreateIn(BaseModel):
    name: str
    description: str = ""
    location_level: Literal["ITALY","REGION","PROVINCE","CITY"] = "ITALY"
    location_label: str = "Italia"
    join_requests_enabled: bool = False

class ClubOut(BaseModel):
    id: str
    name: str
    description: str
    location_level: str
    location_label: str
    join_requests_enabled: bool
    created_by: str
    created_at: datetime

class ClubMemberOut(BaseModel):
    user_id: str
    username: str
    role: str
    created_at: datetime

class ClubMemberAddByUsernameIn(BaseModel):
    username: str

class ClubMemberRoleUpdateIn(BaseModel):
    role: Literal["MEMBER","ADMIN"]

class ClubJoinRequestOut(BaseModel):
    id: str
    club_id: str
    user_id: str
    username: str
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None

class InviteOut(BaseModel):
    token: str
    expires_at: Optional[datetime] = None

# ---------- SERIES ----------
class CriterionIn(BaseModel):
    key: str
    label: str
    is_required: bool = False
    is_enabled: bool = True
    min_value: float = 0.0
    max_value: float = 5.0
    step: float = 0.5

class CriterionOut(BaseModel):
    id: str
    series_id: str
    key: str
    label: str
    is_required: bool
    is_enabled: bool
    min_value: float
    max_value: float
    step: float

class CriterionUpdateIn(BaseModel):
    label: Optional[str] = None
    is_required: Optional[bool] = None
    is_enabled: Optional[bool] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None

class SeriesCreateIn(BaseModel):
    club_id: str
    title: str
    theme: str = ""
    num_films: int = 4
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    participants_mode: Literal["ALL","NONE","CUSTOM"] = "ALL"
    participant_user_ids: List[str] = []
    criteria: List[CriterionIn] = []

class SeriesOut(BaseModel):
    id: str
    club_id: str
    title: str
    theme: str
    num_films: int
    start_date: Optional[date]
    end_date: Optional[date]
    created_by: str
    created_at: datetime

class SeriesJoinRequestOut(BaseModel):
    id: str
    series_id: str
    user_id: str
    username: str
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None

class SeriesParticipantOut(BaseModel):
    user_id: str
    username: str
    role: str
    created_at: datetime

class SeriesParticipantsPatchIn(BaseModel):
    add_user_ids: List[str] = []
    remove_user_ids: List[str] = []

class SeriesParticipantRoleUpdateIn(BaseModel):
    role: Literal["PARTICIPANT","ADMIN"]

# ---------- FILMS ----------
class FilmCreateIn(BaseModel):
    title: str
    poster_url: Optional[str] = None

class FilmOut(BaseModel):
    id: str
    title: str
    poster_url: Optional[str]
    created_at: datetime

class SeriesFilmAddIn(BaseModel):
    film_id: str
    sort_order: int = 0
    is_voting_open: bool = False

class SeriesFilmOut(BaseModel):
    id: str
    series_id: str
    film_id: str
    title: str
    poster_url: Optional[str]
    is_voting_open: bool
    sort_order: int

class VotingToggleIn(BaseModel):
    is_voting_open: bool

# ---------- PUBLIC VIEWS ----------
class PublicSeriesFilmOut(BaseModel):
    id: str
    film_id: str
    title: str
    poster_url: Optional[str]
    sort_order: int
    is_voting_open: bool

class PublicSeriesOut(BaseModel):
    id: str
    club_id: str
    title: str
    theme: str
    num_films: int
    start_date: Optional[date]
    end_date: Optional[date]
    created_at: datetime
    films: List[PublicSeriesFilmOut]

class ClubPublicOut(BaseModel):
    id: str
    name: str
    description: str
    location_level: str
    location_label: str
    series: List[PublicSeriesOut]

# ---------- VOTES / STATS ----------
class VoteIn(BaseModel):
    series_film_id: str
    criterion_key: str
    value: float

class VoteOut(BaseModel):
    id: str
    series_film_id: str
    criterion_key: str
    user_id: str
    value: float
    created_at: datetime
    updated_at: datetime

class CriterionStats(BaseModel):
    criterion_key: str
    label: str
    count: int
    min: Optional[float]
    max: Optional[float]
    avg: Optional[float]

class FilmStatsOut(BaseModel):
    series_film_id: str
    film_title: str
    stats: List[CriterionStats]

class SeriesStatsOut(BaseModel):
    series_id: str
    films: List[FilmStatsOut]

# ---------- APP SETTINGS (SUPERADMIN) ----------
class AppSettingUpsertIn(BaseModel):
    value: str

class AppSettingOut(BaseModel):
    key: str
    value: str
    updated_at: datetime