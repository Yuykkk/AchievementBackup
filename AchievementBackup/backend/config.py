import os
import winreg
import json

def get_steam_path():
    env_path = os.environ.get("ACHIEVEMENTBACKUP_STEAM_PATH")
    if env_path:
        return env_path.replace("/", "\\")
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        path, _ = winreg.QueryValueEx(key, "SteamPath")
        winreg.CloseKey(key)
        return path.replace("/", "\\")
    except:
        return os.getcwd()

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(PLUGIN_DIR)
PROFILE_ROOT = os.path.join(PLUGIN_ROOT, "profile")
PROFILE_HISTORY_ROOT = os.path.join(PROFILE_ROOT, "history")
root_user_config_file = os.path.join(PLUGIN_DIR, "user_config.json")
legacy_root_user_config_file = os.path.join(PLUGIN_ROOT, "user_config.json")
user_config_file = os.path.join(PROFILE_ROOT, "user_config.json")
decisions_file = os.path.join(PROFILE_ROOT, "decisions.json")
pending_file = os.path.join(PLUGIN_DIR, "pending.json")
LOG_ROOT = os.path.join(PLUGIN_ROOT, "logs")
ACTIVITY_LOG = os.path.join(LOG_ROOT, "activity.log")
SESSION_STATE_FILE = os.path.join(LOG_ROOT, "session_state.json")
RESTORE_FLAG_FILE = os.path.join(LOG_ROOT, "restore_in_progress.flag")

SERVER_PORT = 9999
STEAM_PATH = get_steam_path()

DEFAULT_DECISIONS = {
    "name": "AchievementBackup",
    "purpose": "Guardar preferencias e decisoes do usuario fora do codigo do plugin.",
    "ui": {
        "confirmations": "Usar modais proprios do AchievementBackup em vez de alerts/confirms nativos da Steam.",
        "restore_capture_message": "Explicar que capturas restauram somente o jogo selecionado e nao afetam outros jogos.",
        "technical_sheet": "Manter botao Ficha Tecnica para explicar de onde vem userdata, stats, saves, stplug-in e config lua.",
    },
    "backup_behavior": {
        "default_mode": "semi",
        "automatic_requires_warning": True,
        "captures_are_manual": True,
        "capture_restore_safety": "Antes de sobrescrever arquivos do jogo, criar copia em backups/restore-safety.",
    },
    "saved_preferences": [
        "theme",
        "backup_mode",
        "hotkey",
        "broad_external_scan",
        "backup_all_external_saves",
        "use_save_location_api",
        "ignored_appids",
        "auto_mode_warning_ack",
        "backup_path",
    ],
}

DEFAULT_USER_CONFIG = {
    "backup_mode": "semi",
    "semi_auto": True,
    "theme": "blue",
    "use_save_location_api": True,
    "broad_external_scan": False,
    "backup_all_external_saves": False,
    "auto_mode_warning_ack": False,
    "ignored_appids": [],
}

PERSISTED_CONFIG_KEYS = set(DEFAULT_USER_CONFIG.keys()) | {
    "hotkey_enabled",
    "hotkey_mod",
    "hotkey_vk",
    "hotkey_str",
    "backup_path",
}


def read_json_file(path):
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except:
        pass
    return {}


def normalize_user_config(data):
    cfg = dict(DEFAULT_USER_CONFIG)
    had_backup_mode = isinstance(data, dict) and "backup_mode" in data
    had_semi_auto = isinstance(data, dict) and "semi_auto" in data
    if isinstance(data, dict):
        for key, value in data.items():
            if key in PERSISTED_CONFIG_KEYS:
                cfg[key] = value

    if not had_backup_mode and had_semi_auto:
        cfg["backup_mode"] = "semi" if cfg.get("semi_auto", True) else "manual"
    mode = str(cfg.get("backup_mode") or ("semi" if cfg.get("semi_auto", True) else "manual"))
    if mode not in ("auto", "semi", "manual"):
        mode = "semi"
    cfg["backup_mode"] = mode
    cfg["semi_auto"] = mode == "semi"

    theme = str(cfg.get("theme") or "blue")
    cfg["theme"] = theme if theme in ("red", "purple", "blue", "green") else "blue"

    for key in ("use_save_location_api", "broad_external_scan", "backup_all_external_saves", "auto_mode_warning_ack"):
        cfg[key] = bool(cfg.get(key))

    raw_ignored = cfg.get("ignored_appids") or []
    if not isinstance(raw_ignored, list):
        raw_ignored = []
    cfg["ignored_appids"] = sorted({str(v) for v in raw_ignored if str(v).isdigit()}, key=lambda x: int(x))

    backup_path = cfg.get("backup_path")
    if isinstance(backup_path, str):
        backup_path = os.path.expandvars(os.path.expanduser(backup_path.strip()))
        cfg["backup_path"] = os.path.abspath(backup_path) if backup_path else ""
    else:
        cfg["backup_path"] = ""

    return cfg


