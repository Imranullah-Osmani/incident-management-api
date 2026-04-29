from __future__ import annotations

import socket
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Ticket, TicketEvent, TicketStatus, TicketVisibility, User, UserRole
from app.schemas import (
    HealthResponse,
    LoginRequest,
    TicketAssign,
    TicketCreate,
    TicketDetailResponse,
    TicketResponse,
    TicketStatusUpdate,
    TokenResponse,
    UserResponse,
)
from app.security import create_access_token, decode_access_token, hash_password, verify_password
from app.tasks import notify_ticket_change


app = FastAPI(title=settings.app_name, version="0.1.0")
security = HTTPBearer()
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def seed_demo_users(session: Session) -> None:
    demo_users = [
        {"full_name": "System Admin", "email": "admin@example.com", "role": UserRole.admin},
        {"full_name": "Support Agent", "email": "agent@example.com", "role": UserRole.agent},
        {"full_name": "Reporting User", "email": "reporter@example.com", "role": UserRole.reporter},
    ]

    for demo_user in demo_users:
        user = session.scalar(select(User).where(User.email == demo_user["email"]))
        if user:
            user.full_name = demo_user["full_name"]
            user.role = demo_user["role"]
            user.is_active = True
            user.hashed_password = hash_password("ChangeMe123!")
            continue

        session.add(
            User(
                full_name=demo_user["full_name"],
                email=demo_user["email"],
                role=demo_user["role"],
                hashed_password=hash_password("ChangeMe123!"),
            )
        )
    session.commit()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_demo_users(session)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_db),
) -> User:
    try:
        subject = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.") from exc
    user = session.scalar(select(User).where(User.id == subject))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials.")
    return user


def ensure_agent_or_admin(user: User) -> None:
    if user.role not in {UserRole.admin, UserRole.agent}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action requires an agent or admin.")


def visible_ticket_query(session: Session, user: User):
    statement = select(Ticket).options(selectinload(Ticket.events)).order_by(Ticket.updated_at.desc())
    if user.role == UserRole.admin:
        return statement
    if user.role == UserRole.agent:
        return statement.where(
            (Ticket.visibility != TicketVisibility.restricted)
            | (Ticket.assigned_to_id == user.id)
            | (Ticket.created_by_id == user.id)
        )
    return statement.where(Ticket.created_by_id == user.id)


def get_visible_ticket(session: Session, user: User, ticket_id: str) -> Ticket:
    ticket = session.scalar(visible_ticket_query(session, user).where(Ticket.id == ticket_id))
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
    return ticket


def append_event(
    session: Session,
    ticket: Ticket,
    actor: User,
    event_type: str,
    message: str,
    previous_value: str | None = None,
    new_value: str | None = None,
) -> None:
    session.add(
        TicketEvent(
            ticket_id=ticket.id,
            actor_id=actor.id,
            event_type=event_type,
            message=message,
            previous_value=previous_value,
            new_value=new_value,
        )
    )


def get_assignable_user(session: Session, assigned_to_id: str) -> User:
    assignee = session.scalar(select(User).where(User.id == assigned_to_id))
    if not assignee or not assignee.is_active or assignee.role not in {UserRole.admin, UserRole.agent}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assigned user must be an active agent or admin.")
    return assignee


def enqueue_notification(event_type: str, ticket_id: str, recipient: str | None = None) -> None:
    broker = urlparse(settings.redis_url)
    host = broker.hostname
    port = broker.port or 6379
    if not host:
        return
    try:
        with socket.create_connection((host, port), timeout=0.35):
            pass
    except OSError:
        return

    try:
        notify_ticket_change.delay(event_type, ticket_id, recipient)
    except Exception:
        # The API should still complete when Redis/Celery is unavailable in local dev mode.
        return


@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "request": request,
            "demo_accounts": [
                {"email": "admin@example.com", "password": "ChangeMe123!", "role": "admin"},
                {"email": "agent@example.com", "password": "ChangeMe123!", "role": "agent"},
                {"email": "reporter@example.com", "password": "ChangeMe123!", "role": "reporter"},
            ],
            "endpoints": [
                {"method": "POST", "path": "/auth/login", "summary": "Issue a JWT for the incident console."},
                {"method": "GET", "path": "/tickets", "summary": "List tickets visible to the authenticated role."},
                {"method": "POST", "path": "/tickets", "summary": "Create a new support or incident record."},
                {"method": "PATCH", "path": "/tickets/{ticket_id}/status", "summary": "Move the incident through its lifecycle."},
                {"method": "GET", "path": "/health/ready", "summary": "Check database, Redis, and worker readiness."},
            ],
        },
    )


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_db)) -> TokenResponse:
    user = session.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    return TokenResponse(access_token=create_access_token(user.id))


@app.get("/demo/users", response_model=list[UserResponse])
def demo_users(session: Session = Depends(get_db)):
    return list(session.scalars(select(User).order_by(User.role, User.email)))


@app.get("/tickets", response_model=list[TicketResponse])
def list_tickets(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list(session.scalars(visible_ticket_query(session, current_user)))


@app.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.assigned_to_id:
        get_assignable_user(session, payload.assigned_to_id)

    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        visibility=payload.visibility,
        tags=payload.tags,
        created_by_id=current_user.id,
        assigned_to_id=payload.assigned_to_id,
    )
    session.add(ticket)
    session.flush()
    append_event(session, ticket, current_user, "ticket_created", "Ticket created")
    session.commit()
    session.refresh(ticket)
    enqueue_notification("ticket_created", ticket.id, None)
    return ticket


@app.get("/tickets/{ticket_id}", response_model=TicketDetailResponse)
def get_ticket(
    ticket_id: str,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_visible_ticket(session, current_user, ticket_id)


@app.patch("/tickets/{ticket_id}/status", response_model=TicketDetailResponse)
def update_ticket_status(
    ticket_id: str,
    payload: TicketStatusUpdate,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_agent_or_admin(current_user)
    ticket = get_visible_ticket(session, current_user, ticket_id)
    previous_status = ticket.status.value
    ticket.status = payload.status
    append_event(session, ticket, current_user, "status_changed", payload.message, previous_status, payload.status.value)
    session.commit()
    enqueue_notification("status_changed", ticket.id, ticket.created_by_id)
    return get_visible_ticket(session, current_user, ticket.id)


@app.patch("/tickets/{ticket_id}/assign", response_model=TicketDetailResponse)
def assign_ticket(
    ticket_id: str,
    payload: TicketAssign,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_agent_or_admin(current_user)
    ticket = get_visible_ticket(session, current_user, ticket_id)
    get_assignable_user(session, payload.assigned_to_id)
    previous_assignee = ticket.assigned_to_id
    ticket.assigned_to_id = payload.assigned_to_id
    append_event(session, ticket, current_user, "assignment_changed", payload.message, previous_assignee, payload.assigned_to_id)
    session.commit()
    enqueue_notification("assignment_changed", ticket.id, payload.assigned_to_id)
    return get_visible_ticket(session, current_user, ticket.id)


@app.get("/health/live", response_model=HealthResponse)
def live_health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/health/ready", response_model=HealthResponse)
def ready_health(session: Session = Depends(get_db)) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        database_status = "error"

    try:
        redis_client = Redis.from_url(settings.redis_url)
        redis_client.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    worker_mode = "eager" if settings.celery_task_always_eager else "brokered"
    overall = "ok" if database_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(status=overall, database=database_status, redis=redis_status, worker_mode=worker_mode)
