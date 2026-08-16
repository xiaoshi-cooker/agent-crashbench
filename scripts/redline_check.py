#!/usr/bin/env python3
"""Pre-push content guard.

Scans all git-tracked files and commit messages for terms listed in an
external wordlist. The wordlist itself intentionally lives OUTSIDE this
repository (path supplied via the ``REDLINE_WORDLIST`` environment variable);
when it is absent the check is skipped silently, so CI and third-party clones
are unaffected.

Exit codes: 0 = clean or skipped, 1 = at least one match found.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def commit_messages() -> str:
    out = subprocess.run(
        ["git", "log", "--format=%B"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    return out


def main() -> int:
    wordlist_path = os.environ.get("REDLINE_WORDLIST", "")
    if not wordlist_path or not Path(wordlist_path).is_file():
        print("redline: no wordlist configured, skipping.")
        return 0

    terms = [
        t.strip().lower()
        for t in Path(wordlist_path).read_text(encoding="utf-8").splitlines()
        if t.strip() and not t.strip().startswith("#")
    ]
    if not terms:
        print("redline: wordlist empty, skipping.")
        return 0

    hits: list[str] = []

    for rel in tracked_files():
        p = Path(rel)
        try:
            text = p.read_text(encoding="utf-8", errors="ignore").lower()
        except (OSError, IsADirectoryError):
            continue
        for term in terms:
            if term in text:
                hits.append(f"{rel}: contains term #{terms.index(term) + 1}")

    log_text = commit_messages().lower()
    for term in terms:
        if term in log_text:
            hits.append(f"<commit messages>: contains term #{terms.index(term) + 1}")

    if hits:
        print("redline: FAIL — matches found (terms referenced by index, not echoed):")
        for h in hits:
            print("  " + h)
        return 1

    print(f"redline: clean ({len(terms)} terms, {len(tracked_files())} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
