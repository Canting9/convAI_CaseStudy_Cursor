from datetime import date

import pytest

from shelf.cli import report
from shelf.library import Library, LibraryError
from shelf.models import Book, Member


def make_lib():
    lib = Library()
    lib.add_member(Member("M1", "Ada"))
    lib.add_member(Member("M2", "Grace", tier="premium"))
    lib.add_book(Book("111", "Dune"))
    lib.add_book(Book("222", "Neuromancer"))
    return lib


def test_checkout_sets_due_date():
    lib = make_lib()
    loan = lib.checkout("M1", "111", date(2026, 10, 1))
    assert loan.due == date(2026, 10, 15)


def test_cannot_double_checkout():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))
    with pytest.raises(LibraryError):
        lib.checkout("M2", "111", date(2026, 10, 2))


def test_overdue():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))
    assert lib.overdue(date(2026, 10, 15)) == []
    assert len(lib.overdue(date(2026, 10, 16))) == 1


def test_report_counts():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))
    out = report(lib, date(2026, 10, 20))
    assert out.splitlines()[0].startswith("M1 Ada: 1 loans, 1 overdue")


def test_fee_for_late_return():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))   # due Oct 15
    lib.return_book("111", date(2026, 10, 19))     # 4 days late
    assert lib.fees_owed("M1", date(2026, 10, 25)) == 100


def test_no_fee_when_on_time():
    lib = make_lib()
    lib.checkout("M1", "111", date(2026, 10, 1))
    lib.return_book("111", date(2026, 10, 10))
    assert lib.fees_owed("M1", date(2026, 10, 25)) == 0
