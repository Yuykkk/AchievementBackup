import os
import sys
import time
import traceback

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from hotkey import HotkeyManager
from monitor import BackupManager
from server import start_server
from updater import start_auto_update


def plugin_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log(message):
    try:
        root = plugin_root()
        logs = os.path.join(root, "logs")
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(logs, "runner.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + str(message) + "\n")
    except Exception:
        pass


class Runtime:
    def __init__(self):
        self.monitor = None
        self.hotkey = None


def main():
    runtime = Runtime()
    try:
        log("runner iniciado")
        start_auto_update()

        runtime.monitor = BackupManager()
        runtime.monitor.start()

        def hotkey_callback():
            if runtime.monitor:
                runtime.monitor.force_backup()

        runtime.hotkey = HotkeyManager(hotkey_callback)
        start_server(runtime)
    except KeyboardInterrupt:
        log("runner encerrado")
    except Exception:
        log(traceback.format_exc())
        raise
    finally:
        try:
            if runtime.monitor:
                runtime.monitor.stop()
        except Exception:
            pass
        try:
            if runtime.hotkey:
                runtime.hotkey.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
