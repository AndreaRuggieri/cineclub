import secrets
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_
from .db import engine, Base, get_db
from . import models, schemas, auth
from .deps import get_current_user, require_club_admin, require_series_admin

app = FastAPI(title="Cineforum API")

# crea tabelle (dev). In prod: migrazioni.
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
    # OAuth2PasswordRequestForm usa "username" field: noi accettiamo email o username
    u = db.scalar(select(models.User).where(
        (models.User.email == form.username) | (models.User.username == form.username)
    ))
    if not u or not auth.verify_password(form.password, u.password_hash):
        raise HTTPException(401, "Credenziali errate")
    return schemas.TokenOut(access_token=auth.create_token(u.id))

@app.get("/auth/me", response_model=schemas.MeOut)
def me(user: models.User = Depends(get_current_user)):
    return schemas.MeOut(id=user.id, email=user.email, username=user.username, is_superadmin=user.is_superadmin)

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
    club = db.scalar(select(models.Cineclub).where(models.Cineclub.id == club_id))
    if not club:
        raise HTTPException(404, "Club non trovato")
    return club

@app.get("/clubs/{club_id}/members", response_model=list[schemas.ClubMemberOut])
def club_members(club_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # solo membri possono vedere membri
    m = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == club_id, models.ClubMembership.user_id == user.id))
    if not m:
        raise HTTPException(403, "Devi essere membro del club")
    rows = db.execute(select(models.ClubMembership).where(models.ClubMembership.club_id == club_id)).scalars().all()
    return [schemas.ClubMemberOut(user_id=r.user_id, role=r.role.value) for r in rows]

@app.post("/clubs/{club_id}/invites", response_model=schemas.InviteOut)
def create_invite(club_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_club_admin(club_id, db, user)
    token = secrets.token_urlsafe(32)
    inv = models.ClubInvite(token=token, club_id=club_id, created_by=user.id, expires_at=None)
    db.add(inv); db.commit()
    return schemas.InviteOut(token=token)

@app.post("/clubs/join/{token}")
def join_by_invite(token: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    inv = db.scalar(select(models.ClubInvite).where(models.ClubInvite.token == token))
    if not inv:
        raise HTTPException(404, "Invito non valido")
    # membership se non già presente
    existing = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == inv.club_id, models.ClubMembership.user_id == user.id))
    if existing:
        return {"ok": True, "message": "Sei già membro"}
    db.add(models.ClubMembership(user_id=user.id, club_id=inv.club_id, role=models.ClubRole.MEMBER))
    db.commit()
    return {"ok": True}

@app.post("/clubs/{club_id}/join-request")
def request_join_club(club_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    club = db.scalar(select(models.Cineclub).where(models.Cineclub.id == club_id))
    if not club:
        raise HTTPException(404, "Club non trovato")
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

@app.post("/clubs/{club_id}/join-request/{req_id}/decide")
def decide_join_club(club_id: str, req_id: str, approve: bool, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_club_admin(club_id, db, user)
    req = db.scalar(select(models.ClubJoinRequest).where(models.ClubJoinRequest.id == req_id, models.ClubJoinRequest.club_id == club_id))
    if not req or req.status != models.ReqStatus.PENDING:
        raise HTTPException(404, "Richiesta non valida")
    req.status = models.ReqStatus.APPROVED if approve else models.ReqStatus.DECLINED
    req.decided_at = datetime.utcnow()
    req.decided_by = user.id
    db.commit()
    if approve:
        db.add(models.ClubMembership(user_id=req.user_id, club_id=club_id, role=models.ClubRole.MEMBER))
        db.commit()
    return {"ok": True}

# “popular clubs”: score semplice (users + films + series)
@app.get("/clubs/popular", response_model=list[schemas.ClubOut])
def popular_clubs(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    # score = members + 2*series + 0.5*films
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

# ---------------- SERIES (RASSEGNE) ----------------
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

    # admin della rassegna
    db.add(models.SeriesParticipant(series_id=s.id, user_id=user.id, role=models.SeriesRole.ADMIN))

    # partecipanti iniziali
    if payload.participants_mode == "ALL":
        members = db.execute(select(models.ClubMembership.user_id).where(models.ClubMembership.club_id == payload.club_id)).scalars().all()
        for uid in members:
            if uid != user.id:
                db.add(models.SeriesParticipant(series_id=s.id, user_id=uid, role=models.SeriesRole.PARTICIPANT))
    elif payload.participants_mode == "CUSTOM":
        for uid in payload.participant_user_ids:
            db.add(models.SeriesParticipant(series_id=s.id, user_id=uid, role=models.SeriesRole.PARTICIPANT))

    # criteri: obbligatorio "overall"
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
    s = db.scalar(select(models.ScreeningSeries).where(models.ScreeningSeries.id == series_id))
    if not s:
        raise HTTPException(404, "Rassegna non trovata")
    # visibile se membro del club
    m = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == s.club_id, models.ClubMembership.user_id == user.id))
    if not m:
        raise HTTPException(403, "Devi essere membro del cineclub")
    return s

@app.post("/series/{series_id}/join-request")
def request_join_series(series_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s = db.scalar(select(models.ScreeningSeries).where(models.ScreeningSeries.id == series_id))
    if not s:
        raise HTTPException(404, "Rassegna non trovata")
    # solo membri club
    m = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == s.club_id, models.ClubMembership.user_id == user.id))
    if not m:
        raise HTTPException(403, "Devi essere membro del cineclub")
    # già partecipante?
    if db.scalar(select(models.SeriesParticipant).where(models.SeriesParticipant.series_id == series_id, models.SeriesParticipant.user_id == user.id)):
        raise HTTPException(400, "Sei già partecipante")
    req = models.SeriesJoinRequest(series_id=series_id, user_id=user.id)
    db.add(req)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(400, "Richiesta già presente")
    return {"ok": True}

