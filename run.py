import sys
from duality.bootstrap import ensure_env_and_reexec

if __name__ == "__main__":
    ensure_env_and_reexec()
    # После перезапуска выполнение перейдет в __main__ пакета:
    import runpy; runpy.run_module("duality", run_name="__main__")
