import os
import secrets
import uuid
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from .db import engine, Base, get_db
from . import models, schemas, auth
from .deps import (
    get_current_user,
    require_club_admin,
    require_series_admin,
    require_superadmin,
)

app = FastAPI(title="Cineforum API")

# ---------------- CORS (frontend separato) ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in prod metti una allowlist
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- STATIC (poster upload locale) ----------------
STATIC_DIR = os.getenv("STATIC_DIR", "static")
POSTERS_DIR = os.path.join(STATIC_DIR, "posters")
os.makedirs(POSTERS_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# crea tabelle (dev). In prod: migrazioni alembic.
Base.metadata.create_all(bind=engine)

DEFAULT_CRITERIA = [
    ("overall", "Voto film", True),
    ("direction", "Regia", False),
    ("screenplay", "Sceneggiatura", False),
    ("cinematography", "Fotografia", False),
    ("lead_actor", "Attore protagonista", False),
    ("lead_actress", "Attrice protagonista", False),
    ("supporting_actors", "Attori non protagonisti", False),
    ("supporting_actresses", "Attrici non protagoniste", False),
    ("casting", "Casting", False),
    ("costumes", "Costumi", False),
    ("vfx", "Effetti speciali", False),
    ("sound", "Sonoro", False),
    ("score", "Colonna sonora", False),
]

def seed_superadmin(db: Session):
    u = db.scalar(select(models.User).where(models.User.email == "a"))
    if not u:
        su = models.User(
            email="a",
            username="a",
            password_hash=auth.hash_password("a"),
            is_superadmin=True,
        )
        db.add(su)
        db.commit()

@app.on_event("startup")
def _startup():
    db = next(get_db())
    seed_superadmin(db)
    db.close()

# ---------------- HELPERS ----------------
def _ensure_club_member(club_id: str, db: Session, user: models.User) -> models.ClubMembership:
    m = db.scalar(select(models.ClubMembership).where(
        models.ClubMembership.club_id == club_id,
        models.ClubMembership.user_id == user.id
    ))
    if not m:
        raise HTTPException(403, "Devi essere membro del club")
    return m

def _ensure_series_participant(series_id: str, db: Session, user: models.User) -> models.SeriesParticipant:
    p = db.scalar(select(models.SeriesParticipant).where(
        models.SeriesParticipant.series_id == series_id,
        models.SeriesParticipant.user_id == user.id
    ))
    if not p:
        raise HTTPException(403, "Devi essere partecipante della rassegna")
    return p

def _club_exists(club_id: str, db: Session) -> models.Cineclub:
    club = db.scalar(select(models.Cineclub).where(models.Cineclub.id == club_id))
    if not club:
        raise HTTPException(404, "Club non trovato")
    return club

def _series_exists(series_id: str, db: Session) -> models.ScreeningSeries:
    s = db.scalar(select(models.ScreeningSeries).where(models.ScreeningSeries.id == series_id))
    if not s:
        raise HTTPException(404, "Rassegna non trovata")
    return s

def _save_poster(file: UploadFile) -> str:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(400, "Formato non supportato (jpg/jpeg/png/webp)")
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(POSTERS_DIR, name)
    with open(path, "wb") as f:
        f.write(file.file.read())
    return f"/static/posters/{name}"

# ---------------- AUTH ----------------
@app.post("/auth/register", response_model=schemas.TokenOut)
def register(payload: schemas.RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(models.User).where(models.User.email == payload.email)):
        raise HTTPException(400, "Email già usata")
    if db.scalar(select(models.User).where(models.User.username == payload.username)):
        raise HTTPException(400, "Username già usato")
    u = models.User(
        email=payload.email,
        username=payload.username,
        password_hash=auth.hash_password(payload.password),
        is_superadmin=False
    )
    db.add(u); db.commit(); db.refresh(u)
    return schemas.TokenOut(access_token=auth.create_token(u.id))

@app.post("/auth/login", response_model=schemas.TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    u = db.scalar(select(models.User).where(
        (models.User.email == form.username) | (models.User.username == form.username)
    ))
    if not u or not auth.verify_password(form.password, u.password_hash):
        raise HTTPException(401, "Credenziali errate")
    return schemas.TokenOut(access_token=auth.create_token(u.id))

@app.get("/auth/me", response_model=schemas.MeOut)
def me(user: models.User = Depends(get_current_user)):
    return schemas.MeOut(id=user.id, email=user.email, username=user.username, is_superadmin=user.is_superadmin)

# ---------------- APP SETTINGS (SUPERADMIN) ----------------
@app.get("/app/settings", response_model=list[schemas.AppSettingOut])
def list_app_settings(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_superadmin(user)
    rows = db.execute(select(models.AppSetting)).scalars().all()
    return [schemas.AppSettingOut(key=r.key, value=r.value, updated_at=r.updated_at) for r in rows]

@app.put("/app/settings/{key}", response_model=schemas.AppSettingOut)
def upsert_app_setting(
    key: str,
    payload: schemas.AppSettingUpsertIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_superadmin(user)
    s = db.scalar(select(models.AppSetting).where(models.AppSetting.key == key))
    if not s:
        s = models.AppSetting(key=key, value=payload.value, updated_at=datetime.utcnow())
        db.add(s)
    else:
        s.value = payload.value
        s.updated_at = datetime.utcnow()
    db.commit()
    return schemas.AppSettingOut(key=s.key, value=s.value, updated_at=s.updated_at)

# ---------------- CLUBS ----------------
@app.post("/clubs", response_model=schemas.ClubOut)
def create_club(payload: schemas.ClubCreateIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    club = models.Cineclub(
        name=payload.name,
        description=payload.description,
        location_level=models.LocationLevel(payload.location_level),
        location_label=payload.location_label or "Italia",
        join_requests_enabled=payload.join_requests_enabled,
        created_by=user.id
    )
    db.add(club); db.commit(); db.refresh(club)
    db.add(models.ClubMembership(user_id=user.id, club_id=club.id, role=models.ClubRole.ADMIN))
    db.commit()
    return club

@app.get("/clubs/{club_id}", response_model=schemas.ClubOut)
def get_club(club_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return _club_exists(club_id, db)

@app.get("/clubs/{club_id}/public", response_model=schemas.ClubPublicOut)
def get_club_public(club_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    club = _club_exists(club_id, db)
    series_rows = db.execute(
        select(models.ScreeningSeries)
        .where(models.ScreeningSeries.club_id == club_id)
        .order_by(models.ScreeningSeries.created_at.desc())
    ).scalars().all()

    public_series: list[schemas.PublicSeriesOut] = []
    for s in series_rows:
        sf_rows = db.execute(
            select(models.SeriesFilm, models.Film)
            .join(models.Film, models.Film.id == models.SeriesFilm.film_id)
            .where(models.SeriesFilm.series_id == s.id)
            .order_by(models.SeriesFilm.sort_order.asc(), models.SeriesFilm.created_at.asc())
        ).all()

        films = [
            schemas.PublicSeriesFilmOut(
                id=sf.id,
                film_id=f.id,
                title=f.title,
                poster_url=f.poster_url,
                sort_order=sf.sort_order,
                is_voting_open=sf.is_voting_open,
            )
            for (sf, f) in sf_rows
        ]

        public_series.append(
            schemas.PublicSeriesOut(
                id=s.id,
                club_id=s.club_id,
                title=s.title,
                theme=s.theme,
                num_films=s.num_films,
                start_date=s.start_date,
                end_date=s.end_date,
                created_at=s.created_at,
                films=films,
            )
        )

    return schemas.ClubPublicOut(
        id=club.id,
        name=club.name,
        description=club.description,
        location_level=club.location_level.value,
        location_label=club.location_label,
        series=public_series,
    )

@app.get("/clubs/{club_id}/members", response_model=list[schemas.ClubMemberOut])
def club_members(club_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    _ensure_club_member(club_id, db, user)
    rows = db.execute(
        select(models.ClubMembership, models.User)
        .join(models.User, models.User.id == models.ClubMembership.user_id)
        .where(models.ClubMembership.club_id == club_id)
        .order_by(models.ClubMembership.created_at.asc())
    ).all()
    return [
        schemas.ClubMemberOut(
            user_id=m.user_id,
            username=u.username,
            role=m.role.value,
            created_at=m.created_at
        )
        for (m, u) in rows
    ]

@app.post("/clubs/{club_id}/members:add-by-username", response_model=schemas.ClubMemberOut)
def club_add_member_by_username(
    club_id: str,
    payload: schemas.ClubMemberAddByUsernameIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    require_club_admin(club_id, db, user)
    target = db.scalar(select(models.User).where(models.User.username == payload.username))
    if not target:
        raise HTTPException(404, "Utente non trovato")
    existing = db.scalar(select(models.ClubMembership).where(
        models.ClubMembership.club_id == club_id,
        models.ClubMembership.user_id == target.id
    ))
    if existing:
        raise HTTPException(400, "Utente già membro")
    m = models.ClubMembership(user_id=target.id, club_id=club_id, role=models.ClubRole.MEMBER)
    db.add(m); db.commit()
    return schemas.ClubMemberOut(user_id=target.id, username=target.username, role=m.role.value, created_at=m.created_at)

@app.patch("/clubs/{club_id}/members/{user_id}/role", response_model=schemas.ClubMemberOut)
def club_update_member_role(
    club_id: str,
    user_id: str,
    payload: schemas.ClubMemberRoleUpdateIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    require_club_admin(club_id, db, user)
    m = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == club_id, models.ClubMembership.user_id == user_id))
    if not m:
        raise HTTPException(404, "Membership non trovata")
    m.role = models.ClubRole(payload.role)
    db.commit()
    u = db.scalar(select(models.User).where(models.User.id == user_id))
    return schemas.ClubMemberOut(user_id=m.user_id, username=u.username if u else "", role=m.role.value, created_at=m.created_at)

@app.post("/clubs/{club_id}/invites", response_model=schemas.InviteOut)
def create_invite(club_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_club_admin(club_id, db, user)
    token = secrets.token_urlsafe(32)
    inv = models.ClubInvite(token=token, club_id=club_id, created_by=user.id, expires_at=None)
    db.add(inv); db.commit()
    return schemas.InviteOut(token=token, expires_at=inv.expires_at)

@app.post("/clubs/join/{token}")
def join_by_invite(token: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    inv = db.scalar(select(models.ClubInvite).where(models.ClubInvite.token == token))
    if not inv:
        raise HTTPException(404, "Invito non valido")
    if inv.expires_at and inv.expires_at < datetime.utcnow():
        raise HTTPException(400, "Invito scaduto")
    existing = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == inv.club_id, models.ClubMembership.user_id == user.id))
    if existing:
        return {"ok": True, "message": "Sei già membro"}
    db.add(models.ClubMembership(user_id=user.id, club_id=inv.club_id, role=models.ClubRole.MEMBER))
    db.commit()
    return {"ok": True}

@app.post("/clubs/{club_id}/join-request")
def request_join_club(club_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    club = _club_exists(club_id, db)
    if not club.join_requests_enabled:
        raise HTTPException(400, "Richieste accesso non abilitate")
    if db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == club_id, models.ClubMembership.user_id == user.id)):
        raise HTTPException(400, "Sei già membro")

    req = models.ClubJoinRequest(club_id=club_id, user_id=user.id)
    db.add(req)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(400, "Richiesta già presente")
    return {"ok": True}

@app.get("/clubs/{club_id}/join-requests", response_model=list[schemas.ClubJoinRequestOut])
def list_club_join_requests(
    club_id: str,
    status: str | None = Query(default=None, description="PENDING/APPROVED/DECLINED"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    require_club_admin(club_id, db, user)
    q = (
        select(models.ClubJoinRequest, models.User)
        .join(models.User, models.User.id == models.ClubJoinRequest.user_id)
        .where(models.ClubJoinRequest.club_id == club_id)
        .order_by(models.ClubJoinRequest.created_at.desc())
    )
    if status:
        q = q.where(models.ClubJoinRequest.status == models.ReqStatus(status))
    rows = db.execute(q).all()
    return [
        schemas.ClubJoinRequestOut(
            id=r.id,
            club_id=r.club_id,
            user_id=r.user_id,
            username=u.username,
            status=r.status.value,
            created_at=r.created_at,
            decided_at=r.decided_at,
            decided_by=r.decided_by,
        )
        for (r, u) in rows
    ]

@app.post("/clubs/{club_id}/join-request/{req_id}/decide")
def decide_join_club(
    club_id: str,
    req_id: str,
    payload: schemas.DecisionIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    require_club_admin(club_id, db, user)
    req = db.scalar(select(models.ClubJoinRequest).where(models.ClubJoinRequest.id == req_id, models.ClubJoinRequest.club_id == club_id))
    if not req or req.status != models.ReqStatus.PENDING:
        raise HTTPException(404, "Richiesta non valida")

    approve = payload.approve
    req.status = models.ReqStatus.APPROVED if approve else models.ReqStatus.DECLINED
    req.decided_at = datetime.utcnow()
    req.decided_by = user.id
    db.commit()

    if approve:
        existing = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == club_id, models.ClubMembership.user_id == req.user_id))
        if not existing:
            db.add(models.ClubMembership(user_id=req.user_id, club_id=club_id, role=models.ClubRole.MEMBER))
            db.commit()

    return {"ok": True}

@app.get("/clubs/popular", response_model=list[schemas.ClubOut])
def popular_clubs(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    members = func.count(models.ClubMembership.user_id)
    series = func.count(func.distinct(models.ScreeningSeries.id))
    films = func.count(func.distinct(models.SeriesFilm.id))

    q = (
        select(models.Cineclub)
        .join(models.ClubMembership, models.ClubMembership.club_id == models.Cineclub.id, isouter=True)
        .join(models.ScreeningSeries, models.ScreeningSeries.club_id == models.Cineclub.id, isouter=True)
        .join(models.SeriesFilm, models.SeriesFilm.series_id == models.ScreeningSeries.id, isouter=True)
        .group_by(models.Cineclub.id)
        .order_by((members + 2*series + 0.5*films).desc())
        .limit(20)
    )
    return db.execute(q).scalars().all()

@app.get("/clubs/search", response_model=list[schemas.ClubOut])
def search_clubs(
    q: str | None = Query(default=None, description="Ricerca su name (case-insensitive, contains)"),
    location_level: str | None = Query(default=None, description="ITALY/REGION/PROVINCE/CITY"),
    location_label: str | None = Query(default=None, description="Ricerca su location_label (case-insensitive, contains)"),
    sort: str = Query(default="popular", description="popular|newest|name"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    base_q = select(models.Cineclub)

    if q:
        base_q = base_q.where(models.Cineclub.name.ilike(f"%{q}%"))
    if location_level:
        base_q = base_q.where(models.Cineclub.location_level == models.LocationLevel(location_level))
    if location_label:
        base_q = base_q.where(models.Cineclub.location_label.ilike(f"%{location_label}%"))

    if sort == "newest":
        return db.execute(base_q.order_by(models.Cineclub.created_at.desc()).limit(limit).offset(offset)).scalars().all()

    if sort == "name":
        return db.execute(base_q.order_by(models.Cineclub.name.asc()).limit(limit).offset(offset)).scalars().all()

    members = func.count(models.ClubMembership.user_id)
    series = func.count(func.distinct(models.ScreeningSeries.id))
    films = func.count(func.distinct(models.SeriesFilm.id))

    pop_q = (
        select(models.Cineclub)
        .join(models.ClubMembership, models.ClubMembership.club_id == models.Cineclub.id, isouter=True)
        .join(models.ScreeningSeries, models.ScreeningSeries.club_id == models.Cineclub.id, isouter=True)
        .join(models.SeriesFilm, models.SeriesFilm.series_id == models.ScreeningSeries.id, isouter=True)
    )

    if q:
        pop_q = pop_q.where(models.Cineclub.name.ilike(f"%{q}%"))
    if location_level:
        pop_q = pop_q.where(models.Cineclub.location_level == models.LocationLevel(location_level))
    if location_label:
        pop_q = pop_q.where(models.Cineclub.location_label.ilike(f"%{location_label}%"))

    pop_q = (
        pop_q.group_by(models.Cineclub.id)
        .order_by((members + 2*series + 0.5*films).desc())
        .limit(limit).offset(offset)
    )
    return db.execute(pop_q).scalars().all()

@app.get("/clubs/{club_id}/series", response_model=list[schemas.SeriesOut])
def list_series_for_club(
    club_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    _club_exists(club_id, db)
    rows = db.execute(
        select(models.ScreeningSeries)
        .where(models.ScreeningSeries.club_id == club_id)
        .order_by(models.ScreeningSeries.created_at.desc())
    ).scalars().all()
    return rows

# ---------------- SERIES ----------------
@app.post("/series", response_model=schemas.SeriesOut)
def create_series(payload: schemas.SeriesCreateIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_club_admin(payload.club_id, db, user)

    s = models.ScreeningSeries(
        club_id=payload.club_id,
        title=payload.title,
        theme=payload.theme,
        num_films=payload.num_films,
        start_date=payload.start_date,
        end_date=payload.end_date,
        created_by=user.id
    )
    db.add(s); db.commit(); db.refresh(s)

    db.add(models.SeriesParticipant(series_id=s.id, user_id=user.id, role=models.SeriesRole.ADMIN))

    if payload.participants_mode == "ALL":
        members = db.execute(select(models.ClubMembership.user_id).where(models.ClubMembership.club_id == payload.club_id)).scalars().all()
        for uid in members:
            if uid != user.id:
                db.add(models.SeriesParticipant(series_id=s.id, user_id=uid, role=models.SeriesRole.PARTICIPANT))
    elif payload.participants_mode == "CUSTOM":
        for uid in payload.participant_user_ids:
            is_member = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == payload.club_id, models.ClubMembership.user_id == uid))
            if is_member:
                db.add(models.SeriesParticipant(series_id=s.id, user_id=uid, role=models.SeriesRole.PARTICIPANT))

    criteria = payload.criteria
    if not any(c.key == "overall" for c in criteria):
        criteria = [schemas.CriterionIn(key="overall", label="Voto film", is_required=True)] + criteria

    for c in criteria:
        db.add(models.RatingCriterion(
            series_id=s.id,
            key=c.key,
            label=c.label,
            is_required=c.is_required,
            is_enabled=c.is_enabled,
            min_value=c.min_value,
            max_value=c.max_value,
            step=c.step,
        ))

    db.commit()
    return s

@app.get("/series/{series_id}", response_model=schemas.SeriesOut)
def get_series(series_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s = _series_exists(series_id, db)
    _ensure_club_member(s.club_id, db, user)
    return s

@app.get("/series/{series_id}/participants", response_model=list[schemas.SeriesParticipantOut])
def list_series_participants(series_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s = _series_exists(series_id, db)
    _ensure_club_member(s.club_id, db, user)
    rows = db.execute(
        select(models.SeriesParticipant, models.User)
        .join(models.User, models.User.id == models.SeriesParticipant.user_id)
        .where(models.SeriesParticipant.series_id == series_id)
        .order_by(models.SeriesParticipant.created_at.asc())
    ).all()
    return [
        schemas.SeriesParticipantOut(user_id=p.user_id, username=u.username, role=p.role.value, created_at=p.created_at)
        for (p, u) in rows
    ]

@app.patch("/series/{series_id}/participants", response_model=dict)
def patch_series_participants(
    series_id: str,
    payload: schemas.SeriesParticipantsPatchIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    s = _series_exists(series_id, db)
    require_series_admin(series_id, db, user)

    for uid in payload.add_user_ids:
        is_member = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == s.club_id, models.ClubMembership.user_id == uid))
        if not is_member:
            continue
        exists = db.scalar(select(models.SeriesParticipant).where(models.SeriesParticipant.series_id == series_id, models.SeriesParticipant.user_id == uid))
        if not exists:
            db.add(models.SeriesParticipant(series_id=series_id, user_id=uid, role=models.SeriesRole.PARTICIPANT))

    if payload.remove_user_ids:
        admins = db.execute(
            select(models.SeriesParticipant.user_id)
            .where(models.SeriesParticipant.series_id == series_id, models.SeriesParticipant.role == models.SeriesRole.ADMIN)
        ).scalars().all()

        for uid in payload.remove_user_ids:
            p = db.scalar(select(models.SeriesParticipant).where(models.SeriesParticipant.series_id == series_id, models.SeriesParticipant.user_id == uid))
            if not p:
                continue
            if p.role == models.SeriesRole.ADMIN and len(admins) <= 1:
                continue
            db.delete(p)

    db.commit()
    return {"ok": True}

@app.patch("/series/{series_id}/participants/{user_id}/role", response_model=schemas.SeriesParticipantOut)
def update_series_participant_role(
    series_id: str,
    user_id: str,
    payload: schemas.SeriesParticipantRoleUpdateIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    require_series_admin(series_id, db, user)
    p = db.scalar(select(models.SeriesParticipant).where(models.SeriesParticipant.series_id == series_id, models.SeriesParticipant.user_id == user_id))
    if not p:
        raise HTTPException(404, "Partecipante non trovato")

    if p.role == models.SeriesRole.ADMIN and payload.role != "ADMIN":
        admins = db.execute(
            select(models.SeriesParticipant.user_id)
            .where(models.SeriesParticipant.series_id == series_id, models.SeriesParticipant.role == models.SeriesRole.ADMIN)
        ).scalars().all()
        if len(admins) <= 1:
            raise HTTPException(400, "Non puoi rimuovere l'ultimo admin della rassegna")

    p.role = models.SeriesRole(payload.role)
    db.commit()
    u = db.scalar(select(models.User).where(models.User.id == user_id))
    return schemas.SeriesParticipantOut(user_id=p.user_id, username=u.username if u else "", role=p.role.value, created_at=p.created_at)

# ---- criteri ----
@app.get("/series/{series_id}/criteria", response_model=list[schemas.CriterionOut])
def list_criteria(series_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s = _series_exists(series_id, db)
    _ensure_club_member(s.club_id, db, user)
    rows = db.execute(
        select(models.RatingCriterion)
        .where(models.RatingCriterion.series_id == series_id)
        .order_by(models.RatingCriterion.key.asc())
    ).scalars().all()
    return [
        schemas.CriterionOut(
            id=r.id, series_id=r.series_id, key=r.key, label=r.label,
            is_required=r.is_required, is_enabled=r.is_enabled,
            min_value=r.min_value, max_value=r.max_value, step=r.step
        )
        for r in rows
    ]

@app.post("/series/{series_id}/criteria", response_model=schemas.CriterionOut)
def add_custom_criterion(series_id: str, payload: schemas.CriterionIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_series_admin(series_id, db, user)
    if payload.key == "overall":
        raise HTTPException(400, "Il criterio 'overall' è riservato")
    c = models.RatingCriterion(
        series_id=series_id,
        key=payload.key,
        label=payload.label,
        is_required=payload.is_required,
        is_enabled=payload.is_enabled,
        min_value=payload.min_value,
        max_value=payload.max_value,
        step=payload.step
    )
    db.add(c)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(400, "Chiave criterio già esistente per questa rassegna")
    db.refresh(c)
    return schemas.CriterionOut(
        id=c.id, series_id=c.series_id, key=c.key, label=c.label,
        is_required=c.is_required, is_enabled=c.is_enabled,
        min_value=c.min_value, max_value=c.max_value, step=c.step
    )

@app.patch("/criteria/{criterion_id}", response_model=schemas.CriterionOut)
def update_criterion(criterion_id: str, payload: schemas.CriterionUpdateIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    c = db.scalar(select(models.RatingCriterion).where(models.RatingCriterion.id == criterion_id))
    if not c:
        raise HTTPException(404, "Criterio non trovato")
    require_series_admin(c.series_id, db, user)

    if payload.label is not None: c.label = payload.label
    if payload.is_required is not None: c.is_required = payload.is_required
    if payload.is_enabled is not None: c.is_enabled = payload.is_enabled
    if payload.min_value is not None: c.min_value = payload.min_value
    if payload.max_value is not None: c.max_value = payload.max_value
    if payload.step is not None: c.step = payload.step

    db.commit()
    return schemas.CriterionOut(
        id=c.id, series_id=c.series_id, key=c.key, label=c.label,
        is_required=c.is_required, is_enabled=c.is_enabled,
        min_value=c.min_value, max_value=c.max_value, step=c.step
    )

# ---- join requests rassegna ----
@app.post("/series/{series_id}/join-request")
def request_join_series(series_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s = _series_exists(series_id, db)
    _ensure_club_member(s.club_id, db, user)

    if db.scalar(select(models.SeriesParticipant).where(models.SeriesParticipant.series_id == series_id, models.SeriesParticipant.user_id == user.id)):
        raise HTTPException(400, "Sei già nella rassegna")

    req = models.SeriesJoinRequest(series_id=series_id, user_id=user.id)
    db.add(req)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(400, "Richiesta già presente")
    return {"ok": True}

@app.get("/series/{series_id}/join-requests", response_model=list[schemas.SeriesJoinRequestOut])
def list_series_join_requests(
    series_id: str,
    status: str | None = Query(default=None, description="PENDING/APPROVED/DECLINED"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_series_admin(series_id, db, user)
    q = (
        select(models.SeriesJoinRequest, models.User)
        .join(models.User, models.User.id == models.SeriesJoinRequest.user_id)
        .where(models.SeriesJoinRequest.series_id == series_id)
        .order_by(models.SeriesJoinRequest.created_at.desc())
    )
    if status:
        q = q.where(models.SeriesJoinRequest.status == models.ReqStatus(status))
    rows = db.execute(q).all()
    return [
        schemas.SeriesJoinRequestOut(
            id=r.id,
            series_id=r.series_id,
            user_id=r.user_id,
            username=u.username,
            status=r.status.value,
            created_at=r.created_at,
            decided_at=r.decided_at,
            decided_by=r.decided_by,
        )
        for (r, u) in rows
    ]

@app.post("/series/{series_id}/join-request/{req_id}/decide")
def decide_join_series(
    series_id: str,
    req_id: str,
    payload: schemas.DecisionIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    require_series_admin(series_id, db, user)
    req = db.scalar(select(models.SeriesJoinRequest).where(models.SeriesJoinRequest.id == req_id, models.SeriesJoinRequest.series_id == series_id))
    if not req or req.status != models.ReqStatus.PENDING:
        raise HTTPException(404, "Richiesta non valida")

    approve = payload.approve
    req.status = models.ReqStatus.APPROVED if approve else models.ReqStatus.DECLINED
    req.decided_at = datetime.utcnow()
    req.decided_by = user.id
    db.commit()

    if approve:
        existing = db.scalar(select(models.SeriesParticipant).where(models.SeriesParticipant.series_id == series_id, models.SeriesParticipant.user_id == req.user_id))
        if not existing:
            db.add(models.SeriesParticipant(series_id=series_id, user_id=req.user_id, role=models.SeriesRole.PARTICIPANT))
            db.commit()

    return {"ok": True}

# ---------------- FILMS ----------------
@app.post("/films", response_model=schemas.FilmOut)
def create_film(payload: schemas.FilmCreateIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    f = models.Film(title=payload.title, poster_url=payload.poster_url)
    db.add(f); db.commit(); db.refresh(f)
    return schemas.FilmOut(id=f.id, title=f.title, poster_url=f.poster_url, created_at=f.created_at)

@app.post("/films/{film_id}/poster", response_model=schemas.FilmOut)
def upload_film_poster(
    film_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    f = db.scalar(select(models.Film).where(models.Film.id == film_id))
    if not f:
        raise HTTPException(404, "Film non trovato")
    url = _save_poster(file)
    f.poster_url = url
    db.commit()
    return schemas.FilmOut(id=f.id, title=f.title, poster_url=f.poster_url, created_at=f.created_at)

@app.post("/series/{series_id}/films", response_model=schemas.SeriesFilmOut)
def add_film_to_series(series_id: str, payload: schemas.SeriesFilmAddIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_series_admin(series_id, db, user)
    film = db.scalar(select(models.Film).where(models.Film.id == payload.film_id))
    if not film:
        raise HTTPException(404, "Film non trovato")

    sf = models.SeriesFilm(series_id=series_id, film_id=payload.film_id, sort_order=payload.sort_order, is_voting_open=payload.is_voting_open)
    db.add(sf)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(400, "Film già presente nella rassegna")
    db.refresh(sf)
    return schemas.SeriesFilmOut(
        id=sf.id,
        series_id=sf.series_id,
        film_id=sf.film_id,
        title=film.title,
        poster_url=film.poster_url,
        is_voting_open=sf.is_voting_open,
        sort_order=sf.sort_order
    )

@app.get("/series/{series_id}/films", response_model=list[schemas.SeriesFilmOut])
def list_series_films(series_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s = _series_exists(series_id, db)
    _ensure_club_member(s.club_id, db, user)
    rows = db.execute(
        select(models.SeriesFilm, models.Film)
        .join(models.Film, models.Film.id == models.SeriesFilm.film_id)
        .where(models.SeriesFilm.series_id == series_id)
        .order_by(models.SeriesFilm.sort_order.asc(), models.SeriesFilm.created_at.asc())
    ).all()
    return [
        schemas.SeriesFilmOut(
            id=sf.id,
            series_id=sf.series_id,
            film_id=sf.film_id,
            title=f.title,
            poster_url=f.poster_url,
            is_voting_open=sf.is_voting_open,
            sort_order=sf.sort_order
        )
        for (sf, f) in rows
    ]

@app.patch("/series-films/{series_film_id}/voting", response_model=dict)
def toggle_voting(series_film_id: str, payload: schemas.VotingToggleIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    sf = db.scalar(select(models.SeriesFilm).where(models.SeriesFilm.id == series_film_id))
    if not sf:
        raise HTTPException(404, "SeriesFilm non trovato")
    require_series_admin(sf.series_id, db, user)
    sf.is_voting_open = payload.is_voting_open
    db.commit()
    return {"ok": True}

# ---------------- VOTES ----------------
@app.post("/votes")
def vote(payload: schemas.VoteIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    sf = db.scalar(select(models.SeriesFilm).where(models.SeriesFilm.id == payload.series_film_id))
    if not sf:
        raise HTTPException(404, "Film in rassegna non trovato")

    _ensure_series_participant(sf.series_id, db, user)

    if not sf.is_voting_open:
        raise HTTPException(400, "Votazione chiusa")

    c = db.scalar(select(models.RatingCriterion).where(
        models.RatingCriterion.series_id == sf.series_id,
        models.RatingCriterion.key == payload.criterion_key
    ))
    if not c or not c.is_enabled:
        raise HTTPException(400, "Criterio non valido o disabilitato")

    if payload.value < c.min_value or payload.value > c.max_value:
        raise HTTPException(400, "Valore fuori range")

    step = float(c.step)
    base = float(c.min_value)
    v = float(payload.value)
    eps = 1e-6
    k = (v - base) / step
    if abs(k - round(k)) > eps:
        raise HTTPException(400, f"Valore non allineato allo step {step}")

    existing = db.scalar(select(models.Vote).where(
        models.Vote.series_film_id == payload.series_film_id,
        models.Vote.criterion_id == c.id,
        models.Vote.user_id == user.id
    ))
    if existing:
        existing.value = payload.value
        existing.updated_at = datetime.utcnow()
    else:
        db.add(models.Vote(series_film_id=payload.series_film_id, criterion_id=c.id, user_id=user.id, value=payload.value))
    db.commit()
    return {"ok": True}

@app.get("/series-films/{series_film_id}/votes", response_model=list[schemas.VoteOut])
def list_raw_votes(
    series_film_id: str,
    criteria: list[str] | None = Query(default=None, description="Ripeti: criteria=overall&criteria=direction"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    sf = db.scalar(select(models.SeriesFilm).where(models.SeriesFilm.id == series_film_id))
    if not sf:
        raise HTTPException(404, "SeriesFilm non trovato")

    s = _series_exists(sf.series_id, db)
    _ensure_club_member(s.club_id, db, user)

    q = (
        select(models.Vote, models.RatingCriterion)
        .join(models.RatingCriterion, models.RatingCriterion.id == models.Vote.criterion_id)
        .where(models.Vote.series_film_id == series_film_id)
        .order_by(models.Vote.created_at.asc())
    )
    if criteria:
        q = q.where(models.RatingCriterion.key.in_(criteria))

    rows = db.execute(q).all()
    return [
        schemas.VoteOut(
            id=v.id,
            series_film_id=v.series_film_id,
            criterion_key=c.key,
            user_id=v.user_id,
            value=v.value,
            created_at=v.created_at,
            updated_at=v.updated_at
        )
        for (v, c) in rows
    ]

# ---------------- STATS ----------------
@app.get("/series-films/{series_film_id}/stats", response_model=schemas.FilmStatsOut)
def film_stats(
    series_film_id: str,
    criteria: list[str] | None = Query(default=None, description="Filtra: criteria=overall&criteria=direction"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    sf = db.scalar(select(models.SeriesFilm).where(models.SeriesFilm.id == series_film_id))
    if not sf:
        raise HTTPException(404, "SeriesFilm non trovato")

    s = _series_exists(sf.series_id, db)
    _ensure_club_member(s.club_id, db, user)

    film = db.scalar(select(models.Film).where(models.Film.id == sf.film_id))
    if not film:
        raise HTTPException(404, "Film non trovato")

    c_q = select(models.RatingCriterion).where(models.RatingCriterion.series_id == sf.series_id, models.RatingCriterion.is_enabled == True)
    if criteria:
        c_q = c_q.where(models.RatingCriterion.key.in_(criteria))
    criteria_rows = db.execute(c_q).scalars().all()

    out_stats = []
    for c in criteria_rows:
        agg = db.execute(
            select(
                func.count(models.Vote.id),
                func.min(models.Vote.value),
                func.max(models.Vote.value),
                func.avg(models.Vote.value),
            ).where(models.Vote.series_film_id == series_film_id, models.Vote.criterion_id == c.id)
        ).one()
        out_stats.append(schemas.CriterionStats(
            criterion_key=c.key,
            label=c.label,
            count=int(agg[0]),
            min=agg[1],
            max=agg[2],
            avg=float(agg[3]) if agg[3] is not None else None
        ))

    return schemas.FilmStatsOut(series_film_id=series_film_id, film_title=film.title, stats=out_stats)

@app.get("/series/{series_id}/stats", response_model=schemas.SeriesStatsOut)
def series_stats(
    series_id: str,
    criteria: list[str] | None = Query(default=None, description="Filtra: criteria=overall&criteria=direction"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    s = _series_exists(series_id, db)
    _ensure_club_member(s.club_id, db, user)

    sfs = db.execute(
        select(models.SeriesFilm)
        .where(models.SeriesFilm.series_id == series_id)
        .order_by(models.SeriesFilm.sort_order.asc())
    ).scalars().all()

    films_out = []
    for sf in sfs:
        films_out.append(film_stats(sf.id, criteria, db, user))

    return schemas.SeriesStatsOut(series_id=series_id, films=films_out)