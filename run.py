import sys
from highway_to_hell_engine.bootstrap import ensure_env_and_reexec


def _has_arg(prefix: str) -> bool:
    return any(arg == prefix or arg.startswith(prefix + "=") for arg in sys.argv)


def _get_arg_value(prefix: str) -> str | None:
    for i, arg in enumerate(sys.argv):
        if arg == prefix and i + 1 < len(sys.argv):
            return sys.argv[i + 1].strip()
        if arg.startswith(prefix + "="):
            return arg.split("=", 1)[1].strip()
    return None


if __name__ == "__main__":
    # First run (without re-entry flag): ask for language first, then mode.
    if "--__highway_to_hell_engine__" not in sys.argv:
        lang = (_get_arg_value("--lang") or "").lower()
        if lang not in {"en", "ru"}:
            print("\nChoose language / Выберите язык:")
            print("1. English (default)")
            print("2. Русский")
            choice = input("Enter 1 or 2 [1]: ").strip()
            if choice == "2":
                lang = "ru"
            else:
                lang = "en"
            sys.argv.append(f"--lang={lang}")

        if not _has_arg("--mode"):
            if lang == "ru":
                print("\nВыберите режим работы:")
                print("1. API (требуется Spotify Premium)")
                print("2. Local (без Premium, использует локальный клиент Spotify)")
                choice = input("Введите 1 или 2 [1]: ").strip()
                if choice == "2":
                    mode = "local"
                else:
                    mode = "api"
            else:
                print("\nChoose operation mode:")
                print("1. API (requires Spotify Premium)")
                print("2. Local (no Premium, uses local Spotify client)")
                choice = input("Enter 1 or 2 [1]: ").strip()
                if choice == "2":
                    mode = "local"
                else:
                    mode = "api"
            sys.argv.append(f"--mode={mode}")

    ensure_env_and_reexec()

    if "--__highway_to_hell_engine__" in sys.argv:
        sys.argv.remove("--__highway_to_hell_engine__")

    import runpy

    runpy.run_module("highway_to_hell_engine", run_name="__main__")
