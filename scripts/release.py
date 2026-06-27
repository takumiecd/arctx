#!/usr/bin/env python3
# ruff: noqa: D103
"""Prepare ARCTX package releases.

The default release surface is arctx + arctx-cli. arctx-tui can be included
explicitly, but it is not part of the must-ship release path.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PACKAGES = ("arctx", "arctx-cli")
ALL_PACKAGES = ("arctx", "arctx-cli", "arctx-tui")
VERSION_FILES = (
    ROOT / "packages/arctx/pyproject.toml",
    ROOT / "packages/arctx-cli/pyproject.toml",
    ROOT / "packages/arctx-tui/pyproject.toml",
    ROOT / "packages/arctx/src/arctx/__init__.py",
)
DIST = ROOT / "dist"
WEB = ROOT / "web"
PACKAGED_STATIC = ROOT / "packages/arctx/src/arctx/web/static"
DEPENDENCY_FILES = (
    ROOT / "packages/arctx-cli/pyproject.toml",
    ROOT / "packages/arctx-tui/pyproject.toml",
)


def run(cmd: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(cmd), flush=True)
    env = os.environ.copy()
    if cmd and cmd[0] == uv():
        env.setdefault("UV_CACHE_DIR", str(ROOT / ".uv-cache"))
        env.setdefault("UV_TOOL_DIR", str(ROOT / ".uv-tools"))
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def uv() -> str:
    path = shutil.which("uv")
    if path is None:
        raise RuntimeError(
            "uv is required for release automation. Install it first: https://docs.astral.sh/uv/"
        )
    return path


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


def clean_dist(packages: tuple[str, ...]) -> None:
    if DIST.exists():
        print(f"Removing {DIST.relative_to(ROOT)}", flush=True)
        shutil.rmtree(DIST)
    for package in packages:
        dist = ROOT / "packages" / package / "dist"
        if dist.exists():
            print(f"Removing {dist.relative_to(ROOT)}", flush=True)
            shutil.rmtree(dist)


def run_tests() -> None:
    run(
        [
            uv(),
            "run",
            "pytest",
            "packages/arctx/tests",
            "packages/arctx-cli/tests",
            "packages/arctx-tui/tests",
            "--import-mode=importlib",
            "-q",
        ]
    )


def bundle_web(*, npm_install: str) -> None:
    package_json = WEB / "package.json"
    if not package_json.is_file():
        raise RuntimeError("web/package.json is missing")

    install_cmd = ["npm", npm_install]
    if npm_install == "ci" and not (WEB / "package-lock.json").is_file():
        install_cmd = ["npm", "install"]

    run(install_cmd, cwd=WEB)
    run(["npm", "run", "build"], cwd=WEB)

    dist = WEB / "dist"
    if not (dist / "index.html").is_file():
        raise RuntimeError("web build produced no dist/index.html")

    if PACKAGED_STATIC.exists():
        shutil.rmtree(PACKAGED_STATIC)
    shutil.copytree(dist, PACKAGED_STATIC)
    print(
        f"Copied {dist.relative_to(ROOT)} -> {PACKAGED_STATIC.relative_to(ROOT)}",
        flush=True,
    )


def build_packages(packages: tuple[str, ...]) -> None:
    DIST.mkdir(exist_ok=True)
    for package in packages:
        run([uv(), "build", f"packages/{package}", "--out-dir", str(DIST)])


def dist_files() -> list[str]:
    files = [
        path
        for path in DIST.iterdir()
        if path.is_file() and (path.name.endswith(".whl") or path.name.endswith(".tar.gz"))
    ]
    return sorted(str(path.relative_to(ROOT)) for path in files)


def check_dist() -> None:
    files = dist_files()
    if not files:
        raise RuntimeError("No distribution files found under dist/")
    run([uv(), "tool", "run", "twine", "check", *files])


def upload_dist(repository: str | None) -> None:
    files = dist_files()
    if not files:
        raise RuntimeError("No distribution files found under dist/")
    cmd = [uv(), "tool", "run", "twine", "upload"]
    if repository:
        cmd.extend(["--repository", repository])
    cmd.extend(files)
    run(cmd)


def package_selection(args: argparse.Namespace) -> tuple[str, ...]:
    selected = tuple(args.package or PRIMARY_PACKAGES)
    if args.include_tui and "arctx-tui" not in selected:
        selected = (*selected, "arctx-tui")
    unknown = sorted(set(selected) - set(ALL_PACKAGES))
    if unknown:
        raise ValueError(f"Unknown package(s): {', '.join(unknown)}")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bump ARCTX package versions and optionally build/upload distributions."
    )
    parser.add_argument("version", help="Release version, for example 0.3.1b1")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help=(
            "Run the standard release path: test, bundle web, build arctx+arctx-cli, "
            "and twine check"
        ),
    )
    parser.add_argument(
        "--package",
        action="append",
        choices=ALL_PACKAGES,
        help="Package to build/upload. May be repeated. Defaults to arctx and arctx-cli.",
    )
    parser.add_argument(
        "--include-tui",
        action="store_true",
        help="Also include arctx-tui in the selected packages",
    )
    parser.add_argument("--no-clean", action="store_true", help="Do not remove dist directories")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest during --prepare")
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Do not build and package the web GUI",
    )
    parser.add_argument(
        "--npm-install",
        choices=("ci", "install"),
        default="ci",
        help="npm install command to use before building web (default: ci)",
    )
    parser.add_argument("--build", action="store_true", help="Build selected packages")
    parser.add_argument(
        "--no-isolation",
        action="store_true",
        help="Deprecated no-op kept for old release commands",
    )
    parser.add_argument("--check", action="store_true", help="Run twine check after build")
    parser.add_argument("--upload", action="store_true", help="Upload dist/* with twine")
    parser.add_argument(
        "--repository",
        default=None,
        help="Twine repository name, for example testpypi. Omit for production PyPI.",
    )
    args = parser.parse_args()

    packages = package_selection(args)
    set_version(args.version)
    if not args.no_clean:
        clean_dist(packages)
    if args.prepare and not args.skip_tests:
        run_tests()
    if args.prepare and not args.no_web:
        bundle_web(npm_install=args.npm_install)
    if args.build or args.prepare:
        build_packages(packages)
    if args.check or args.prepare:
        check_dist()
    if args.upload:
        upload_dist(args.repository)

    print(f"Prepared ARCTX {args.version}: {', '.join(packages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
