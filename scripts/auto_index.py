#!/usr/bin/env python3
"""
Tiny index generator for claude-artifacts.

Usage:
  python3 scripts/auto_index.py
  python3 scripts/auto_index.py --dry-run
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


INDEX_FILE = "index.html"
ALLOWED_EXTS = {".html", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
IGNORE_FILES = {INDEX_FILE}
NOTES_HINTS = {
    "note",
    "notes",
    "playbook",
    "guide",
    "prompt",
    "curriculum",
    "cheatsheet",
}


@dataclass
class Artifact:
    title: str
    desc: str
    file: str
    tag: str
    date: str


def js_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def to_title(filename: str) -> str:
    stem = Path(filename).stem.replace("-", " ").replace("_", " ")
    return " ".join(word.capitalize() for word in stem.split())


def infer_tag(file_name: str) -> str:
    stem = Path(file_name).stem.lower()
    if any(hint in stem for hint in NOTES_HINTS):
        return "notes"
    if Path(file_name).suffix.lower() == ".html":
        return "tool"
    return "projects"


def infer_desc(file_name: str, tag: str) -> str:
    if tag == "notes":
        return f"Auto-added notes artifact ({file_name})."
    if tag == "tool":
        return f"Auto-added interactive artifact ({file_name})."
    return f"Auto-added project artifact ({file_name})."


def parse_existing_artifacts(index_html: str) -> tuple[list[Artifact], tuple[int, int]]:
    array_match = re.search(
        r"const\s+artifacts\s*=\s*\[(?P<body>.*?)\]\s*;",
        index_html,
        re.DOTALL,
    )
    if not array_match:
        raise RuntimeError("Could not find `const artifacts = [...]` in index.html")

    body = array_match.group("body")
    span = array_match.span()
    object_pattern = re.compile(
        r"""\{
\s*title:\s*"(?P<title>.*?)",
\s*desc:\s*"(?P<desc>.*?)",
\s*file:\s*"(?P<file>.*?)",
\s*tag:\s*"(?P<tag>.*?)",
\s*date:\s*"(?P<date>.*?)"
\s*\}""",
        re.DOTALL,
    )

    artifacts: list[Artifact] = []
    for match in object_pattern.finditer(body):
        tag = match.group("tag").strip()
        if tag == "tools":
            tag = "tool"
        if tag not in {"notes", "tool", "projects"}:
            tag = infer_tag(match.group("file").strip())
        artifacts.append(
            Artifact(
                title=match.group("title").strip(),
                desc=match.group("desc").strip(),
                file=match.group("file").strip(),
                tag=tag,
                date=match.group("date").strip(),
            )
        )
    return artifacts, span


def build_final_artifacts(repo_root: Path, existing: list[Artifact]) -> list[Artifact]:
    existing_by_file = {item.file: item for item in existing}
    existing_order = [item.file for item in existing]

    discoverable_files = sorted(
        [
            p.name
            for p in repo_root.iterdir()
            if p.is_file()
            and p.suffix.lower() in ALLOWED_EXTS
            and p.name not in IGNORE_FILES
            and not p.name.startswith(".")
        ],
        key=str.lower,
    )

    ordered_files: list[str] = []
    for file_name in existing_order:
        if file_name in discoverable_files:
            ordered_files.append(file_name)
    for file_name in discoverable_files:
        if file_name not in ordered_files:
            ordered_files.append(file_name)

    today = datetime.now().strftime("%b %Y")
    final_items: list[Artifact] = []
    for file_name in ordered_files:
        if file_name in existing_by_file:
            item = existing_by_file[file_name]
            final_items.append(
                Artifact(
                    title=item.title or to_title(file_name),
                    desc=item.desc or infer_desc(file_name, item.tag),
                    file=file_name,
                    tag=item.tag,
                    date=item.date or today,
                )
            )
        else:
            tag = infer_tag(file_name)
            final_items.append(
                Artifact(
                    title=to_title(file_name),
                    desc=infer_desc(file_name, tag),
                    file=file_name,
                    tag=tag,
                    date=today,
                )
            )
    return final_items


def render_artifacts_block(artifacts: list[Artifact]) -> str:
    lines = ["const artifacts = ["]
    for i, item in enumerate(artifacts):
        lines.extend(
            [
                "  {",
                f'    title: "{js_escape(item.title)}",',
                f'    desc: "{js_escape(item.desc)}",',
                f'    file: "{js_escape(item.file)}",',
                f'    tag: "{js_escape(item.tag)}",',
                f'    date: "{js_escape(item.date)}"',
                "  }" + ("," if i < len(artifacts) - 1 else ""),
            ]
        )
    lines.append("];")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-update index.html artifacts list.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root containing index.html (default: current directory).",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    index_path = repo_root / INDEX_FILE
    if not index_path.exists():
        raise FileNotFoundError(f"{index_path} not found")

    original = index_path.read_text(encoding="utf-8")
    existing, span = parse_existing_artifacts(original)
    final_items = build_final_artifacts(repo_root, existing)
    new_block = render_artifacts_block(final_items)
    updated = original[: span[0]] + new_block + original[span[1] :]

    print(f"Found {len(existing)} existing entries.")
    print(f"Discovered {len(final_items)} artifact files.")

    if args.dry_run:
        print("Dry run only; no file changes written.")
        return 0

    if updated != original:
        index_path.write_text(updated, encoding="utf-8")
        print(f"Updated {index_path}")
    else:
        print("No changes needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
