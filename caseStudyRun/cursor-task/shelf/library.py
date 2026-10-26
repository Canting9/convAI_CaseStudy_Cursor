from datetime import date, timedelta
from typing import Dict, List, Optional

from .models import Book, Loan, Member

LOAN_DAYS = 14


class LibraryError(Exception):
    pass


class Library:
    def __init__(self) -> None:
        self.members: Dict[str, Member] = {}
        self.books: Dict[str, Book] = {}
        self.loans: List[Loan] = []

    def add_member(self, member: Member) -> None:
        self.members[member.id] = member

    def add_book(self, book: Book) -> None:
        self.books[book.isbn] = book

    def _active_loan(self, isbn: str) -> Optional[Loan]:
        for loan in self.loans:
            if loan.isbn == isbn and loan.returned is None:
                return loan
        return None

    def checkout(self, member_id: str, isbn: str, on: date) -> Loan:
        if member_id not in self.members:
            raise LibraryError(f"unknown member {member_id}")
        if isbn not in self.books:
            raise LibraryError(f"unknown book {isbn}")
        if self._active_loan(isbn) is not None:
            raise LibraryError(f"book {isbn} is already checked out")
        loan = Loan(member_id, isbn, on, on + timedelta(days=LOAN_DAYS))
        self.loans.append(loan)
        return loan

    def return_book(self, isbn: str, on: date) -> Loan:
        loan = self._active_loan(isbn)
        if loan is None:
            raise LibraryError(f"book {isbn} is not checked out")
        loan.returned = on
        return loan

    def loans_for(self, member_id: str) -> List[Loan]:
        return [loan for loan in self.loans if loan.member_id == member_id]

    def overdue(self, today: date) -> List[Loan]:
        return [
            loan for loan in self.loans
            if loan.returned is None and today > loan.due
        ]
