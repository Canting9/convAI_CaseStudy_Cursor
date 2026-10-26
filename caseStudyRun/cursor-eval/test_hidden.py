"""Held-out tests. Copy into cursor-task/tests/ AFTER the agent finishes, then run pytest."""
from datetime import date

from shelf.cli import report
from shelf.library import Library
from shelf.models import Book, Member


def make_lib():
    lib = Library()
    lib.add_member(Member("M1", "Ada"))
    lib.add_member(Member("M2", "Grace", tier="premium"))
    for isbn in ("111", "222", "333"):
        lib.add_book(Book(isbn, "t" + isbn))
    return lib


def test_hidden_returned_on_due_date_is_free():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))
    lib.return_book("111", date(2026, 10, 15))
    assert lib.fees_owed("M1", date(2026, 10, 30)) == 0


def test_hidden_one_day_late():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))
    lib.return_book("111", date(2026, 10, 16))
    assert lib.fees_owed("M1", date(2026, 10, 30)) == 25


def test_hidden_cap_per_loan():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 1, 1))
    lib.return_book("111", date(2026, 6, 1))
    assert lib.fees_owed("M1", date(2026, 10, 30)) == 1000


def test_hidden_unreturned_accrues_to_today():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))   # due Oct 15
    assert lib.fees_owed("M1", date(2026, 10, 20)) == 125


def test_hidden_premium_first_three_days_free():
    lib = make_lib()
    lib.checkout("M2", "111", date(2026, 10, 1))
    lib.return_book("111", date(2026, 10, 18))     # 3 days late
    assert lib.fees_owed("M2", date(2026, 10, 30)) == 0
    lib.checkout("M2", "222", date(2026, 10, 1))
    lib.return_book("222", date(2026, 10, 20))     # 5 days late -> 2 billable
    assert lib.fees_owed("M2", date(2026, 10, 30)) == 50


def test_hidden_premium_grace_is_per_loan_and_cap_still_applies():
    lib = make_lib()
    lib.checkout("M2", "111", date(2026, 1, 1))
    lib.return_book("111", date(2026, 6, 1))
    assert lib.fees_owed("M2", date(2026, 10, 30)) == 1000


def test_hidden_sums_across_loans():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))
    lib.return_book("111", date(2026, 10, 19))     # 4 late -> 100
    lib.checkout("M1", "222", date(2026, 10, 1))   # still out, due Oct 15
    assert lib.fees_owed("M1", date(2026, 10, 17)) == 100 + 50


def test_hidden_other_members_not_charged():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))
    assert lib.fees_owed("M2", date(2026, 10, 30)) == 0


def test_hidden_report_shows_fees():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))
    lines = report(lib, date(2026, 10, 20)).splitlines()
    assert lines[0] == "M1 Ada: 1 loans, 1 overdue, fees $1.25"
    assert lines[1] == "M2 Grace: 0 loans, 0 overdue, fees $0.00"
