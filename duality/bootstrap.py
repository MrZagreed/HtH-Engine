import os, sys, time, subprocess, json
from pathlib import Path
from typing import Tuple

VENVDIR_NAME = "duality_venv"
REENTER_FLAG = "--__duality__"
REQUIREMENTS_FILE = "requirements.txt"

def venv_paths(venv_dir: Path) -> Tuple[Path, Path]:
    if os.name == "nt":
        py = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        py = venv_dir / "bin" / "python"
        pip = venv_dir / "bin" / "pip"
    return py, pip

def _is_msstore_python() -> bool:
    # Грубая эвристика по пути запускаемого интерпретатора
    exe = Path(sys.executable).resolve().as_posix().lower()
    return "microsoft" in exe or "windowsapps" in exe

def _detect_best_python() -> str:
    """
    На Windows пытаемся найти самый новый Python через 'py -0p'.
    Если недоступно, остаемся на текущем интерпретаторе.
    На *nix просто возвращаем текущий.
    """
    if os.name == "nt":
        try:
            out = subprocess.check_output(["py", "-0p"], text=True, timeout=5)
            paths = [line.strip() for line in out.splitlines() if line.strip()]
            # Выбираем последний (обычно самый новый)
            if paths:
                return paths[-1]
        except Exception:
            pass
    return sys.executable

def _create_venv(venv_dir: Path, python_exe: str) -> None:
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    cmd = [python_exe, "-m", "venv", str(venv_dir)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Не удалось создать venv: {res.stderr[:400]}")

def _pip_install_requirements(venv_dir: Path, req_file: Path) -> None:
    py, pip = venv_paths(venv_dir)
    # Обновляем pip и wheel
    subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    # Устанавливаем зависимости из файла
    if req_file.exists():
        subprocess.check_call([str(py), "-m", "pip", "install", "-r", str(req_file)])
    else:
        # Фоллбэк: ничего не устанавливаем, но это странно.
        pass

def _diagnostics(venv_dir: Path, req_file: Path) -> dict:
    py, pip = venv_paths(venv_dir)
    wants = []
    if req_file.exists():
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            wants.append(line.split(";",1)[0].strip())
    code = f"""
import importlib, json, pkgutil
mods = {wants!r}
res = {{}}
for m in mods:
    name = m.split("==")[0].split(">=")[0].split("<")[0].strip()
    found = pkgutil.find_loader(name) is not None
    info = {{"found": found}}
    if found:
        try:
            mod = importlib.import_module(name)
            info["version"] = getattr(mod, "__version__", "unknown")
        except Exception as e:
            info["version"] = "unknown"
            info["error"] = str(e)
    res[name] = info
print(json.dumps(res, ensure_ascii=False))
"""
    out = subprocess.check_output([str(py), "-c", code], text=True, timeout=30)
    return json.loads(out)

def ensure_env_and_reexec() -> None:
    """
    Один клик: создаем venv, ставим зависимости из requirements.txt,
    делаем первичную диагностику и перезапускаем скрипт уже в venv.
    Также пытаемся выбрать самую свежую версию Python (актуально для MS Store).
    """
    here = Path(__file__).resolve().parent.parent
    script = here / "run.py"
    venv_dir = here / VENVDIR_NAME
    req = here / REQUIREMENTS_FILE

    # Если это уже повторный вход из venv — просто выходим.
    if REENTER_FLAG in sys.argv:
        return

    # Если мы уже внутри нужного venv — продолжаем.
    if venv_dir.exists():
        py, _ = venv_paths(venv_dir)
        if Path(sys.executable).resolve() == py.resolve():
            return

    # Пытаемся использовать самую свежую установленную версию Python
    best_python = _detect_best_python()
    want_recreate = not venv_dir.exists()

    if want_recreate:
        _create_venv(venv_dir, best_python)

    # Устанавливаем зависимости из requirements
    _pip_install_requirements(venv_dir, req)

    # Прогоняем диагностику
    diag = _diagnostics(venv_dir, req)
    (here / "logs").mkdir(exist_ok=True)
    (here / "logs" / "env_diagnostics.json").write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")

    # Перезапуск в venv
    py, _ = venv_paths(venv_dir)
    new_argv = [str(py), str(script), REENTER_FLAG] + sys.argv[1:]
    if os.name == "nt":
        cmd = " ".join(f'"{a}"' if " " in a else a for a in new_argv)
        subprocess.Popen(cmd, shell=True)
    else:
        subprocess.Popen(new_argv)
    time.sleep(1.5)
    sys.exit(0)
