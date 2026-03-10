#!/usr/bin/env python3
"""
Bootstrap: selects a compatible Python, creates venv, installs dependencies,
and re-executes run.py inside the virtual environment.

Preferred versions:
- Python 3.12
- Python 3.11
- Python 3.10

If no compatible version is found via `py` launcher, the current
interpreter is used only when version-compatible.
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from typing import Iterable, Optional

VENVDIR_NAME = "highway_to_hell_engine_venv"
REENTER_FLAG = "--__highway_to_hell_engine__"
REQUIREMENTS_FILE = "requirements.txt"
PREFERRED_MINOR_VERSIONS = (12, 11, 10)
MIN_SUPPORTED = (3, 10)
MAX_TESTED_MAJOR = 3
MAX_TESTED_MINOR = 12


def venv_paths(venv_dir: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe", venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "python", venv_dir / "bin" / "pip"


def parse_python_version(text: str) -> Optional[tuple[int, int, int]]:
    raw = text.strip()
    if raw.lower().startswith("python "):
        raw = raw.split(None, 1)[1]

    parts = raw.split(".")
    if len(parts) < 2:
        return None

    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2]) if len(parts) >= 3 else 0
    except ValueError:
        return None

    return major, minor, patch


def format_version(version: tuple[int, int, int]) -> str:
    return f"{version[0]}.{version[1]}.{version[2]}"


def is_supported(version: tuple[int, int, int]) -> bool:
    return version >= (MIN_SUPPORTED[0], MIN_SUPPORTED[1], 0)


def is_preferred(version: tuple[int, int, int]) -> bool:
    return version[0] == MAX_TESTED_MAJOR and version[1] in PREFERRED_MINOR_VERSIONS


def describe_version_choice(version: tuple[int, int, int]) -> str:
    if is_preferred(version):
        return "preferred"
    if is_supported(version):
        if version[0] == MAX_TESTED_MAJOR and version[1] > MAX_TESTED_MINOR:
            return "compatible but untested"
        return "compatible"
    return "incompatible"


def run_capture(cmd: list[str], timeout: int = 10) -> Optional[str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    return (result.stdout or result.stderr or "").strip()


def get_python_version(python_cmd: list[str]) -> Optional[tuple[int, int, int]]:
    out = run_capture(python_cmd + ["--version"], timeout=8)
    if not out:
        return None
    return parse_python_version(out)


def iter_windows_py_candidates() -> Iterable[tuple[tuple[int, int, int], list[str], str]]:
    for minor in PREFERRED_MINOR_VERSIONS:
        cmd = ["py", f"-3.{minor}"]
        version = get_python_version(cmd)
        if version:
            yield version, cmd, f"launcher py -3.{minor}"

    for minor in range(13, 9, -1):
        if minor in PREFERRED_MINOR_VERSIONS:
            continue
        cmd = ["py", f"-3.{minor}"]
        version = get_python_version(cmd)
        if version:
            yield version, cmd, f"launcher py -3.{minor}"


def detect_best_python() -> tuple[list[str], tuple[int, int, int], str]:
    candidates: list[tuple[tuple[int, int, int], list[str], str]] = []

    if os.name == "nt":
        candidates.extend(iter_windows_py_candidates())

    current_cmd = [sys.executable]
    current_version = get_python_version(current_cmd)
    if current_version:
        candidates.append((current_version, current_cmd, "current interpreter"))

    preferred = [item for item in candidates if is_preferred(item[0])]
    if preferred:
        preferred.sort(key=lambda item: (item[0][0], item[0][1], item[0][2]), reverse=True)
        return preferred[0][1], preferred[0][0], preferred[0][2]

    supported = [item for item in candidates if is_supported(item[0])]
    if supported:
        supported.sort(key=lambda item: (item[0][0], item[0][1], item[0][2]), reverse=True)
        return supported[0][1], supported[0][0], supported[0][2]

    details = ", ".join(
        f"{source}: {format_version(version)} ({describe_version_choice(version)})"
        for version, _, source in candidates
    ) or "nothing found"
    raise RuntimeError(
        "No compatible Python found. Requires Python 3.10-3.12 (3.12 recommended). "
        f"Detected: {details}"
    )


def create_venv(venv_dir: Path, python_cmd: list[str]) -> None:
    venv_dir.parent.mkdir(parents=True, exist_ok=True)

    cmd_list = python_cmd + [
        "-m", "venv",
        "--clear",
        "--upgrade-deps",
        str(venv_dir),
    ]

    try:
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        if result.returncode == 0:
            return

        print("Failed to create venv:", file=sys.stderr)
        print(result.stderr.strip() or result.stdout.strip() or "[no output]", file=sys.stderr)
    except FileNotFoundError:
        print("Failed to launch selected interpreter to create venv.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Venv creation timed out.", file=sys.stderr)

    if os.name == "nt":
        cmd_str = subprocess.list2cmdline(cmd_list)
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        if result.returncode == 0:
            return

        print("Critical venv creation failure (shell fallback):", file=sys.stderr)
        print(result.stderr.strip() or result.stdout.strip() or "[no output]", file=sys.stderr)

    raise SystemExit(1)


def install_swspotify_compat(venv_python: Path) -> None:
    """Installs SwSpotify on Windows + Python 3.12+ by bypassing old pywin32 pin."""
    print("Installing compatible package set for local mode (SwSpotify)...")
    subprocess.check_call([
        str(venv_python), "-m", "pip", "install",
        "--require-virtualenv",
        "flask>=2.3,<3.0",
        "Flask-Cors>=3.0.10,<4.0.0",
        "pywin32>=306",
    ])
    subprocess.check_call([
        str(venv_python), "-m", "pip", "install",
        "--require-virtualenv",
        "swspotify==1.2.3",
        "--no-deps",
    ])


def pip_install_requirements(venv_dir: Path, req_file: Path) -> None:
    venv_python, _ = venv_paths(venv_dir)

    subprocess.check_call([
        str(venv_python), "-m", "pip", "install", "--upgrade",
        "pip", "setuptools", "wheel",
    ])

    if req_file.is_file():
        print(f"Installing dependencies from {req_file.name} ...")
        subprocess.check_call([
            str(venv_python), "-m", "pip", "install",
            "--require-virtualenv",
            "-r", str(req_file),
        ])

        venv_version = get_python_version([str(venv_python)])
        if os.name == "nt" and venv_version and venv_version >= (3, 12, 0):
            install_swspotify_compat(venv_python)
    else:
        print(f"File {req_file.name} not found, dependency install skipped.")


def is_running_inside_target_venv(venv_dir: Path) -> bool:
    venv_python, _ = venv_paths(venv_dir)
    try:
        return Path(sys.executable).resolve() == venv_python.resolve()
    except FileNotFoundError:
        return False



def get_venv_python_version(venv_dir: Path) -> Optional[tuple[int, int, int]]:
    venv_python, _ = venv_paths(venv_dir)
    if not venv_python.exists():
        return None
    return get_python_version([str(venv_python)])

def ensure_env_and_reexec() -> None:
    here = Path(__file__).resolve().parent.parent
    script = here / "run.py"
    venv_dir = here / VENVDIR_NAME
    req_path = here / REQUIREMENTS_FILE

    if REENTER_FLAG in sys.argv:
        return

    if venv_dir.exists() and is_running_inside_target_venv(venv_dir):
        return

    if not script.is_file():
        raise FileNotFoundError(f"Startup file not found: {script}")

    print("[bootstrap] Setting up isolated environment...", flush=True)

    python_cmd, version, source = detect_best_python()
    print(
        f"Selected interpreter: {source} | Python {format_version(version)} "
        f"({describe_version_choice(version)})"
    )

    if version[0] == MAX_TESTED_MAJOR and version[1] > MAX_TESTED_MINOR:
        print(
            "Warning: using a newer-than-tested version. "
            "Python 3.12 is recommended for this project.",
            file=sys.stderr,
        )

    rebuild_venv = False
    if venv_dir.exists():
        venv_version = get_venv_python_version(venv_dir)
        if venv_version is None:
            print("Existing venv is broken or incomplete and will be recreated.")
            rebuild_venv = True
        elif (venv_version[0], venv_version[1]) != (version[0], version[1]):
            print(
                "Existing venv uses different Python version: "
                f"{format_version(venv_version)}. Required {format_version(version)}."
            )
            rebuild_venv = True
        elif not is_supported(venv_version):
            print(
                "Existing venv uses unsupported Python version: "
                f"{format_version(venv_version)}."
            )
            rebuild_venv = True

    if not venv_dir.exists() or rebuild_venv:
        print(f"Creating venv: {venv_dir}")
        create_venv(venv_dir, python_cmd)
    else:
        print(f"Using existing venv: {venv_dir}")
    print("Installing packages...")
    pip_install_requirements(venv_dir, req_path)

    venv_python, _ = venv_paths(venv_dir)
    new_argv = [str(venv_python), str(script), REENTER_FLAG, *sys.argv[1:]]

    print(f"[bootstrap] Re-executing in venv: {venv_python}\n")

    if os.name == "nt":
        # On Windows, re-launch via subprocess without shell so paths with
        # spaces (e.g. "Python is trash") stay intact.
        completed = subprocess.run(new_argv, check=False)
        raise SystemExit(completed.returncode)

    os.execv(str(venv_python), new_argv)


if __name__ == "__main__":
    try:
        ensure_env_and_reexec()
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Bootstrap error:\n{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)



