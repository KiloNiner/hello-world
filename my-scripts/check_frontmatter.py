#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml",
# ]
# ///
"""
check_frontmatter.py — Check YAML frontmatter well-formedness across a
directory of markdown notes (e.g. an Obsidian vault).

Usage:
    pipx run check_frontmatter.py PATH

Options:
    PATH   Directory to scan recursively for *.md files (required)

Notes:
    - Reports two classes of problem:
      1. Real YAML parse errors (bad quoting/escaping, broken block mappings,
         a '---' opener with no matching closer, frontmatter that doesn't
         parse to a mapping).
      2. Likely duplicated/nested frontmatter blocks: a second '---...---'
         block sitting at the top of the body that itself parses as a
         frontmatter-shaped mapping (has a recognized key like tags/aliases/
         summary). This is a corruption pattern seen in the wild where an
         editor or sync tool leaves an old frontmatter block behind as dead
         text instead of replacing it, silently hiding the note's real tags
         from anything that only reads the outer (minimal) block.
    - A plain '---' used as a markdown horizontal rule in the body is not
      flagged; only a second block that actually looks like frontmatter is.
    - Exits with status 1 if any problems were found, 0 otherwise, so it can
      be used as a CI/pre-commit gate.
"""
import argparse
import sys
from pathlib import Path

import yaml

FRONTMATTER_KEYS = {"aliases", "tags", "date created", "date modified", "summary", "wiki"}


def split_frontmatter(text):
    """Return (frontmatter_text, body_text), or (None, None) if the file
    doesn't open with a '---' block or has no closing '---'."""
    if not text.startswith("---"):
        return None, None
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return None, None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:])
    return None, None


def looks_like_frontmatter(fm_text):
    """True if this text parses as a dict with at least one recognized
    frontmatter key — used to distinguish a genuine duplicated block from
    a coincidental '---' horizontal rule in the body."""
    try:
        parsed = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return False
    return isinstance(parsed, dict) and bool(FRONTMATTER_KEYS & set(parsed.keys()))


def check_file(path):
    """Return (parse_error_or_None, is_duplicated)."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return None, False

    fm_text, body = split_frontmatter(raw)
    if fm_text is None:
        return "opens with '---' but no closing '---' delimiter found", False

    try:
        parsed = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        return f"YAML parse error: {e}", False

    if parsed is not None and not isinstance(parsed, dict):
        return f"frontmatter did not parse to a mapping (got {type(parsed).__name__})", False

    body_stripped = body.lstrip("\n")
    if body_stripped.startswith("---"):
        body_lines = body_stripped.split("\n")
        for j in range(1, min(len(body_lines), 30)):
            if body_lines[j].strip() == "---":
                inner = "\n".join(body_lines[1:j])
                if looks_like_frontmatter(inner):
                    return None, True
                break

    return None, False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="Directory to scan recursively for *.md files")
    args = parser.parse_args()

    if not args.path.is_dir():
        parser.error(f"not a directory: {args.path}")

    md_files = sorted(args.path.rglob("*.md"))
    parse_errors = []
    duplicated = []

    for path in md_files:
        rel = path.relative_to(args.path)
        try:
            error, is_duplicated = check_file(path)
        except Exception as e:
            parse_errors.append((str(rel), f"read/scan error: {e}"))
            continue
        if error:
            parse_errors.append((str(rel), error))
        if is_duplicated:
            duplicated.append(str(rel))

    print(f"Scanned {len(md_files)} markdown files under {args.path}\n")

    print(f"=== Real YAML parse errors: {len(parse_errors)} ===")
    for rel, reason in parse_errors:
        print(f"- {rel}\n    {reason}")

    print(f"\n=== Likely duplicated/nested frontmatter blocks: {len(duplicated)} ===")
    for rel in duplicated:
        print(f"- {rel}")

    if not parse_errors and not duplicated:
        print("No problems found.")

    sys.exit(1 if (parse_errors or duplicated) else 0)


if __name__ == "__main__":
    main()
