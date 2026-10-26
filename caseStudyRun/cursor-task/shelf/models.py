from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Member:
    id: str
    name: str
    tier: str = "standard"  # "standard" or "premium"


@dataclass
class Book:
    isbn: str
    title: str


@dataclass
class Loan:
    member_id: str
    isbn: str
    checked_out: date
    due: date
    returned: Optional[date] = None
