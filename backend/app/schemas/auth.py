from typing import Optional

from pydantic import BaseModel


# ── User ──
class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "client"
    country_id: Optional[int] = None
    language: str = "en"


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    country_id: Optional[int] = None
    language: str
    is_active: bool

    model_config = {"from_attributes": True}


# ── Auth ──
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginRequest(BaseModel):
    email: str
    password: str
