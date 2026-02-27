import re
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from datetime import datetime


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("username")
    @classmethod
    def username_must_be_safe(cls, v: str) -> str:
        if re.search(r"[<>&\"'/;]", v):
            raise ValueError("Username contains forbidden characters")
        if not re.match(r"^[a-zA-Z0-9_.\-]+$", v):
            raise ValueError("Username must only contain letters, digits, underscores, dots, or hyphens")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    x402_balance: float
    tier: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
