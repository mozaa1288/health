#!/usr/bin/env python3
"""Validate every bundled health skill without third-party dependencies."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    "archive-garmin-data",
    "garmin-pantry-meal-plan",
    "import-garmin-account-export",
    "log-food",
    "reconcile-daily-food",
    "update-pantry",
)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def main() -> int:
    python_files: list[Path] = []
    tests: list[Path] = []
    for name in SKILLS:
        skill_dir = ROOT / "skills" / name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            fail(f"missing {skill_md.relative_to(ROOT)}")
        frontmatter = skill_md.read_text(encoding="utf-8").split("---", 2)
        if len(frontmatter) < 3 or f"name: {name}" not in frontmatter[1]:
            fail(f"{skill_md.relative_to(ROOT)} has the wrong skill name")
        if any(path.name == "__pycache__" for path in skill_dir.rglob("__pycache__")):
            fail(f"generated __pycache__ found in {skill_dir.relative_to(ROOT)}")
        for path in skill_dir.rglob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
            python_files.append(path)
            if path.name.startswith("test_"):
                tests.append(path)

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for test in tests:
        result = subprocess.run(
            [sys.executable, str(test)],
            cwd=test.parent,
            env=env,
            check=False,
        )
        if result.returncode:
            fail(f"tests failed: {test.relative_to(ROOT)}")

    print(
        f"Validated {len(SKILLS)} skills, {len(python_files)} Python files, "
        f"and {len(tests)} test suites."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