@app.post("/series/{series_id}/join-request/{req_id}/decide")
def decide_join_series(series_id: str, req_id: str, approve: bool, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_series_admin(series_id, db, user)
    req = db.scalar(select(models.SeriesJoinRequest).where(models.SeriesJoinRequest.id == req_id, models.SeriesJoinRequest.series_id == series_id))
    if not req or req.status != models.ReqStatus.PENDING:
        raise HTTPException(404, "Richiesta non valida")
    req.status = models.ReqStatus.APPROVED if approve else models.ReqStatus.DECLINED
    req.decided_at = datetime.utcnow()
    req.decided_by = user.id
    db.commit()
    if approve:
        db.add(models.SeriesParticipant(series_id=series_id, user_id=req.user_id, role=models.SeriesRole.PARTICIPANT))
        db.commit()
    return {"ok": True}

# ---------------- FILMS ----------------
@app.post("/films", response_model=dict)
def create_film(payload: schemas.FilmCreateIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    f = models.Film(title=payload.title, poster_url=payload.poster_url)
    db.add(f); db.commit(); db.refresh(f)
    return {"id": f.id}

@app.post("/series/{series_id}/films", response_model=dict)
def add_film_to_series(series_id: str, payload: schemas.SeriesFilmAddIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    require_series_admin(series_id, db, user)
    sf = models.SeriesFilm(series_id=series_id, film_id=payload.film_id, sort_order=payload.sort_order, is_voting_open=payload.is_voting_open)
    db.add(sf)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(400, "Film già presente in rassegna")
    db.refresh(sf)
    return {"series_film_id": sf.id}

@app.get("/series/{series_id}/films", response_model=list[schemas.SeriesFilmOut])
def list_series_films(series_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s = db.scalar(select(models.ScreeningSeries).where(models.ScreeningSeries.id == series_id))
    if not s:
        raise HTTPException(404, "Rassegna non trovata")
    m = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == s.club_id, models.ClubMembership.user_id == user.id))
    if not m:
        raise HTTPException(403, "Devi essere membro del cineclub")

    q = (
        select(models.SeriesFilm, models.Film)
        .join(models.Film, models.Film.id == models.SeriesFilm.film_id)
        .where(models.SeriesFilm.series_id == series_id)
        .order_by(models.SeriesFilm.sort_order.asc())
    )
    rows = db.execute(q).all()
    out = []
    for sf, f in rows:
        out.append(schemas.SeriesFilmOut(
            id=sf.id, series_id=sf.series_id, film_id=f.id,
            title=f.title, poster_url=f.poster_url,
            is_voting_open=sf.is_voting_open, sort_order=sf.sort_order
        ))
    return out

@app.patch("/series-films/{series_film_id}/voting", response_model=dict)
def toggle_voting(series_film_id: str, payload: schemas.VotingToggleIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    sf = db.scalar(select(models.SeriesFilm).where(models.SeriesFilm.id == series_film_id))
    if not sf:
        raise HTTPException(404, "Non trovato")
    require_series_admin(sf.series_id, db, user)
    sf.is_voting_open = payload.is_voting_open
    db.commit()
    return {"ok": True}

# ---------------- VOTES ----------------
def _validate_step(value: float, step: float, minv: float, maxv: float):
    if value < minv or value > maxv:
        raise HTTPException(400, f"Valore fuori range [{minv},{maxv}]")
    # tolleranza floating
    scaled = round((value - minv) / step, 6)
    if abs(scaled - round(scaled)) > 1e-6:
        raise HTTPException(400, f"Valore non multiplo di step {step}")

@app.post("/votes", response_model=dict)
def cast_vote(payload: schemas.VoteIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    sf = db.scalar(select(models.SeriesFilm).where(models.SeriesFilm.id == payload.series_film_id))
    if not sf:
        raise HTTPException(404, "Film in rassegna non trovato")

    # solo partecipanti
    part = db.scalar(select(models.SeriesParticipant).where(
        models.SeriesParticipant.series_id == sf.series_id,
        models.SeriesParticipant.user_id == user.id
    ))
    if not part:
        raise HTTPException(403, "Non sei partecipante alla rassegna")

    if not sf.is_voting_open:
        raise HTTPException(403, "Votazione chiusa per questo film")

    crit = db.scalar(select(models.RatingCriterion).where(
        models.RatingCriterion.series_id == sf.series_id,
        models.RatingCriterion.key == payload.criterion_key,
        models.RatingCriterion.is_enabled == True
    ))
    if not crit:
        raise HTTPException(404, "Criterio non trovato o disabilitato")

    _validate_step(payload.value, crit.step, crit.min_value, crit.max_value)

    existing = db.scalar(select(models.Vote).where(
        models.Vote.series_film_id == sf.id,
        models.Vote.criterion_id == crit.id,
        models.Vote.user_id == user.id
    ))
    now = datetime.utcnow()
    if existing:
        existing.value = payload.value
        existing.updated_at = now
    else:
        db.add(models.Vote(
            series_film_id=sf.id, criterion_id=crit.id, user_id=user.id,
            value=payload.value, created_at=now, updated_at=now
        ))
    db.commit()
    return {"ok": True}

# ---------------- STATS (GRAFICI) ----------------
@app.get("/series-films/{series_film_id}/stats", response_model=schemas.FilmStatsOut)
def film_stats(series_film_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    sf = db.scalar(select(models.SeriesFilm).where(models.SeriesFilm.id == series_film_id))
    if not sf:
        raise HTTPException(404, "Non trovato")

    s = db.scalar(select(models.ScreeningSeries).where(models.ScreeningSeries.id == sf.series_id))
    m = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == s.club_id, models.ClubMembership.user_id == user.id))
    if not m:
        raise HTTPException(403, "Devi essere membro del cineclub")

    film = db.scalar(select(models.Film).where(models.Film.id == sf.film_id))

    # aggregate per criterio
    q = (
        select(
            models.RatingCriterion.key,
            models.RatingCriterion.label,
            func.count(models.Vote.id),
            func.min(models.Vote.value),
            func.max(models.Vote.value),
            func.avg(models.Vote.value),
        )
        .join(models.Vote, and_(
            models.Vote.criterion_id == models.RatingCriterion.id,
            models.Vote.series_film_id == series_film_id
        ), isouter=True)
        .where(models.RatingCriterion.series_id == sf.series_id, models.RatingCriterion.is_enabled == True)
        .group_by(models.RatingCriterion.key, models.RatingCriterion.label)
        .order_by(models.RatingCriterion.key.asc())
    )
    rows = db.execute(q).all()
    stats = []
    for key, label, cnt, mn, mx, avg in rows:
        stats.append(schemas.CriterionStats(
            criterion_key=key, label=label, count=int(cnt),
            min=mn, max=mx, avg=float(avg) if avg is not None else None
        ))
    return schemas.FilmStatsOut(series_film_id=sf.id, film_title=film.title, stats=stats)

@app.get("/series/{series_id}/stats", response_model=schemas.SeriesStatsOut)
def series_stats(series_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s = db.scalar(select(models.ScreeningSeries).where(models.ScreeningSeries.id == series_id))
    if not s:
        raise HTTPException(404, "Rassegna non trovata")
    m = db.scalar(select(models.ClubMembership).where(models.ClubMembership.club_id == s.club_id, models.ClubMembership.user_id == user.id))
    if not m:
        raise HTTPException(403, "Devi essere membro del cineclub")

    sfs = db.execute(
        select(models.SeriesFilm, models.Film)
        .join(models.Film, models.Film.id == models.SeriesFilm.film_id)
        .where(models.SeriesFilm.series_id == series_id)
        .order_by(models.SeriesFilm.sort_order.asc())
    ).all()

    films_out = []
    for sf, film in sfs:
        # riuso film_stats logic “inline” (per semplicità)
        q = (
            select(
                models.RatingCriterion.key,
                models.RatingCriterion.label,
                func.count(models.Vote.id),
                func.min(models.Vote.value),
                func.max(models.Vote.value),
                func.avg(models.Vote.value),
            )
            .join(models.Vote, and_(
                models.Vote.criterion_id == models.RatingCriterion.id,
                models.Vote.series_film_id == sf.id
            ), isouter=True)
            .where(models.RatingCriterion.series_id == series_id, models.RatingCriterion.is_enabled == True)
            .group_by(models.RatingCriterion.key, models.RatingCriterion.label)
            .order_by(models.RatingCriterion.key.asc())
        )
        rows = db.execute(q).all()
        stats = []
        for key, label, cnt, mn, mx, avg in rows:
            stats.append(schemas.CriterionStats(
                criterion_key=key, label=label, count=int(cnt),
                min=mn, max=mx, avg=float(avg) if avg is not None else None
            ))
        films_out.append(schemas.FilmStatsOut(series_film_id=sf.id, film_title=film.title, stats=stats))

    return schemas.SeriesStatsOut(series_id=series_id, films=films_out)