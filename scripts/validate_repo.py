#!/usr/bin/env python3
"""Validate the health skill bundle with only the Python standard library."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    "pull-garmin-data",
    "plan-meals",
    "log-food",
    "sync-food",
    "recommend-meal",
    "update-pantry",
)
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
BACKTICK_RELATIVE_PATH = re.compile(r"`((?:\.\.?/)+[^`\s]+)`")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")


def validate_marketplace() -> None:
    path = ROOT / ".claude-plugin" / "marketplace.json"
    marketplace = load_json(path)
    if not isinstance(marketplace, dict):
        fail("marketplace must contain a JSON object")

    plugins = marketplace.get("plugins")
    if marketplace.get("name") != "mozaa-health" or not isinstance(plugins, list) or len(plugins) != 1:
        fail("invalid mozaa-health marketplace structure")

    plugin = plugins[0]
    if plugin.get("name") != "health-automation" or plugin.get("source") != "./":
        fail("invalid health-automation plugin definition")

    expected = [f"./skills/{name}" for name in SKILLS]
    actual = plugin.get("skills")
    if actual != expected:
        fail(f"marketplace skill list mismatch; expected={expected}, actual={actual}")


def validate_bundle() -> None:
    path = ROOT / "skill-bundle.json"
    bundle = load_json(path)
    if not isinstance(bundle, dict):
        fail("skill-bundle.json must contain a JSON object")
    if bundle.get("skills") != list(SKILLS):
        fail(
            "skill-bundle.json skill list mismatch; "
            f"expected={list(SKILLS)}, actual={bundle.get('skills')}"
        )


def validate_relative_links() -> int:
    checked = 0
    root_resolved = ROOT.resolve()
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        candidates = MARKDOWN_LINK.findall(text)
        candidates.extend(BACKTICK_RELATIVE_PATH.findall(text))
        for candidate in candidates:
            destination = candidate.split("#", 1)[0].split("?", 1)[0]
            if not destination or destination.startswith(
                ("#", "/", "http://", "https://", "mailto:")
            ):
                continue
            target = (path.parent / destination).resolve()
            if not target.is_relative_to(root_resolved):
                fail(
                    f"{path.relative_to(ROOT)} links outside the repository: "
                    f"{candidate}"
                )
            if not target.exists():
                fail(
                    f"{path.relative_to(ROOT)} has missing relative link/path: "
                    f"{candidate}"
                )
            checked += 1
    return checked


def validate_skill_layout() -> None:
    skills_dir = ROOT / "skills"
    actual = sorted(
        path.name
        for path in skills_dir.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    expected = sorted(SKILLS)
    if actual != expected:
        fail(f"skill folder mismatch; expected={expected}, actual={actual}")

    for name in SKILLS:
        skill_dir = skills_dir / name
        skill_md = skill_dir / "SKILL.md"
        agent_metadata = skill_dir / "agents" / "openai.yaml"
        if not skill_md.is_file():
            fail(f"missing {skill_md.relative_to(ROOT)}")
        if not agent_metadata.is_file():
            fail(f"missing {agent_metadata.relative_to(ROOT)}")

        parts = skill_md.read_text(encoding="utf-8").split("---", 2)
        if len(parts) < 3:
            fail(f"{skill_md.relative_to(ROOT)} is missing YAML frontmatter")
        names = re.findall(r"^name:\s*(\S+)\s*$", parts[1], flags=re.MULTILINE)
        if names != [name]:
            fail(
                f"{skill_md.relative_to(ROOT)} has the wrong skill name; "
                f"expected={name}, actual={names}"
            )


def main() -> int:
    validate_marketplace()
    validate_bundle()
    validate_skill_layout()
    relative_links = validate_relative_links()

    generated = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("__pycache__")
        if ".git" not in path.parts
    ]
    if generated:
        fail(f"generated __pycache__ directories found: {generated}")

    raw_archives = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("garmin_????-??-??.json")
        if ".git" not in path.parts
    ]
    if raw_archives:
        fail(f"raw Garmin daily archives found: {raw_archives}")

    food_logs = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("food-log-????-??-??.jsonl")
        if ".git" not in path.parts
    ]
    if food_logs:
        fail(f"daily food logs found: {food_logs}")

    stale_runtime_food_sheet_terms = (
        "12Exzl-EZWxkiN0cd9XafE9R7a_MBoNiZuio46deANnQ",
        "sheet_rows",
        "Daily Summary",
        "27-column",
    )
    stale_files: list[str] = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".git" in path.parts
            or path.suffix not in {".md", ".py", ".json", ".yaml", ".yml"}
        ):
            continue
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        if any(term in text for term in stale_runtime_food_sheet_terms):
            stale_files.append(str(path.relative_to(ROOT)))
    if stale_files:
        fail(f"stale runtime food-sheet references found: {sorted(stale_files)}")

    python_files = sorted(
        path for path in ROOT.rglob("*.py") if ".git" not in path.parts
    )
    tests = [path for path in python_files if path.name.startswith("test_")]
    for path in python_files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            fail(f"Python syntax failed in {path.relative_to(ROOT)}: {exc}")

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for test in tests:
        result = subprocess.run([sys.executable, str(test)], cwd=test.parent, env=env, check=False)
        if result.returncode:
            fail(f"tests failed: {test.relative_to(ROOT)}")

    print(
        f"Validated {len(SKILLS)} skills, {len(python_files)} Python files, "
        f"{relative_links} relative links/paths, and {len(tests)} test suites."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
