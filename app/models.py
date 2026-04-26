from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class UserRole(str, enum.Enum):
    admin = "admin"
    agent = "agent"
    reporter = "reporter"


class TicketStatus(str, enum.Enum):
    new = "new"
    acknowledged = "acknowledged"
    investigating = "investigating"
    resolved = "resolved"
    closed = "closed"


class TicketVisibility(str, enum.Enum):
    public = "public"
    internal = "internal"
    restricted = "restricted"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    created_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="created_by",
        foreign_keys="Ticket.created_by_id",
    )
    assigned_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="assigned_to",
        foreign_keys="Ticket.assigned_to_id",
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(50), default="medium")
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.new, index=True)
    visibility: Mapped[TicketVisibility] = mapped_column(
        Enum(TicketVisibility),
        default=TicketVisibility.internal,
        index=True,
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    created_by: Mapped[User] = relationship(back_populates="created_tickets", foreign_keys=[created_by_id])
    assigned_to: Mapped[User | None] = relationship(back_populates="assigned_tickets", foreign_keys=[assigned_to_id])
    events: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(String(255))
    previous_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    ticket: Mapped[Ticket] = relationship(back_populates="events")