def write_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def backup_profile_config(config):
    try:
        os.makedirs(PROFILE_HISTORY_ROOT, exist_ok=True)
        stamp = __import__("datetime").datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        history_path = os.path.join(PROFILE_HISTORY_ROOT, f"user_config_{stamp}.json")
        write_json_file(history_path, config)
        entries = sorted(
            [os.path.join(PROFILE_HISTORY_ROOT, name) for name in os.listdir(PROFILE_HISTORY_ROOT) if name.endswith(".json")],
            key=lambda path: os.path.getmtime(path),
            reverse=True,
        )
        for old in entries[25:]:
            try:
                os.remove(old)
            except:
                pass
    except:
        pass


def save_user_config(config, make_history=True):
    cfg = normalize_user_config(config)
    ensure_profile()
    if make_history:
        backup_profile_config(cfg)
    write_json_file(user_config_file, cfg)
    try:
        write_json_file(root_user_config_file, cfg)
    except:
        pass
    return cfg


def ensure_profile():
    try:
        os.makedirs(PROFILE_ROOT, exist_ok=True)
        candidates = [
            read_json_file(legacy_root_user_config_file),
            read_json_file(root_user_config_file),
            read_json_file(user_config_file),
        ]
        merged = dict(DEFAULT_USER_CONFIG)
        ignored_appids = set()
        for data in candidates:
            if isinstance(data, dict):
                ignored_appids |= set(str(v) for v in data.get("ignored_appids") or [] if str(v).isdigit())
                for key, value in data.items():
                    if key in PERSISTED_CONFIG_KEYS and key != "ignored_appids":
                        merged[key] = value
        merged["ignored_appids"] = sorted(ignored_appids, key=lambda x: int(x))
        merged = normalize_user_config(merged)
        if read_json_file(user_config_file) != merged:
            write_json_file(user_config_file, merged)
        if read_json_file(root_user_config_file) != merged:
            try:
                write_json_file(root_user_config_file, merged)
            except:
                pass
        if not os.path.exists(decisions_file):
            with open(decisions_file, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_DECISIONS, f, ensure_ascii=False, indent=2)
    except:
        pass

def load_user_config():
    ensure_profile()
    return normalize_user_config(read_json_file(user_config_file))

ensure_profile()

def ignored_appids():
    cfg = load_user_config()
    values = cfg.get("ignored_appids") or []
    if not isinstance(values, list):
        return set()
    return {str(v) for v in values if str(v).isdigit()}

def is_ignored_appid(appid):
    return str(appid or "") in ignored_appids()

def restore_terminal_color():
    theme = str(load_user_config().get("theme") or "red").lower()
    return {
        "red": "0C",
        "purple": "0D",
        "blue": "0B",
        "green": "0A",
    }.get(theme, "0C")

def get_backup_root():
    cfg = load_user_config()
    backup_path = cfg.get("backup_path")
    if isinstance(backup_path, str) and backup_path.strip():
        return backup_path
    return os.path.join(PLUGIN_ROOT, "backups")

def default_backup_root():
    return os.path.join(PLUGIN_ROOT, "backups")

def refresh_backup_root():
    global BACKUP_ROOT
    BACKUP_ROOT = get_backup_root()
    return BACKUP_ROOT

BACKUP_ROOT = get_backup_root()

BACKUP_TARGETS = [
    {"src": os.path.join(STEAM_PATH, "userdata"), "name": "userdata"},
    
    {"src": os.path.join(STEAM_PATH, "appcache", "stats"), "name": "appcache_stats"},
    
    {"src": os.path.join(STEAM_PATH, "depotcache"), "name": "depotcache"},

    {"src": os.path.join(STEAM_PATH, "config", "lua"), "name": "lua"},

    {"src": os.path.join(STEAM_PATH, "config", "stplug-in"), "name": "stplug-in"}
]

UI_THEME = {
    "title": "AchievementBackup",
    "bg": "#101014",
    "accent": "#8b5cf6"
}
