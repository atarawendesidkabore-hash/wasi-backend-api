"""Pydantic schemas for eCFA CBDC wallet operations."""
from datetime import datetime
from pydantic import BaseModel, Field


class WalletCreateRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2, description="ISO-2 country code")
    wallet_type: str = Field(
        default="RETAIL",
        description="CENTRAL_BANK | COMMERCIAL_BANK | AGENT | MERCHANT | RETAIL",
    )
    phone_hash: str | None = Field(None, description="SHA-256 of phone number (USSD users)")
    institution_code: str | None = Field(None, description="BIC/SWIFT for banks")
    institution_name: str | None = Field(None, description="Institution display name")
    pin: str | None = Field(None, min_length=4, max_length=6, description="4-6 digit PIN for USSD")


class WalletCreateResponse(BaseModel):
    wallet_id: str
    wallet_type: str
    country_code: str
    kyc_tier: int
    daily_limit_ecfa: float
    balance_limit_ecfa: float
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WalletBalanceResponse(BaseModel):
    wallet_id: str
    balance_ecfa: float
    available_balance_ecfa: float
    hold_amount_ecfa: float
    ledger_verified_balance: float
    balance_matches_ledger: bool
    kyc_tier: int
    daily_limit_ecfa: float
    daily_spent_ecfa: float
    status: str


class WalletFreezeRequest(BaseModel):
    admin_wallet_id: str = Field(..., description="Wallet ID of the admin performing the freeze")
    target_wallet_id: str = Field(..., description="Wallet to freeze")
    reason: str = Field(..., min_length=5, description="Reason for freezing")


class WalletFreezeResponse(BaseModel):
    wallet_id: str
    status: str
    reason: str | None = None
    frozen_at: str | None = None


class WalletInfoResponse(BaseModel):
    wallet_id: str
    wallet_type: str
    country_code: str
    kyc_tier: int
    balance_ecfa: float
    available_balance_ecfa: float
    status: str
    daily_limit_ecfa: float
    balance_limit_ecfa: float
    has_pin: bool
    has_public_key: bool
    created_at: datetime
    last_activity_at: datetime | None

    model_config = {"from_attributes": True}


class SetPinRequest(BaseModel):
    wallet_id: str
    new_pin: str = Field(..., min_length=4, max_length=6, pattern=r"^\d{4,6}$")


class SetPinResponse(BaseModel):
    wallet_id: str
    message: str
