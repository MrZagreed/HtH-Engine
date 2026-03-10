import sys
from duality.bootstrap import ensure_env_and_reexec

if __name__ == "__main__":
    # Если это первый запуск (без флага перезапуска), предложим выбор режима
    if "--__duality__" not in sys.argv:
        if not any(arg.startswith("--mode") for arg in sys.argv):
            print("\nВыберите режим работы:")
            print("1. API (требуется Spotify Premium)")
            print("2. Локальный (без Premium, использует локальный клиент Spotify)")
            choice = input("Введите 1 или 2: ").strip()
            if choice == "1":
                mode = "api"
            elif choice == "2":
                mode = "local"
            else:
                print("Неверный выбор, используется режим API по умолчанию.")
                mode = "api"
            sys.argv.append(f"--mode={mode}")

    ensure_env_and_reexec()

    if "--__duality__" in sys.argv:
        sys.argv.remove("--__duality__")

    import runpy
    runpy.run_module("duality", run_name="__main__")