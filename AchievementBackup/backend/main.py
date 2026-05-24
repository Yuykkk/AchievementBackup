import os
import shutil
import sys
import threading
import Millennium

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from monitor import BackupManager
from server import start_server
from hotkey import HotkeyManager
from updater import start_auto_update

WEBKIT_DIR_NAME = "AchievementBackup"
WEBKIT_JS_FILE = "index.js"

def find_plugin_root():
    current = os.path.abspath(__file__)
    for _ in range(4):
        current = os.path.dirname(current)
        if os.path.exists(os.path.join(current, "plugin.json")):
            return current
    return os.path.dirname(os.path.abspath(__file__))

def copy_webkit_ui(plugin_root):
    source = os.path.join(plugin_root, "public", WEBKIT_JS_FILE)
    if not os.path.exists(source):
        print(f"[AchievementBackup] UI nao encontrada: {source}")
        return ""

    try:
        steam_root = Millennium.steam_path()
    except Exception as exc:
        print(f"[AchievementBackup] Nao foi possivel localizar Steam pelo Millennium: {exc}")
        steam_root = ""

    if not steam_root:
        return source

    target_dir = os.path.join(steam_root, "steamui", WEBKIT_DIR_NAME)
    target = os.path.join(target_dir, WEBKIT_JS_FILE)
    try:
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(source, target)
        print(f"[AchievementBackup] UI copiada para SteamUI: {target}")
        return os.path.join(WEBKIT_DIR_NAME, WEBKIT_JS_FILE).replace("\\", "/")
    except Exception as exc:
        print(f"[AchievementBackup] Falha ao copiar UI para SteamUI: {exc}")
        return source

class Plugin:
    def __init__(self):
        self.monitor = None
        self.hotkey = None

    def _load(self):
        print("[AchievementBackup] Carregando plugin...")
        start_auto_update()

        # Carregar UI
        plugin_root = find_plugin_root()
        js_path = copy_webkit_ui(plugin_root)
        if js_path:
            try:
                Millennium.add_browser_js(js_path)
                print(f"[AchievementBackup] UI injetada: {js_path}")
            except Exception as exc:
                print(f"[AchievementBackup] Falha ao injetar UI principal: {exc}")
                fallback = os.path.join(plugin_root, "public", WEBKIT_JS_FILE)
                if fallback != js_path and os.path.exists(fallback):
                    try:
                        Millennium.add_browser_js(fallback)
                        print(f"[AchievementBackup] UI injetada por fallback: {fallback}")
                    except Exception as fallback_exc:
                        print(f"[AchievementBackup] Falha no fallback da UI: {fallback_exc}")

        # Iniciar Monitor
        self.monitor = BackupManager()
        self.monitor.start()

        # Iniciar Hotkey Manager (Passar callback para o monitor)
        def _hk_callback():
            if self.monitor:
                self.monitor.force_backup()
        
        self.hotkey = HotkeyManager(_hk_callback)
        # Configurar hotkey inicial (será atualizada pelo servidor se config existir)
        # O servidor vai ler o user_config e chamar hotkey.update()
        
        # Iniciar Servidor (Passar self para acesso ao hotkey manager)
        self.server_thread = threading.Thread(target=start_server, args=(self,), daemon=True)
        self.server_thread.start()

        Millennium.ready()

    def _unload(self):
        print("[AchievementBackup] Descarregando...")
        if self.monitor:
            self.monitor.stop()
        if self.hotkey:
            self.hotkey.stop()

plugin = Plugin()
