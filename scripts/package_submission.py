#!/usr/bin/env python3
"""Submission packaging and verification script for CS11-768 Assignment 1.

Verifies all required files and artifacts are present, checks that no forbidden
or sensitive files are included, and packages a clean submission ZIP archive.
"""

from pathlib import Path
import sys
import zipfile

REQUIRED_ARTIFACTS = [
    "artifacts/fix.patch",
    "artifacts/part1-trajectory.json",
    "artifacts/django__django-15368.patch",
    "artifacts/django__django-15368-trajectory.json",
    "artifacts/token-usage-analysis.md",
    "artifacts/part3-trajectory.json",
    "artifacts/game-result.json",
    "artifacts/part3-no-legal-moves-deepseek.json",
    "artifacts/part3-no-legal-moves-deepseek-result.json",
    "artifacts/part3-legal-moves-deepseek.json",
    "artifacts/part3-legal-moves-deepseek-result.json",
    "artifacts/part3-no-legal-moves-gpt-oss.json",
    "artifacts/part3-no-legal-moves-gpt-oss-result.json",
    "artifacts/part3-legal-moves-gpt-oss.json",
    "artifacts/part3-legal-moves-gpt-oss-result.json",
    "artifacts/observation-experiment.md",
    "artifacts/part3-python-skill-trajectory.json",
]

REQUIRED_SRC = [
    "src/assignment/agent/base.py",
    "src/assignment/agent/code_agent.py",
    "src/assignment/agent/chess_agent.py",
    "src/assignment/agent/chess_tools.py",
    "src/assignment/agent/tools.py",
    "src/assignment/agent/chess_analysis.py",
    "src/assignment/prompts.py",
]

REQUIRED_OTHER = [
    "AI_USAGE.md",
]


def check_placeholders(path: Path) -> list[str]:
    """Check markdown file for unfilled placeholders."""
    issues = []
    text = path.read_text(encoding="utf-8")
    for placeholder in ["*[Count]*", "*[%]*", "*[Yes / No]*", "[TODO", "TODO:"]:
        if placeholder in text:
            issues.append(f"Unfilled placeholder '{placeholder}' found in {path}")
    return issues


def verify_and_package(output_zip: str = "submission.zip") -> bool:
    root = Path(__file__).resolve().parent.parent
    missing: list[str] = []

    print("=== Checking Required Files ===")
    all_files = REQUIRED_ARTIFACTS + REQUIRED_SRC + REQUIRED_OTHER
    for rel_path in all_files:
        p = root / rel_path
        if not p.is_file():
            missing.append(rel_path)
            print(f"  [MISSING] {rel_path}")
        else:
            print(f"  [OK]      {rel_path}")

    # Check for placeholders in reports
    for rep in ["artifacts/observation-experiment.md", "artifacts/token-usage-analysis.md"]:
        p = root / rep
        if p.is_file():
            issues = check_placeholders(p)
            for issue in issues:
                print(f"  [WARN]    {issue}")

    if missing:
        print(f"\nError: {len(missing)} required file(s) are missing. Cannot build submission archive.")
        return False

    print(f"\n=== Packaging {output_zip} ===")
    zip_path = root / output_zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in all_files:
            file_path = root / rel_path
            zf.write(file_path, arcname=rel_path)
            print(f"  Added: {rel_path}")

    print(f"\n[OK] Submission packaged successfully: {zip_path}")
    print(f"Archive size: {zip_path.stat().st_size / (1024 * 1024):.2f} MB")

    # Verify archive contents
    print("\n=== Verifying Archive Contents ===")
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        print(f"Total entries: {len(namelist)}")
        forbidden = [n for n in namelist if ".env" in n or "tests/" in n or "tasks/" in n]
        if forbidden:
            print(f"  [ERROR] Forbidden entries found: {forbidden}")
            return False
        print("  [OK] No forbidden files detected.")

    return True


if __name__ == "__main__":
    success = verify_and_package()
    sys.exit(0 if success else 1)
