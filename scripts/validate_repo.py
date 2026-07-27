#!/usr/bin/env python3
"""Validate every bundled health skill without third-party dependencies."""

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
    "update-pantry",
)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def validate_marketplace() -> None:
    path = ROOT / ".claude-plugin" / "marketplace.json"
    if not path.is_file():
        fail("missing .claude-plugin/marketplace.json")
    try:
        marketplace = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid marketplace JSON: {exc}")

    if marketplace.get("name") != "mozaa-health":
        fail("marketplace name must be mozaa-health")
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        fail("marketplace must expose one health-automation bundle")
    plugin = plugins[0]
    if plugin.get("name") != "health-automation":
        fail("plugin name must be health-automation")
    if plugin.get("source") != "./" or plugin.get("strict") is not False:
        fail("health-automation must use source './' with strict false")

    expected_paths = {f"./skills/{name}" for name in SKILLS}
    actual_paths = set(plugin.get("skills") or [])
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        fail(f"marketplace skill mismatch; missing={missing}, extra={extra}")
    for relative in actual_paths:
        if not (ROOT / relative.removeprefix("./") / "SKILL.md").is_file():
            fail(f"marketplace path has no SKILL.md: {relative}")


def main() -> int:
    validate_marketplace()
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
        f"Validated marketplace, {len(SKILLS)} skills, {len(python_files)} Python files, "
        f"and {len(tests)} test suites."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
