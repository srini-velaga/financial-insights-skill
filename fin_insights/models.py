"""Data models for financial transactions."""

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
from uuid import uuid4


@dataclass
class Transaction:
    institution: str
    account_type: str  # 'credit_card' or 'checking'
    transaction_date: date
    description: str
    amount: float  # positive=expense/debit, negative=income/credit
    unified_category: str
    source_file: str
    id: str = field(default_factory=lambda: str(uuid4()))
    card_name: str | None = None
    post_date: date | None = None
    description_clean: str | None = None
    transaction_type: str | None = None  # 'purchase', 'payment', 'deposit', 'transfer', 'fee', 'refund'
    original_category: str | None = None
    unified_subcategory: str | None = None
    location: str | None = None

    def __post_init__(self):
        if self.description_clean is None:
            self.description_clean = self._clean_description(self.description)

    @staticmethod
    def _clean_description(desc: str) -> str:
        """Normalize description for dedup and matching."""
        return " ".join(desc.upper().split())

    @property
    def fingerprint(self) -> str:
        """SHA-256 fingerprint for deduplication."""
        raw = f"{self.transaction_date}|{self.amount:.2f}|{self.description_clean}|{self.institution}|{self.account_type}"
        return sha256(raw.encode()).hexdigest()
