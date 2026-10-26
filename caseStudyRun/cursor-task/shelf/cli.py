import argparse
import json
from datetime import date
from typing import List, Optional

from .library import Library
from .models import Book, Member


def load(path: str) -> Library:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    lib = Library()
    for m in data["members"]:
        lib.add_member(Member(m["id"], m["name"], m.get("tier", "standard")))
    for b in data["books"]:
        lib.add_book(Book(b["isbn"], b["title"]))
    for loan in data["loans"]:
        lib.checkout(loan["member"], loan["isbn"], date.fromisoformat(loan["checked_out"]))
        if loan.get("returned"):
            lib.return_book(loan["isbn"], date.fromisoformat(loan["returned"]))
    return lib


def report(lib: Library, today: date) -> str:
    overdue = lib.overdue(today)
    lines = []
    for member in lib.members.values():
        loans = lib.loans_for(member.id)
        late = [loan for loan in overdue if loan.member_id == member.id]
        lines.append(f"{member.id} {member.name}: {len(loans)} loans, {len(late)} overdue")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="shelf")
    parser.add_argument("--data", default="data/sample.json")
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args(argv)
    lib = load(args.data)
    print(report(lib, date.fromisoformat(args.today)))


if __name__ == "__main__":
    main()
