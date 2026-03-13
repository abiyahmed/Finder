#!/usr/bin/env python3
"""
Import GitHub tokens from a text file into the app's github_tokens table.
Format: one token per line, optional " - Description" after the token.
  ghp_xxxx... - Kirubel Ateka
  ghp_yyyy...
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Force real DB: do not use in-memory SQLite (TEST_MODE)
import os
os.environ.pop("TEST_MODE", None)

from src.infrastructure.database import init_db, add_github_token, engine

# Token prefix; rest is alphanumeric and underscore (GitHub PAT format)
TOKEN_LINE = re.compile(r"^(ghp_[A-Za-z0-9_]+|gho_[A-Za-z0-9_]+)\s*(?:-\s*(.*))?$", re.IGNORECASE)


def parse_token_lines(text: str) -> list[tuple[str, str | None]]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = TOKEN_LINE.match(line)
        if m:
            token, desc = m.group(1).strip(), m.group(2)
            desc = desc.strip() if desc else None
            out.append((token, desc or None))
        elif line.startswith("ghp_") or line.startswith("gho_"):
            out.append((line.strip(), None))
    return out


def main():
    parser = argparse.ArgumentParser(description="Import GitHub tokens into the database.")
    parser.add_argument("file", nargs="?", type=Path, help="Text file with tokens (one per line). Default: stdin.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be added, do not write to DB.")
    args = parser.parse_args()

    if args.file:
        content = args.file.read_text(encoding="utf-8", errors="replace")
    else:
        content = sys.stdin.read()

    pairs = parse_token_lines(content)
    if not pairs:
        print("No tokens found.")
        sys.exit(1)

    if args.dry_run:
        for token, desc in pairs:
            print(f"  {token[:20]}... -> {desc or '(no description)'}")
        print(f"Total: {len(pairs)} token(s). Run without --dry-run to import.")
        return

    # Show which DB we're using (redact password)
    u = engine.url
    if u.host:
        display_url = f"{u.drivername}://{u.username}:***@{u.host}:{u.port or 5432}/{u.database}"
    else:
        display_url = str(u)
    print(f"Using database: {display_url}")

    init_db()
    for token, desc in pairs:
        add_github_token(token, description=desc)
        print(f"  OK: {desc or token[:24]}...")
    print(f"Done. Imported {len(pairs)} token(s).")


if __name__ == "__main__":
    main()
