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

import hashlib
import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Iterable, Optional

VENVDIR_NAME = "highway_to_hell_engine_venv"
REENTER_FLAG = "--__highway_to_hell_engine__"
REQUIREMENTS_FILE = "requirements.txt"
STATE_FILE_NAME = ".bootstrap_state.json"
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


def _get_lang_from_argv() -> str:
    for i, arg in enumerate(sys.argv):
        if arg == "--lang" and i + 1 < len(sys.argv):
            value = sys.argv[i + 1].strip().lower()
            return "ru" if value == "ru" else "en"
        if arg.startswith("--lang="):
            value = arg.split("=", 1)[1].strip().lower()
            return "ru" if value == "ru" else "en"
    return "en"


def _msg(lang: str, en: str, ru: str) -> str:
    return ru if lang == "ru" else en


def _render_progress(step: int, total: int, label: str) -> None:
    width = 28
    done = int((step / total) * width) if total > 0 else width
    bar = "#" * done + "-" * (width - done)
    print(f"[bootstrap] [{bar}] {step}/{total} {label}", flush=True)


def _run_step(cmd: list[str], lang: str, step_name_en: str, step_name_ru: str, timeout: int = 300) -> None:
    step_name = _msg(lang, step_name_en, step_name_ru)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode == 0:
        return

    print(_msg(lang, f"[bootstrap] Failed: {step_name}", f"[bootstrap] Ошибка: {step_name}"), file=sys.stderr)

    combined = (result.stderr or "") + "\n" + (result.stdout or "")
    lines = [line for line in combined.splitlines() if line.strip()]
    if lines:
        tail = lines[-12:]
        print("\n".join(tail), file=sys.stderr)

    raise SystemExit(result.returncode)


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


def _state_path(venv_dir: Path) -> Path:
    return venv_dir / STATE_FILE_NAME


def _requirements_hash(req_file: Path) -> str:
    if not req_file.is_file():
        return "missing"
    return hashlib.sha256(req_file.read_bytes()).hexdigest()


