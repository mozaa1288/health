#!/usr/bin/env python3
"""Validate the health skill bundle with only the Python standard library."""

from __future__ import annotations

import json
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
    "recommend-next-meal",
    "update-pantry",
)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def validate_marketplace() -> None:
    path = ROOT / ".claude-plugin" / "marketplace.json"
    try:
        marketplace = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail("missing .claude-plugin/marketplace.json")
    except json.JSONDecodeError as exc:
        fail(f"invalid marketplace JSON: {exc}")

    plugins = marketplace.get("plugins")
    if marketplace.get("name") != "mozaa-health" or not isinstance(plugins, list) or len(plugins) != 1:
        fail("invalid mozaa-health marketplace structure")

    plugin = plugins[0]
    if plugin.get("name") != "health-automation" or plugin.get("source") != "./":
        fail("invalid health-automation plugin definition")

    expected = {f"./skills/{name}" for name in SKILLS}
    actual = set(plugin.get("skills") or [])
    if actual != expected:
        fail(f"marketplace skill mismatch; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")


def main() -> int:
    validate_marketplace()
    python_files: list[Path] = []
    tests: list[Path] = []

    for name in SKILLS:
        skill_dir = ROOT / "skills" / name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            fail(f"missing {skill_md.relative_to(ROOT)}")

        parts = skill_md.read_text(encoding="utf-8").split("---", 2)
        if len(parts) < 3 or f"name: {name}" not in parts[1]:
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
        result = subprocess.run([sys.executable, str(test)], cwd=test.parent, env=env, check=False)
        if result.returncode:
            fail(f"tests failed: {test.relative_to(ROOT)}")

    print(f"Validated {len(SKILLS)} skills, {len(python_files)} Python files, and {len(tests)} test suites.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
