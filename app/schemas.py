from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import TicketStatus, TicketVisibility, UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    role: UserRole

    model_config = ConfigDict(from_attributes=True)


class TicketCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10)
    priority: str = "medium"
    visibility: TicketVisibility = TicketVisibility.internal
    tags: list[str] = Field(default_factory=list)
    assigned_to_id: str | None = None


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    message: str = Field(default="Status updated by API")


class TicketAssign(BaseModel):
    assigned_to_id: str
    message: str = Field(default="Ticket assignment updated")


class TicketEventResponse(BaseModel):
    id: int
    event_type: str
    message: str
    previous_value: str | None = None
    new_value: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketResponse(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    status: TicketStatus
    visibility: TicketVisibility
    tags: list[str]
    created_by_id: str
    assigned_to_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketDetailResponse(TicketResponse):
    events: list[TicketEventResponse] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    database: str | None = None
    redis: str | None = None
    worker_mode: str | None = None
