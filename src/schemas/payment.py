from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class TopupRequest(BaseModel):
    amount: float = Field(gt=0, le=10000)
    reference_id: str = Field(min_length=6, max_length=100)


class TransactionResponse(BaseModel):
    id: int
    transaction_type: str
    amount: float
    balance_before: float
    balance_after: float
    reference_id: Optional[str] = None
    description: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentStatusResponse(BaseModel):
    user_id: int
    balance: float
    tier: str
    recent_transactions: list[TransactionResponse]
