#!/usr/bin/env python3
import argparse
import pathlib
import re
import subprocess
import sys
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "highway_to_hell_engine" / "__init__.py"
DIST_DIR = ROOT / "dist"

FORBIDDEN_PATH_PATTERNS = [
    r"(^|/)logs/",
    r"(^|/)highway_to_hell_engine_data/",
    r"(^|/)duality_data/",
    r"(^|/)highway_to_hell_engine_venv/",
    r"(^|/)duality_venv/",
    r"(^|/)\.codex/",
    r"(^|/)\.vscode/",
    r"(^|/)\.idea/",
    r"\.log$",
    r"\.db$",
    r"spotify_oauth_cache\.json$",
    r"highway_to_hell_engine_config\.json$",
]

# Heuristic scans to catch accidental hardcoded credentials.
FORBIDDEN_CONTENT_PATTERNS = [
    r"(?i)(spotify_secret|client_secret|api_key|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
    r"(?i)discord_client_id\s*[:=]\s*['\"]\d{18,19}['\"]",
]

REQUIRED_MARKERS: dict[str, list[str]] = {
    "LICENSE": [
        r"(?i)copyright \(c\)\s*2026\s*mr\.zagreed",
        r"(?i)remove, alter, or hide the original authorship attribution",
    ],
    "NOTICE": [
        r"(?i)hth engine notice",
        r"(?i)copyright \(c\)\s*2026\s*mr\.zagreed",
    ],
    "highway_to_hell_engine/authorship.py": [
        r"AUTHOR_NAME\s*=\s*\"Mr\.Zagreed\"",
        r"AUTHOR_NOTICE\s*=\s*\"Discord Karaoke RPC by Mr\.Zagreed\"",
    ],
    "README.md": [
        r"## Authorship and license",
        r"`LICENSE`",
    ],
    "README_ru.md": [
        r"## Авторство и лицензия",
        r"`LICENSE`",
    ],
}


def run_git(args: Iterable[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def read_version() -> str:
    content = VERSION_FILE.read_text(encoding="utf-8")
    m = re.search(r"__version__\s*=\s*\"([^\"]+)\"", content)
    if not m:
        raise RuntimeError("Cannot parse __version__")
    return m.group(1)


def check_clean_worktree() -> None:
    status = run_git(["status", "--porcelain"])
    if status:
        raise RuntimeError("Working tree is not clean. Commit or stash changes before release.")


def check_branch(expected: str = "master") -> None:
    branch = run_git(["branch", "--show-current"])
    if branch != expected:
        raise RuntimeError(f"Release must be made from '{expected}' branch. Current: '{branch}'")


def tracked_files() -> list[str]:
    out = run_git(["ls-files"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def scan_paths(files: list[str]) -> None:
    bad = []
    for path in files:
        normalized = path.replace("\\", "/")
        for pat in FORBIDDEN_PATH_PATTERNS:
            if re.search(pat, normalized):
                bad.append(path)
                break
    if bad:
        joined = "\n".join(f"  - {p}" for p in sorted(set(bad)))
        raise RuntimeError(f"Forbidden files are tracked and would leak into release:\n{joined}")


def scan_contents(files: list[str]) -> None:
    hits = []
    for rel in files:
        p = ROOT / rel
        if not p.is_file():
            continue
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".ico", ".db"}:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for pat in FORBIDDEN_CONTENT_PATTERNS:
            if re.search(pat, text):
                hits.append(rel)
                break
    if hits:
        joined = "\n".join(f"  - {p}" for p in sorted(set(hits)))
        raise RuntimeError(f"Potential hardcoded secrets detected:\n{joined}")


def create_archive(version: str) -> pathlib.Path:
    DIST_DIR.mkdir(exist_ok=True)
    out = DIST_DIR / f"hth-engine-v{version}.zip"
    run_git(["archive", "--format", "zip", "-o", str(out), "HEAD"])
    return out

def check_required_markers(files: list[str]) -> None:
    tracked = set(files)
    errors: list[str] = []

    for rel, patterns in REQUIRED_MARKERS.items():
        if rel not in tracked:
            errors.append(f"{rel}: file is missing from tracked release files")
            continue

        p = ROOT / rel
        if not p.is_file():
            errors.append(f"{rel}: file not found on disk")
            continue

        try:
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            errors.append(f"{rel}: cannot read file ({e})")
            continue

        missing = [pat for pat in patterns if not re.search(pat, text)]
        if missing:
            errors.append(f"{rel}: missing required authorship markers")

    if errors:
        joined = "\n".join(f"  - {x}" for x in errors)
        raise RuntimeError(f"Authorship/copyright checks failed:\n{joined}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe release guard for HtH Engine")
    parser.add_argument("--create-archive", action="store_true", help="Create dist/hth-engine-v<version>.zip from HEAD")
    parser.add_argument("--skip-branch-check", action="store_true", help="Allow running outside master branch")
    args = parser.parse_args()

    try:
        version = read_version()
        if "pre" in version.lower():
            raise RuntimeError(f"Version '{version}' still looks pre-release.")

        check_clean_worktree()
        if not args.skip_branch_check:
            check_branch("master")

        files = tracked_files()
        scan_paths(files)
        scan_contents(files)
        check_required_markers(files)

        print(f"Release guard OK for version {version}")

        if args.create_archive:
            archive = create_archive(version)
            print(f"Archive created: {archive}")

        print("Safe to tag and publish release.")
        return 0
    except Exception as e:
        print(f"RELEASE GUARD FAILED: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

