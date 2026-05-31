#!/usr/bin/env python3
"""Prepare ARCTX package releases."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("arctx", "arctx-cli", "arctx-tui")
VERSION_FILES = (
    ROOT / "packages/arctx/pyproject.toml",
    ROOT / "packages/arctx-cli/pyproject.toml",
    ROOT / "packages/arctx-tui/pyproject.toml",
    ROOT / "packages/arctx/src/arctx/__init__.py",
)
DEPENDENCY_FILES = (
    ROOT / "packages/arctx-cli/pyproject.toml",
    ROOT / "packages/arctx-tui/pyproject.toml",
)


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def replace_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path.relative_to(ROOT)} for {pattern!r}")
    path.write_text(updated, encoding="utf-8")


def set_version(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:a|b|rc)?\d*", version):
        raise ValueError(f"Unsupported version format: {version}")

    for path in VERSION_FILES:
        if path.name == "__init__.py":
            replace_once(path, r'__version__ = "[^"]+"', f'__version__ = "{version}"')
        else:
            replace_once(path, r'^version = "[^"]+"', f'version = "{version}"')

    for path in DEPENDENCY_FILES:
        replace_once(path, r'"arctx>=[^"]+"', f'"arctx>={version}"')


def clean_dist() -> None:
    for package in PACKAGES:
        dist = ROOT / "packages" / package / "dist"
        if dist.exists():
            print(f"Removing {dist.relative_to(ROOT)}", flush=True)
            shutil.rmtree(dist)


def build_packages(no_isolation: bool) -> None:
    for package in PACKAGES:
        cmd = [sys.executable, "-m", "build"]
        if no_isolation:
            cmd.append("--no-isolation")
        cmd.append(f"packages/{package}")
        run(cmd)


def check_dist() -> None:
    files = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "packages").glob("*/dist/*"))
    if not files:
        raise RuntimeError("No distribution files found under packages/*/dist/")
    run([sys.executable, "-m", "twine", "check", *files])


def upload_dist() -> None:
    files = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "packages").glob("*/dist/*"))
    if not files:
        raise RuntimeError("No distribution files found under packages/*/dist/")
    run([sys.executable, "-m", "twine", "upload", *files])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bump ARCTX package versions and optionally build/upload distributions."
    )
    parser.add_argument("version", help="Release version, for example 0.2.0b3")
    parser.add_argument("--no-clean", action="store_true", help="Do not remove package dist dirs")
    parser.add_argument("--build", action="store_true", help="Build all three packages")
    parser.add_argument(
        "--no-isolation",
        action="store_true",
        help="Build with dependencies from the active environment",
    )
    parser.add_argument("--check", action="store_true", help="Run twine check after build")
    parser.add_argument("--upload", action="store_true", help="Upload packages/*/dist/* with twine")
    args = parser.parse_args()

    set_version(args.version)
    if not args.no_clean:
        clean_dist()
    if args.build:
        build_packages(args.no_isolation)
    if args.check:
        check_dist()
    if args.upload:
        upload_dist()

    print(f"Prepared ARCTX {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
