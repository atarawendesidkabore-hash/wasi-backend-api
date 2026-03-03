"""Pydantic schemas for eCFA CBDC transaction operations."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

ALLOWED_TX_TYPES = Literal[
    "TRANSFER_P2P", "MERCHANT_PAYMENT", "CASH_IN", "CASH_OUT",
    "BILL_PAYMENT", "SALARY", "GOV_DISBURSEMENT",
]
ALLOWED_CHANNELS = Literal["API", "USSD"]


class TransferRequest(BaseModel):
    sender_wallet_id: str
    receiver_wallet_id: str
    amount_ecfa: float = Field(..., gt=0, description="Amount in eCFA (= XOF)")
    tx_type: ALLOWED_TX_TYPES = Field(default="TRANSFER_P2P", description="Transaction type")
    channel: ALLOWED_CHANNELS = Field(default="API", description="API | USSD")
    pin: str | None = Field(None, min_length=4, max_length=6, description="4-6 digit PIN (for USSD)")
    signature: str | None = Field(None, description="ED25519 signature hex (for API)")
    nonce: str | None = Field(None, description="Client-generated nonce included in signature")
    policy_id: int | None = Field(None, description="Programmable money policy ID")
    spending_category: str | None = Field(None, description="FOOD | HEALTH | EDUCATION | ANY")
    memo: str | None = Field(None, max_length=500)
    fee_ecfa: float = Field(default=0.0, ge=0)


class TransferResponse(BaseModel):
    transaction_id: str
    status: str
    amount_ecfa: float
    fee_ecfa: float
    sender_wallet_id: str
    receiver_wallet_id: str
    is_cross_border: bool


class MintRequest(BaseModel):
    central_bank_wallet_id: str
    target_wallet_id: str
    amount_ecfa: float = Field(..., gt=0)
    reference: str = Field(..., min_length=3, description="Issuance reference")
    memo: str | None = None


class MintResponse(BaseModel):
    transaction_id: str
    status: str
    amount_ecfa: float
    target_wallet_id: str
    target_new_balance: float


class BurnRequest(BaseModel):
    central_bank_wallet_id: str
    source_wallet_id: str
    amount_ecfa: float = Field(..., gt=0)
    reference: str = Field(..., min_length=3)


class BurnResponse(BaseModel):
    transaction_id: str
    status: str
    amount_ecfa: float
    source_wallet_id: str
    source_new_balance: float


class TransactionStatusResponse(BaseModel):
    transaction_id: str
    tx_type: str
    status: str
    amount_ecfa: float
    fee_ecfa: float
    total_ecfa: float
    sender_wallet_id: str | None
    receiver_wallet_id: str | None
    is_cross_border: bool
    aml_status: str
    channel: str
    cobol_ref: str | None
    initiated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class TransactionHistoryItem(BaseModel):
    transaction_id: str
    tx_type: str
    status: str
    amount_ecfa: float
    fee_ecfa: float
    counterparty_wallet_id: str | None
    direction: str  # SENT | RECEIVED
    channel: str
    initiated_at: datetime


class TransactionHistoryResponse(BaseModel):
    wallet_id: str
    transactions: list[TransactionHistoryItem]
    total_count: int
    page: int
    page_size: int