def _load_state(venv_dir: Path) -> dict:
    path = _state_path(venv_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(venv_dir: Path, state: dict) -> None:
    path = _state_path(venv_dir)
    path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def _build_state(venv_dir: Path, req_file: Path) -> dict:
    venv_python, _ = venv_paths(venv_dir)
    version = get_python_version([str(venv_python)])
    return {
        "requirements_hash": _requirements_hash(req_file),
        "venv_python_version": format_version(version) if version else "unknown",
        "platform": os.name,
    }


def _has_package(venv_python: Path, package_name: str) -> bool:
    return run_capture([str(venv_python), "-m", "pip", "show", package_name], timeout=8) is not None


def _deps_are_current(venv_dir: Path, req_file: Path) -> bool:
    venv_python, _ = venv_paths(venv_dir)
    if not venv_python.exists():
        return False

    saved = _load_state(venv_dir)
    current = _build_state(venv_dir, req_file)
    if saved != current:
        return False

    if not _has_package(venv_python, "spotipy"):
        return False

    venv_version = get_python_version([str(venv_python)])
    if os.name == "nt" and venv_version and venv_version >= (3, 12, 0):
        if not _has_package(venv_python, "swspotify"):
            return False

    return True


def install_swspotify_compat(venv_python: Path, lang: str) -> None:
    _run_step(
        [
            str(venv_python), "-m", "pip", "install",
            "--disable-pip-version-check",
            "--progress-bar", "off",
            "--require-virtualenv",
            "-q",
            "flask>=2.3,<3.0",
            "Flask-Cors>=3.0.10,<4.0.0",
            "pywin32>=306",
        ],
        lang,
        "Installing Windows compatibility dependencies",
        "Установка зависимостей совместимости Windows",
    )
    _run_step(
        [
            str(venv_python), "-m", "pip", "install",
            "--disable-pip-version-check",
            "--progress-bar", "off",
            "--require-virtualenv",
            "-q",
            "swspotify==1.2.3",
            "--no-deps",
        ],
        lang,
        "Installing SwSpotify",
        "Установка SwSpotify",
    )


def pip_install_requirements(venv_dir: Path, req_file: Path, lang: str, force: bool = False) -> None:
    if not force and _deps_are_current(venv_dir, req_file):
        print(_msg(lang, "[bootstrap] Dependencies are up to date.", "[bootstrap] Зависимости уже актуальны."))
        return

    venv_python, _ = venv_paths(venv_dir)
    venv_version = get_python_version([str(venv_python)])

    total_steps = 2
    needs_swspotify = os.name == "nt" and venv_version and venv_version >= (3, 12, 0)
    if needs_swspotify:
        total_steps = 3

    print(_msg(lang, "[bootstrap] Installing dependencies...", "[bootstrap] Установка зависимостей..."), flush=True)

    _run_step(
        [
            str(venv_python), "-m", "pip", "install", "--upgrade",
            "--disable-pip-version-check",
            "--progress-bar", "off",
            "-q",
            "pip", "setuptools", "wheel",
        ],
        lang,
        "Updating pip tooling",
        "Обновление pip-инструментов",
    )
    _render_progress(1, total_steps, _msg(lang, "Updating pip tooling", "Обновление pip-инструментов"))

    if req_file.is_file():
        _run_step(
            [
                str(venv_python), "-m", "pip", "install",
                "--disable-pip-version-check",
                "--progress-bar", "off",
                "--require-virtualenv",
                "-q",
                "-r", str(req_file),
            ],
            lang,
            "Installing packages from requirements.txt",
            "Установка пакетов из requirements.txt",
        )
        _render_progress(2, total_steps, _msg(lang, "requirements.txt installed", "requirements.txt установлен"))
    else:
        print(_msg(lang, f"File {req_file.name} not found, skipping.", f"Файл {req_file.name} не найден, шаг пропущен."))
        _render_progress(2, total_steps, _msg(lang, "requirements step skipped", "шаг requirements пропущен"))

    if needs_swspotify:
        install_swspotify_compat(venv_python, lang)
        _render_progress(3, total_steps, _msg(lang, "Windows compatibility packages installed", "Пакеты совместимости Windows установлены"))

    _save_state(venv_dir, _build_state(venv_dir, req_file))


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
    lang = _get_lang_from_argv()

    if REENTER_FLAG in sys.argv:
        return

    if venv_dir.exists() and is_running_inside_target_venv(venv_dir):
        return

    if not script.is_file():
        raise FileNotFoundError(f"Startup file not found: {script}")

    print(_msg(lang, "[bootstrap] Setting up isolated environment...", "[bootstrap] Настройка изолированного окружения..."), flush=True)

    python_cmd, version, source = detect_best_python()
    print(
        _msg(
            lang,
            f"Selected interpreter: {source} | Python {format_version(version)} ({describe_version_choice(version)})",
            f"Выбран интерпретатор: {source} | Python {format_version(version)} ({describe_version_choice(version)})",
        )
    )

    if version[0] == MAX_TESTED_MAJOR and version[1] > MAX_TESTED_MINOR:
        print(
            _msg(
                lang,
                "Warning: using a newer-than-tested version. Python 3.12 is recommended.",
                "Внимание: используется версия новее протестированной. Рекомендуется Python 3.12.",
            ),
            file=sys.stderr,
        )

    rebuild_venv = False
    if venv_dir.exists():
        venv_version = get_venv_python_version(venv_dir)
        if venv_version is None:
            print(_msg(lang, "Existing venv is broken and will be recreated.", "Существующий venv поврежден и будет пересоздан."))
            rebuild_venv = True
        elif (venv_version[0], venv_version[1]) != (version[0], version[1]):
            print(
                _msg(
                    lang,
                    f"Existing venv uses different Python: {format_version(venv_version)}. Required {format_version(version)}.",
                    f"Существующий venv использует другой Python: {format_version(venv_version)}. Нужен {format_version(version)}.",
                )
            )
            rebuild_venv = True
        elif not is_supported(venv_version):
            print(
                _msg(
                    lang,
                    f"Existing venv uses unsupported Python: {format_version(venv_version)}.",
                    f"Существующий venv использует неподдерживаемый Python: {format_version(venv_version)}.",
                )
            )
            rebuild_venv = True

    if not venv_dir.exists() or rebuild_venv:
        print(_msg(lang, f"Creating venv: {venv_dir}", f"Создание venv: {venv_dir}"))
        create_venv(venv_dir, python_cmd)
    else:
        print(_msg(lang, f"Using existing venv: {venv_dir}", f"Используется существующий venv: {venv_dir}"))

    pip_install_requirements(venv_dir, req_path, lang=lang, force=rebuild_venv)

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
