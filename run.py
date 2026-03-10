import sys
from highway_to_hell_engine.bootstrap import ensure_env_and_reexec

if __name__ == "__main__":
    # First run (without re-entry flag): ask for operation mode
    if "--__highway_to_hell_engine__" not in sys.argv:
        if not any(arg.startswith("--mode") for arg in sys.argv):
            print("\nChoose operation mode:")
            print("1. API (requires Spotify Premium)")
            print("2. Local (no Premium, uses local Spotify client)")
            choice = input("Enter 1 or 2: ").strip()
            if choice == "1":
                mode = "api"
            elif choice == "2":
                mode = "local"
            else:
                print("Invalid choice. Using API mode by default.")
                mode = "api"
            sys.argv.append(f"--mode={mode}")

    ensure_env_and_reexec()

    if "--__highway_to_hell_engine__" in sys.argv:
        sys.argv.remove("--__highway_to_hell_engine__")

    import runpy
    runpy.run_module("highway_to_hell_engine", run_name="__main__")