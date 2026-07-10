from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    visibility: TicketVisibility = TicketVisibility.internal
    tags: list[str] = Field(default_factory=list)
    assigned_to_id: str | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("assigned_to_id", mode="before")
    @classmethod
    def strip_assigned_to_id(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value
        return value.strip() or None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for tag in value:
            clean_tag = tag.strip().lower()
            if clean_tag and clean_tag not in seen:
                normalized.append(clean_tag)
                seen.add(clean_tag)
        return normalized


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    message: str = Field(default="Status updated by API", min_length=3, max_length=255)

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class TicketAssign(BaseModel):
    assigned_to_id: str = Field(min_length=1)
    message: str = Field(default="Ticket assignment updated", min_length=3, max_length=255)

    @field_validator("assigned_to_id", mode="before")
    @classmethod
    def strip_assigned_to_id(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


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


class TicketSummaryResponse(BaseModel):
    visible_total: int
    assigned_total: int
    unassigned_total: int
    status_counts: dict[str, int]
    priority_counts: dict[str, int]


class HealthResponse(BaseModel):
    status: str
    database: str | None = None
    redis: str | None = None
    worker_mode: str | None = None
