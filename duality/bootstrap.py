#!/usr/bin/env python3
"""
Bootstrap: выбирает совместимый Python, создаёт venv, ставит зависимости
и перезапускает run.py внутри виртуального окружения.

Предпочтение версий:
- Python 3.12
- Python 3.11
- Python 3.10

Если подходящая версия через launcher `py` не найдена, используется текущий
интерпретатор только если он совместим по версии.
"""

from __future__ import annotations

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Iterable, Optional

VENVDIR_NAME = "duality_venv"
REENTER_FLAG = "--__duality__"
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
        return "предпочтительная"
    if is_supported(version):
        if version[0] == MAX_TESTED_MAJOR and version[1] > MAX_TESTED_MINOR:
            return "совместимая, но не проверенная"
        return "совместимая"
    return "несовместимая"


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
        candidates.append((current_version, current_cmd, "текущий интерпретатор"))

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
    ) or "ничего не найдено"
    raise RuntimeError(
        "Не найден совместимый Python. Нужен Python 3.10–3.12, лучше 3.12. "
        f"Обнаружено: {details}"
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

        print("Ошибка создания venv:", file=sys.stderr)
        print(result.stderr.strip() or result.stdout.strip() or "[нет вывода]", file=sys.stderr)
    except FileNotFoundError:
        print("Не удалось запустить выбранный интерпретатор для создания venv.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Создание venv превысило лимит времени.", file=sys.stderr)

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

        print("Критическая ошибка создания venv (fallback через shell):", file=sys.stderr)
        print(result.stderr.strip() or result.stdout.strip() or "[нет вывода]", file=sys.stderr)

    raise SystemExit(1)


def install_swspotify_compat(venv_python: Path) -> None:
    """Устанавливает SwSpotify на Windows + Python 3.12+, обходя старый пин pywin32."""
    print("Установка совместимого набора для локального режима (SwSpotify)...")
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
        print(f"Установка зависимостей из {req_file.name} ...")
        subprocess.check_call([
            str(venv_python), "-m", "pip", "install",
            "--require-virtualenv",
            "-r", str(req_file),
        ])

        venv_version = get_python_version([str(venv_python)])
        if os.name == "nt" and venv_version and venv_version >= (3, 12, 0):
            install_swspotify_compat(venv_python)
    else:
        print(f"Файл {req_file.name} не найден, установка зависимостей пропущена.")


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
        raise FileNotFoundError(f"Не найден файл запуска: {script}")

    print("[bootstrap] Настройка изолированного окружения...", flush=True)

    python_cmd, version, source = detect_best_python()
    print(
        f"Выбран интерпретатор: {source} | Python {format_version(version)} "
        f"({describe_version_choice(version)})"
    )

    if version[0] == MAX_TESTED_MAJOR and version[1] > MAX_TESTED_MINOR:
        print(
            "Предупреждение: используется версия новее проверенной. "
            "Для этого проекта предпочтителен Python 3.12.",
            file=sys.stderr,
        )

    rebuild_venv = False
    if venv_dir.exists():
        venv_version = get_venv_python_version(venv_dir)
        if venv_version is None:
            print("Существующий venv поврежден или неполон, будет пересоздан.")
            rebuild_venv = True
        elif (venv_version[0], venv_version[1]) != (version[0], version[1]):
            print(
                "Существующий venv использует другую версию Python: "
                f"{format_version(venv_version)}. Требуется {format_version(version)}."
            )
            rebuild_venv = True
        elif not is_supported(venv_version):
            print(
                "Существующий venv использует неподдерживаемую версию Python: "
                f"{format_version(venv_version)}."
            )
            rebuild_venv = True

    if not venv_dir.exists() or rebuild_venv:
        print(f"Создаем venv: {venv_dir}")
        create_venv(venv_dir, python_cmd)
    else:
        print(f"Используем существующий venv: {venv_dir}")
    print("Устанавливаем пакеты...")
    pip_install_requirements(venv_dir, req_path)

    venv_python, _ = venv_paths(venv_dir)
    new_argv = [str(venv_python), str(script), REENTER_FLAG, *sys.argv[1:]]

    print(f"[bootstrap] Перезапуск в venv: {venv_python}\n")

    if os.name == "nt":
        cmd = subprocess.list2cmdline(new_argv)
        subprocess.Popen(cmd, shell=True)
        time.sleep(2)
        raise SystemExit(0)

    os.execv(str(venv_python), new_argv)


if __name__ == "__main__":
    try:
        ensure_env_and_reexec()
    except KeyboardInterrupt:
        print("\nПрервано", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Ошибка bootstrap:\n{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)



