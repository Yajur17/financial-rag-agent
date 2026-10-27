"""
Pre-publish privacy scan.

This repo was derived from a private project built on real brokerage
statements. Before anything is pushed, every file in the repo is checked
against a denylist of values taken from those real statements (figures,
security names, ISINs, ids, the holder's name, etc.).

The denylist itself is sensitive, so it is NOT in the repo: it lives in a
gitignored local file, `.privacy_denylist.txt`, one entry per line:

  num:<n>      a number, normalised (commas removed, trailing zeros dropped).
               Matches any numeric token in the repo with the same value.
  int:<n>      an integer part (>= 4 digits). Matches any numeric token whose
               integer part is n -- catches truncated figures like 1,23,456.
  str:<s>      case-insensitive substring (ids, ISINs, codes)
  phrase:<p>   case-insensitive phrase, whitespace-insensitive
  word:<w>     case-insensitive whole word
  literal:<l>  exact substring
  author:<w>   the author's name: a word that is a hit everywhere EXCEPT in
               LICENSE and on README credit lines

Bare 4-digit years (e.g. 2025) are not checked as numbers -- dates are
everywhere and carry no information. The author's name is allowed only in
LICENSE and on README credit lines (see `author:` above).

Usage:  python3 scripts/privacy_scan.py            (exit code 1 on any hit)
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DENYLIST = ROOT / ".privacy_denylist.txt"

SKIP_DIRS = {".git", "__pycache__", "embeddings", "node_modules", ".venv", "venv"}
SKIP_FILES = {".privacy_denylist.txt", ".env", ".DS_Store"}
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def norm(tok):
    tok = tok.rstrip(",.")
    t = tok.replace(",", "")
    if "." in t:
        whole, frac = t.split(".", 1)
        frac = frac.rstrip("0")
    else:
        whole, frac = t, ""
    whole = whole.lstrip("0") or "0"
    return whole + ("." + frac if frac else ""), whole


def load_denylist():
    if not DENYLIST.exists():
        sys.exit(f"denylist not found: {DENYLIST} (it is local-only by design)")
    d = {"num": set(), "int": set(), "str": [], "phrase": [], "word": [], "literal": [], "author": []}
    for line in DENYLIST.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or ":" not in line:
            continue
        kind, val = line.split(":", 1)
        if kind in ("num", "int"):
            d[kind].add(val)
        elif kind in d:
            d[kind].append(val)
    return d


def repo_files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_dir() or any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if p.name in SKIP_FILES:
            continue
        yield p


def author_allowed(path, line):
    rel = path.relative_to(ROOT).as_posix()
    if rel == "LICENSE":
        return True
    return rel == "README.md" and re.search(r"author|copyright|built by|©", line, re.I)


def scan_line(path, line, d, compiled, compiled_author):
    hits = []
    for m in NUM.finditer(line):
        raw = m.group(0).rstrip(",.")
        if re.fullmatch(r"(19|20)\d\d", raw):          # bare year
            continue
        full, whole = norm(raw)
        if full in d["num"]:
            hits.append(("num", raw))
        elif len(whole) >= 4 and whole in d["int"]:
            hits.append(("int", raw))
    low = line.lower()
    for s in d["str"]:
        if s.lower() in low:
            hits.append(("str", s))
    squashed = re.sub(r"\s+", " ", low)
    for p in d["phrase"]:
        if re.sub(r"\s+", " ", p.lower()) in squashed:
            hits.append(("phrase", p))
    for w, rx in compiled:
        if rx.search(line):
            hits.append(("word", w))
    for w, rx in compiled_author:
        if rx.search(line) and not author_allowed(path, line):
            hits.append(("author", w))
    for lit in d["literal"]:
        if re.search(r"(?<![A-Za-z])" + re.escape(lit), line):
            hits.append(("literal", lit))
    return hits


def main():
    d = load_denylist()
    compiled = [(w, re.compile(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", re.I))
                for w in d["word"]]
    compiled_author = [(w, re.compile(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", re.I))
                       for w in d["author"]]
    n_entries = sum(len(v) for v in d.values())
    total, files = 0, 0
    for path in repo_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files += 1
        for i, line in enumerate(text.splitlines(), 1):
            for kind, val in scan_line(path, line, d, compiled, compiled_author):
                total += 1
                print(f"{path.relative_to(ROOT)}:{i}: [{kind}] {val}")
    # git metadata: the commit identity must be the personal one, never a work account
    try:
        email = subprocess.run(["git", "-C", str(ROOT), "config", "--local", "user.email"],
                               capture_output=True, text=True).stdout.strip()
        if email:
            print(f"git user.email (repo-local): {email}")
    except FileNotFoundError:
        pass
    print(f"\nscanned {files} files against {n_entries} denylist entries -> {total} hit(s)")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
