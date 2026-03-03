import re
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from datetime import datetime

# Institutional terms that cannot appear in usernames (prevent impersonation)
_RESERVED_WORDS = {
    "bceao", "imf", "worldbank", "world_bank", "ministry", "minister",
    "governor", "official", "admin", "central_bank", "centralbank",
    "president", "directeur", "ecowas", "cedeao", "uemoa", "waemu",
    "regulator", "compliance", "auditor", "treasury", "tresor",
}


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
        # Block institutional impersonation
        lower = v.lower()
        for word in _RESERVED_WORDS:
            if word in lower:
                raise ValueError("Username contains reserved institutional terms")
        return v

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit")
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
