import json
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import winreg
from datetime import datetime

from config import ACTIVITY_LOG, BACKUP_ROOT, LOG_ROOT, PLUGIN_ROOT, RESTORE_FLAG_FILE, STEAM_PATH, is_ignored_appid, restore_terminal_color, user_config_file

ALLOWED_EXTENSIONS = {
    ".bin", ".dat", ".vdf", ".sav", ".save", ".json", ".cfg", ".ini", ".lua", ".xml", ".slot", ".profile",
    ".es3", ".bytes", ".prefs", ".db", ".sqlite", ".sqlite3", ".rpgsave", ".savegame", ".bak", ".txt", ".gs"
}
BLOCKED_EXTERNAL_EXTENSIONS = {
    ".exe", ".dll", ".pdb", ".mp4", ".mkv", ".avi", ".webm", ".png", ".jpg", ".jpeg", ".dds", ".wav", ".mp3", ".ogg",
    ".zip", ".rar", ".7z"
}
SAVE_DIR_NAMES = {"save", "saves", "saved", "savedata", "savegame", "savegames", "profile", "profiles", "userdata"}
GAME_NAME_STOPWORDS = {
    "the", "of", "and", "or", "a", "an", "to", "for", "with", "in",
    "directors", "director", "cut", "edition", "definitive", "complete",
    "remastered", "remaster", "deluxe", "ultimate", "tm", "r"
}
RECENT_SECONDS = 14 * 24 * 60 * 60
MAX_SNAPSHOT_BYTES = 768 * 1024 * 1024
MAX_FULL_EXTERNAL_BACKUP_BYTES = 20 * 1024 * 1024 * 1024
MANIFEST_URL = "https://raw.githubusercontent.com/mtkennerly/ludusavi-manifest/master/data/manifest.yaml"
MANIFEST_CACHE = os.path.join(PLUGIN_ROOT, "cache", "ludusavi_manifest.yaml")
MANIFEST_MAX_AGE = 14 * 24 * 60 * 60
_LUDUSAVI_MANIFEST = None
_LUDUSAVI_INDEX = None


def log_event(level, message):
    try:
        os.makedirs(LOG_ROOT, exist_ok=True)
        line = f"{datetime.now().isoformat(timespec='seconds')} [{level}] {message}\n"
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except:
        pass
    try:
        print(f"[AchievementBackup:{level}] {message}")
    except:
        pass


def ps_quote(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def console_python_executable():
    exe = sys.executable or ""
    base = os.path.basename(exe).lower()
    if base == "pythonw.exe":
        candidate = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(candidate):
            return candidate
    if exe and os.path.exists(exe):
        return exe
    return "py"


def steam_is_running():
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Get-Process steam -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Id",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=0x08000000,
        )
        return bool((result.stdout or "").strip())
    except Exception as e:
        log_event("WARN", f"Failed checking Steam process: {e}")
        return False


def start_steam_client(steam_exe):
    if not steam_exe or not os.path.exists(steam_exe):
        log_event("WARN", f"Steam executable not found: {steam_exe}")
        return False

    steam_dir = os.path.dirname(steam_exe) or STEAM_PATH
    attempts = []

    for label, starter in (
        ("popen", lambda: subprocess.Popen([steam_exe], cwd=steam_dir)),
        ("startfile", lambda: os.startfile(steam_exe)),
        (
            "powershell",
            lambda: subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"Start-Process -FilePath {ps_quote(steam_exe)} -WorkingDirectory {ps_quote(steam_dir)}",
                ],
                timeout=12,
                creationflags=0x08000000,
            ),
        ),
    ):
        try:
            starter()
            for _ in range(10):
                time.sleep(1)
                if steam_is_running():
                    return True
        except Exception as e:
            attempts.append(f"{label}: {e}")

    log_event("WARN", "Failed starting Steam after restore: " + " | ".join(attempts))
    return False


def sanitize(name):
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", str(name or "Unknown Game"))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Unknown Game"


def timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M")


def snapshot_root():
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    return BACKUP_ROOT


def achievements_root():
    return snapshot_root()


def unique_snapshot_dir(game_name):
    game_dir = os.path.join(achievements_root(), sanitize(game_name))
    os.makedirs(game_dir, exist_ok=True)
    base = timestamp()
    candidate = os.path.join(game_dir, base)
    idx = 2
    while os.path.exists(candidate):
        candidate = os.path.join(game_dir, f"{base}_{idx}")
        idx += 1
    return candidate


def normalize(path):
    return os.path.normpath(path)


def is_under(base, child):
    try:
        base_abs = os.path.abspath(base).lower()
        child_abs = os.path.abspath(child).lower()
        return child_abs == base_abs or child_abs.startswith(base_abs + os.sep)
    except:
        return False


def get_running_appid():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        val, _ = winreg.QueryValueEx(key, "RunningAppID")
        winreg.CloseKey(key)
        return int(val)
    except:
        return 0


def parse_acf_value(text, key):
    match = re.search(rf'"{re.escape(key)}"\s+"([^"]+)"', text, re.I)
    return match.group(1) if match else None


def steamapps_folders():
    folders = [os.path.join(STEAM_PATH, "steamapps")]
    vdf = os.path.join(STEAM_PATH, "steamapps", "libraryfolders.vdf")
    try:
        raw = open(vdf, "r", encoding="utf-8", errors="ignore").read()
        for match in re.finditer(r'"path"\s+"([^"]+)"', raw):
            steamapps = os.path.join(match.group(1).replace("\\\\", "\\"), "steamapps")
            if os.path.isdir(steamapps):
                folders.append(steamapps)
    except:
        pass
    return list(dict.fromkeys(folders))


def get_installed_app(appid, fallback_name=None):
    appid = str(appid)
    for steamapps in steamapps_folders():
        manifest = os.path.join(steamapps, f"appmanifest_{appid}.acf")
        if not os.path.exists(manifest):
            continue
        try:
            raw = open(manifest, "r", encoding="utf-8", errors="ignore").read()
            name = parse_acf_value(raw, "name") or fallback_name or f"AppID {appid}"
            installdir = parse_acf_value(raw, "installdir") or name
            return {
                "appid": appid,
                "name": name,
                "steamapps": steamapps,
                "common": os.path.join(steamapps, "common", installdir),
                "manifest": manifest,
            }
        except:
            pass
    return {"appid": appid, "name": fallback_name or f"AppID {appid}", "common": ""}


def installed_apps():
    apps = []
    for steamapps in steamapps_folders():
        try:
            for name in os.listdir(steamapps):
                match = re.match(r"appmanifest_(\d+)\.acf$", name, re.I)
                if not match:
                    continue
                appid = match.group(1)
                manifest = os.path.join(steamapps, name)
                raw = open(manifest, "r", encoding="utf-8", errors="ignore").read()
                game_name = parse_acf_value(raw, "name") or f"AppID {appid}"
                installdir = parse_acf_value(raw, "installdir") or game_name
                common = os.path.join(steamapps, "common", installdir)
                if os.path.isdir(common):
                    apps.append({
                        "appid": appid,
                        "name": game_name,
                        "steamapps": steamapps,
                        "common": common,
                        "manifest": manifest,
                    })
        except:
            pass
    unique = {}
    for app in apps:
        unique[str(app["appid"])] = app
    return list(unique.values())


def is_recent(path, window_seconds=RECENT_SECONDS):
    try:
        return (time.time() - os.path.getmtime(path)) <= window_seconds
    except:
        return False


def walk_limited(root, max_depth=12, max_files=5000):
    if not root or not os.path.exists(root):
        return
    root = os.path.abspath(root)
    count = 0
    for current, dirs, files in os.walk(root):
        rel = os.path.relpath(current, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= max_depth:
            dirs[:] = []
        for name in files:
            count += 1
            if count > max_files:
                return
            yield os.path.join(current, name)


def ext_ok(path):
    return os.path.splitext(path.lower())[1] in ALLOWED_EXTENSIONS


def external_file_ok(path):
    if os.path.basename(str(path or "")).lower() == "steam_autocloud.vdf":
        return False
    ext = os.path.splitext(path.lower())[1]
    if ext in BLOCKED_EXTERNAL_EXTENSIONS:
        return False
    if ext in ALLOWED_EXTENSIONS:
        return True
    try:
        size = os.path.getsize(path)
    except:
        return False
    return ext == "" and 0 < size <= 32 * 1024 * 1024


def norm_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def game_tokens(name):
    words = re.findall(r"[a-z0-9]+", str(name or "").lower())
    return [w for w in words if len(w) >= 3 and w not in GAME_NAME_STOPWORDS]


def path_parts(path):
    return [norm_key(part) for part in os.path.normpath(path).split(os.sep) if part]


def is_ignored_external_path(path):
    try:
        full = os.path.abspath(path)
        if is_under(BACKUP_ROOT, full) or is_under(PLUGIN_ROOT, full) or is_under(STEAM_PATH, full):
            return True
        temp_paths = [os.environ.get("TEMP"), os.environ.get("TMP")]
        if any(t and is_under(t, full) for t in temp_paths):
            return True
        parts = path_parts(full)
        if any(part in {"temp", "tmp", "cache", "caches", "crashdumps", "logs"} for part in parts):
            return True
        if "backups" in parts and any(part in {"achievementbackup", "achievementbackupclean"} for part in parts):
            return True
    except:
        return True
    return False


def external_base_dirs():
    bases = []
    user = os.environ.get("USERPROFILE") or ""
    docs = os.path.join(user, "Documents")
    onedrive_docs = os.path.join(user, "OneDrive", "Documents")
    for path in (
        docs,
        os.path.join(docs, "My Games"),
        onedrive_docs,
        os.path.join(onedrive_docs, "My Games"),
        os.path.join(user, "Saved Games"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("APPDATA"),
        os.path.join(os.environ.get("APPDATA") or "", "..", "LocalLow"),
    ):
        if path and os.path.isdir(path):
            bases.append(os.path.abspath(path))
    return list(dict.fromkeys(bases))


def looks_like_game_save_dir(path, app):
    name = app.get("name") or ""
    appid = str(app.get("appid") or "")
    lower_path = path.replace("\\", "/").lower()
    if appid and appid in lower_path:
        return True
    compact_path = norm_key(path)
    compact_name = norm_key(name)
    if compact_name and compact_name in compact_path:
        return True
    tokens = game_tokens(name)
    if len(tokens) >= 2 and all(token in compact_path for token in tokens[:2]):
        return True
    if len(tokens) >= 3 and sum(1 for token in tokens if token in compact_path) >= 3:
        return True
    return False


def find_external_save_roots(app):
    roots = []
    for base in external_base_dirs():
        try:
            base_lower = base.lower()
            if "locallow" in base_lower or "localappdata" in base_lower or "appdata" in base_lower:
                max_depth = 4
            elif "documents" in base_lower or "saved games" in base_lower:
                max_depth = 3
            else:
                max_depth = 2
            for current, dirs, _files in os.walk(base):
                dirs[:] = [d for d in dirs if not is_ignored_external_path(os.path.join(current, d))]
                if is_ignored_external_path(current):
                    dirs[:] = []
                    continue
                rel = os.path.relpath(current, base)
                depth = 0 if rel == "." else rel.count(os.sep) + 1
                if depth > max_depth:
                    dirs[:] = []
                    continue
                if current != base and looks_like_game_save_dir(current, app):
                    roots.append(current)
                    dirs[:] = []
                if len(roots) >= 12:
                    break
        except:
            pass
    return list(dict.fromkeys(os.path.abspath(root) for root in roots))


def external_source_label(source_root):
    source_root = os.path.abspath(source_root)
    friendly = os.path.basename(source_root) or "External"
    for base in external_base_dirs():
        if not is_under(base, source_root):
            continue
        base_norm = os.path.normpath(base).lower()
        user = (os.environ.get("USERPROFILE") or "").lower()
        if base_norm.endswith(os.path.normpath("Documents").lower()):
            base_name = "Documents"
        elif base_norm.endswith(os.path.normpath("Documents\\My Games").lower()):
            base_name = "Documents - My Games"
        elif base_norm.endswith(os.path.normpath("Saved Games").lower()):
            base_name = "Saved Games"
        elif os.environ.get("LOCALAPPDATA") and os.path.abspath(base).lower() == os.path.abspath(os.environ.get("LOCALAPPDATA")).lower():
            base_name = "AppData Local"
        elif os.environ.get("APPDATA") and os.path.abspath(base).lower() == os.path.abspath(os.environ.get("APPDATA")).lower():
            base_name = "AppData Roaming"
        elif "locallow" in base_norm:
            base_name = "AppData LocalLow"
        elif "onedrive" in base_norm and "documents" in base_norm:
            base_name = "OneDrive Documents"
        else:
            base_name = os.path.basename(base) or "External"
        rel = os.path.relpath(source_root, base)
        if rel != ".":
            first = rel.split(os.sep)[0]
            friendly = f"{base_name} - {first}"
        else:
            friendly = base_name
        break
    return sanitize(friendly)[:96]


def should_copy_stats(path, appid):
    lower = path.lower()
    return str(appid) in lower and os.path.splitext(lower)[1] in {".bin", ".dat", ".vdf"}


def should_copy_userdata(path, appid):
    lower = path.replace("\\", "/").lower()
    appid = str(appid)
    in_app_folder = "/userdata/" in lower and f"/{appid}/" in lower
    in_760 = "/userdata/" in lower and "/760/" in lower and appid in lower
    return (in_app_folder or in_760 or appid in lower) and ext_ok(path)


def userdata_config_mentions_appid(path, appid):
    try:
        if not ext_ok(path):
            return False
        if os.path.getsize(path) > 16 * 1024 * 1024:
            return False
        normalized = path.replace("\\", "/").lower()
        name = os.path.basename(normalized)
        if "/userdata/" not in normalized or "/config/" not in normalized:
            return False
        if name not in {"localconfig.vdf", "sharedconfig.vdf", "shortcuts.vdf"} and not name.endswith((".vdf", ".json")):
            return False
        needle = str(appid).encode("utf-8", errors="ignore")
        with open(path, "rb") as f:
            return needle in f.read()
    except:
        return False


def should_copy_luatools(path, appid):
    lower = path.lower()
    return str(appid) in lower and os.path.splitext(lower)[1] in {".json", ".cfg", ".ini", ".vdf", ".lua"}


def find_save_roots(app):
    roots = []
    common = app.get("common") or ""
    if not os.path.isdir(common):
        return roots
    for current, dirs, _files in os.walk(common):
        rel = os.path.relpath(current, common)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 4:
            dirs[:] = []
            continue
        for d in list(dirs):
            clean = re.sub(r"[^a-z0-9]", "", d.lower())
            if clean in SAVE_DIR_NAMES:
                roots.append(os.path.join(current, d))
        if len(roots) >= 24:
            break
    return roots


def classify_userdata_bucket(path):
    lower = path.replace("\\", "/").lower()
    name = os.path.basename(lower)
    if "achievement" in lower or "/librarycache/" in lower:
        return "achievements"
    if name.endswith((".sav", ".save")) or "/remote/" in lower:
        return "saves"
    return "userdata"


def add_candidate(candidates, seen, source, source_root, bucket, category, limits, require_recent=False, app=None):
    try:
        source = os.path.abspath(source)
        if source in seen or not is_under(source_root, source):
            return
        if require_recent and not is_recent(source):
            return
        size = os.path.getsize(source)
        if size <= 0 or size > 128 * 1024 * 1024:
            return
        max_bytes = int(limits.get("max_bytes") or MAX_SNAPSHOT_BYTES)
        if limits["bytes"] + size > max_bytes:
            limits["skipped"] += size
            return
        seen.add(source)
        limits["bytes"] += size
        entry = {
            "source": source,
            "sourceRoot": os.path.abspath(source_root),
            "bucket": bucket,
            "category": category,
            "relative": os.path.relpath(source, source_root),
            "size": size,
        }
        if app:
            entry["appid"] = str(app.get("appid") or "")
            entry["gameName"] = app.get("name") or ""
        candidates.append(entry)
    except Exception as e:
        log_event("WARN", f"candidate failed {source}: {e}")


def load_ludusavi_manifest_text():
    global _LUDUSAVI_MANIFEST
    if isinstance(_LUDUSAVI_MANIFEST, str):
        return _LUDUSAVI_MANIFEST
    try:
        os.makedirs(os.path.dirname(MANIFEST_CACHE), exist_ok=True)
        should_download = not os.path.exists(MANIFEST_CACHE) or (time.time() - os.path.getmtime(MANIFEST_CACHE)) > MANIFEST_MAX_AGE
        if should_download:
            req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "AchievementBackup/2.0"})
            with urllib.request.urlopen(req, timeout=8) as response:
                raw = response.read()
            with open(MANIFEST_CACHE, "wb") as f:
                f.write(raw)
            log_event("INFO", f"Ludusavi manifest cached: {MANIFEST_CACHE}")
        with open(MANIFEST_CACHE, "r", encoding="utf-8", errors="ignore") as f:
            _LUDUSAVI_MANIFEST = f.read()
    except Exception as e:
        log_event("WARN", f"Ludusavi manifest load failed: {e}")
        _LUDUSAVI_MANIFEST = ""
    return _LUDUSAVI_MANIFEST


def manifest_entry_for_appid(appid):
    global _LUDUSAVI_INDEX
    sid = str(appid or "")
    if _LUDUSAVI_INDEX is not None:
        return _LUDUSAVI_INDEX.get(sid, (None, None))
    text = load_ludusavi_manifest_text()
    _LUDUSAVI_INDEX = {}
    current_title = None
    block = []

    def flush(title, lines):
        if not title or not lines:
            return
        raw = "\n".join(lines)
        steam_ids = []
        in_steam = False
        for line in lines:
            if line.startswith("  steam:"):
                in_steam = True
                continue
            if in_steam and line.startswith("  ") and not line.startswith("    "):
                in_steam = False
            if in_steam:
                match = re.match(r'^\s{4}id:\s*"?(\d+)"?\s*$', line)
                if match:
                    steam_ids.append(match.group(1))
        if not steam_ids or "  steam:" not in raw:
            return
        files = {}
        in_files = False
        for line in lines:
            if line.startswith("  files:"):
                in_files = True
                continue
            if in_files and line.startswith("  ") and not line.startswith("    "):
                break
            if not in_files:
                continue
            match = re.match(r'^\s{4}(.+?):\s*$', line)
            if not match:
                continue
            key = match.group(1).strip().strip('"').strip("'")
            if key and not key.startswith("-") and "<" in key:
                files[key] = {}
        data = {"files": files, "steam": {"id": steam_ids[0]}}
        _LUDUSAVI_INDEX[str(steam_ids[0])] = (title, data)

    for line in text.splitlines():
        if line and not line.startswith(" ") and line.endswith(":"):
            flush(current_title, block)
            current_title = line[:-1].strip().strip('"').strip("'")
            block = []
        elif current_title:
            block.append(line)
    flush(current_title, block)
    return _LUDUSAVI_INDEX.get(sid, (None, None))


def steam_user_ids():
    ids = []
    userdata = os.path.join(STEAM_PATH, "userdata")
    try:
        for name in os.listdir(userdata):
            if name.isdigit() and os.path.isdir(os.path.join(userdata, name)):
                ids.append(name)
    except:
        pass
    return ids or ["*"]


def user_setting(name, default=None):
    try:
        if os.path.exists(user_config_file):
            with open(user_config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and name in data:
                return data.get(name)
    except:
        pass
    return default


def broad_external_scan_enabled():
    return bool(user_setting("broad_external_scan", False))


def save_location_api_enabled():
    return bool(user_setting("use_save_location_api", True))


def backup_all_external_saves_enabled():
    return bool(user_setting("backup_all_external_saves", False))


def manifest_allowed_base(path, app):
    if not path:
        return False
    full = os.path.abspath(path)
    allowed = [
        os.environ.get("USERPROFILE"),
        os.environ.get("APPDATA"),
        os.environ.get("LOCALAPPDATA"),
        os.path.join(os.environ.get("APPDATA") or "", "..", "LocalLow"),
        os.environ.get("PUBLIC"),
        os.environ.get("PROGRAMDATA"),
        STEAM_PATH,
        app.get("common"),
    ]
    return any(base and is_under(base, full) for base in allowed)


def resolve_manifest_pattern(pattern, app):
    if not isinstance(pattern, str) or pattern.startswith(("./", "../")):
        return []
    home = os.environ.get("USERPROFILE") or ""
    common = app.get("common") or ""
    root = os.path.dirname(app.get("steamapps") or os.path.join(STEAM_PATH, "steamapps"))
    game_dir = os.path.basename(common) if common else (app.get("name") or "")
    replacements = {
        "<home>": home,
        "<game>": game_dir,
        "<root>": root,
        "<base>": common,
        "<storeGameId>": str(app.get("appid") or ""),
        "<osUserName>": os.environ.get("USERNAME") or os.path.basename(home),
        "<winAppData>": os.environ.get("APPDATA") or "",
        "<winLocalAppData>": os.environ.get("LOCALAPPDATA") or "",
        "<winLocalAppDataLow>": os.path.join(home, "AppData", "LocalLow"),
        "<winDocuments>": os.path.join(home, "Documents"),
        "<winPublic>": os.environ.get("PUBLIC") or "",
        "<winProgramData>": os.environ.get("PROGRAMDATA") or "",
        "<winDir>": os.environ.get("WINDIR") or "",
    }
    patterns = [pattern]
    if "<storeUserId>" in pattern:
        patterns = [pattern.replace("<storeUserId>", user_id) for user_id in steam_user_ids()]
        patterns.append(pattern.replace("<storeUserId>", "*"))
    resolved = []
    for item in patterns:
        path = item.replace("/", os.sep)
        for token, value in replacements.items():
            path = path.replace(token, value)
        if "<" in path or ">" in path:
            continue
        resolved.append(os.path.expandvars(path))
    return list(dict.fromkeys(resolved))


def add_manifest_path_candidates(candidates, seen, pattern, app, limits):
    for resolved in resolve_manifest_pattern(pattern, app):
        if not manifest_allowed_base(resolved, app) or is_ignored_external_path(resolved):
            continue
        matches = glob.glob(resolved, recursive=True)
        if not matches and os.path.exists(resolved):
            matches = [resolved]
        for match in matches[:64]:
            if not manifest_allowed_base(match, app) or is_ignored_external_path(match):
                continue
            if os.path.isdir(match):
                source_root = match
                for file in walk_limited(match, max_depth=12, max_files=1600) or []:
                    if external_file_ok(file):
                        add_candidate(candidates, seen, file, source_root, "external-saves", "ludusavi-manifest", limits, app=app)
            elif os.path.isfile(match) and external_file_ok(match):
                add_candidate(candidates, seen, match, os.path.dirname(match), "external-saves", "ludusavi-manifest", limits, app=app)


def add_ludusavi_candidates(candidates, seen, app, limits):
    title, entry = manifest_entry_for_appid(app.get("appid"))
    if not entry:
        return 0
    before = len(candidates)
    files = entry.get("files") or {}
    if isinstance(files, dict):
        for pattern, meta in files.items():
            if isinstance(meta, dict):
                tags = [str(tag).lower() for tag in (meta.get("tags") or [])]
                if tags and not any(tag in {"save", "config"} for tag in tags):
                    continue
            add_manifest_path_candidates(candidates, seen, pattern, app, limits)
    added = len(candidates) - before
    log_event("API", f"Ludusavi manifest matched {title or app.get('name')} ({app.get('appid')}); added={added}")
    return added


def collect_files(appid, game_name=None):
    app = get_installed_app(appid, game_name)
    candidates = []
    seen = set()
    limits = {"bytes": 0, "skipped": 0}

    stats_root = os.path.join(STEAM_PATH, "appcache", "stats")
    for file in walk_limited(stats_root, max_depth=10, max_files=3000) or []:
        if should_copy_stats(file, appid):
            add_candidate(candidates, seen, file, stats_root, "stats", "appcache-stats", limits)

    userdata_root = os.path.join(STEAM_PATH, "userdata")
    try:
        for steam_user in os.listdir(userdata_root):
            user_root = os.path.join(userdata_root, steam_user)
            if not os.path.isdir(user_root):
                continue
            app_root = os.path.join(user_root, str(appid))
            for file in walk_limited(app_root, max_depth=8, max_files=1200) or []:
                if ext_ok(file):
                    add_candidate(candidates, seen, file, userdata_root, classify_userdata_bucket(file), "userdata", limits)
            user_760 = os.path.join(user_root, "760")
            for file in walk_limited(user_760, max_depth=10, max_files=1200) or []:
                if str(appid) in file and ext_ok(file):
                    add_candidate(candidates, seen, file, userdata_root, classify_userdata_bucket(file), "userdata-760", limits)
            account_config = os.path.join(user_root, "config")
            for file in walk_limited(account_config, max_depth=3, max_files=300) or []:
                if userdata_config_mentions_appid(file, appid):
                    add_candidate(candidates, seen, file, userdata_root, "userdata", "userdata-app-config", limits)
    except:
        pass
    for file in walk_limited(userdata_root, max_depth=14, max_files=2500) or []:
        if should_copy_userdata(file, appid):
            add_candidate(candidates, seen, file, userdata_root, classify_userdata_bucket(file), "userdata", limits)

    for save_root in find_save_roots(app):
        for file in walk_limited(save_root, max_depth=8, max_files=700) or []:
            if ext_ok(file):
                add_candidate(candidates, seen, file, STEAM_PATH, "saves", "game-save", limits, require_recent=True)

    if save_location_api_enabled():
        try:
            add_ludusavi_candidates(candidates, seen, app, limits)
        except Exception as e:
            log_event("WARN", f"Ludusavi manifest scan failed for {app.get('name')} ({appid}): {e}")

    if broad_external_scan_enabled():
        for save_root in find_external_save_roots(app):
            for file in walk_limited(save_root, max_depth=10, max_files=1200) or []:
                if external_file_ok(file):
                    add_candidate(candidates, seen, file, save_root, "external-saves", "external-save", limits, app=app)

    lua_roots = [
        os.path.join(STEAM_PATH, "config", "stplug-in"),
        os.path.join(STEAM_PATH, "config", "lua-tools"),
        os.path.join(STEAM_PATH, "config", "luatools"),
        os.path.join(STEAM_PATH, "plugins", "LuaTools"),
        os.path.join(PLUGIN_ROOT, "..", "LuaTools"),
    ]
    for root in lua_roots:
        for file in walk_limited(root, max_depth=8, max_files=600) or []:
            if should_copy_luatools(file, appid):
                add_candidate(candidates, seen, file, root, "lua-tools", "lua-tools", limits)

    if limits["skipped"]:
        log_event("WARN", f"Snapshot cap reached for AppID {appid}; skipped about {limits['skipped']} bytes")
    return app, candidates


def collect_external_candidates_for_app(app, seen, limits):
    before = limits["bytes"]
    candidates = []
    for save_root in find_save_roots(app):
        for file in walk_limited(save_root, max_depth=8, max_files=900) or []:
            if ext_ok(file):
                add_candidate(candidates, seen, file, save_root, "external-saves", "game-folder-save", limits, app=app)

    if save_location_api_enabled():
        try:
            add_ludusavi_candidates(candidates, seen, app, limits)
        except Exception as e:
            log_event("WARN", f"Full backup API save scan failed for {app.get('name')} ({app.get('appid')}): {e}")

    if broad_external_scan_enabled():
        for save_root in find_external_save_roots(app):
            for file in walk_limited(save_root, max_depth=10, max_files=1200) or []:
                if external_file_ok(file):
                    add_candidate(candidates, seen, file, save_root, "external-saves", "external-save", limits, app=app)

    return candidates, limits["bytes"] - before


def copy_external_candidate_for_full_backup(dest_folder, item):
    game_label = sanitize(f"{item.get('gameName') or 'Unknown Game'} ({item.get('appid') or '0'})")
    origin_label = external_source_label(item["sourceRoot"])
    dest_rel = os.path.join("external-saves", game_label, origin_label, item["relative"])
    dest = os.path.join(dest_folder, dest_rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(item["source"], dest)
    copied = {
        "source": item["source"],
        "sourceRoot": item["sourceRoot"],
        "backupRelative": dest_rel.replace("\\", "/"),
        "targetRelative": item["relative"].replace("\\", "/"),
        "bucket": "external-saves",
        "category": item.get("category") or "external-save",
        "size": item.get("size") or 0,
        "appid": str(item.get("appid") or ""),
        "gameName": item.get("gameName") or "",
        "sourceLabel": origin_label,
    }
    return copied


def backup_external_saves_for_all_games(dest_folder):
    if not backup_all_external_saves_enabled():
        return {"enabled": False, "files": [], "count": 0, "skippedBytes": 0}

    copied = []
    seen = set()
    limits = {"bytes": 0, "skipped": 0, "max_bytes": MAX_FULL_EXTERNAL_BACKUP_BYTES}
    apps = installed_apps()
    log_event("BACKUP", f"Full backup external save scan started: installed_apps={len(apps)}")

    for app in apps:
        appid = str(app.get("appid") or "")
        if not appid or is_ignored_appid(appid):
            continue
        try:
            candidates, added_bytes = collect_external_candidates_for_app(app, seen, limits)
            if not candidates:
                continue
            for item in candidates:
                try:
                    copied.append(copy_external_candidate_for_full_backup(dest_folder, item))
                except Exception as copy_error:
                    log_event("WARN", f"Full backup external save copy failed for {app.get('name')} ({appid}): {copy_error}")
            log_event("BACKUP", f"External saves copied for {app.get('name')} ({appid}): files={len(candidates)} bytes={added_bytes}")
        except Exception as e:
            log_event("WARN", f"Full backup external save scan failed for {app.get('name')} ({appid}): {e}")

    return {
        "enabled": True,
        "files": copied,
        "count": len(copied),
        "bytes": sum(int(item.get("size") or 0) for item in copied),
        "skippedBytes": limits.get("skipped", 0),
    }


def copy_candidate(snapshot_dir, item):
    bucket = item["bucket"]
    if bucket == "external-saves":
        game_label = sanitize(f"{item.get('gameName') or 'Unknown Game'} ({item.get('appid') or '0'})")
        origin_label = external_source_label(item["sourceRoot"])
        dest_rel = os.path.join(bucket, game_label, origin_label, item["relative"])
    else:
        dest_rel = os.path.join(bucket, item["relative"])
    dest = os.path.join(snapshot_dir, dest_rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(item["source"], dest)
    copied = {
        "source": item["source"],
        "sourceRoot": item["sourceRoot"],
        "backupRelative": dest_rel.replace("\\", "/"),
        "targetRelative": item["relative"].replace("\\", "/"),
        "bucket": bucket,
        "category": item["category"],
        "size": item["size"],
    }
    if item.get("appid"):
        copied["appid"] = str(item.get("appid"))
    if item.get("gameName"):
        copied["gameName"] = item.get("gameName")
    if bucket == "external-saves":
        copied["sourceLabel"] = external_source_label(item["sourceRoot"])
    return copied


def dir_size(path):
    total = 0
    for current, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(current, name))
            except:
                pass
    return total


def accounts_from_copied_files(copied):
    accounts = []
    for item in copied:
        rel = str(item.get("targetRelative") or item.get("backupRelative") or "").replace("\\", "/")
        parts = [p for p in rel.split("/") if p]
        if not parts:
            continue
        if parts[0].isdigit():
            accounts.append(parts[0])
        elif len(parts) >= 2 and parts[1].isdigit():
            accounts.append(parts[1])
    return sorted(dict.fromkeys(accounts))


def create_achievement_snapshot(appid, game_name=None, reason="auto-close"):
    if not appid or int(appid) <= 0:
        return {"ok": False, "message": "No AppID available"}
    app, candidates = collect_files(appid, game_name)
    guarantee_mode = broad_external_scan_enabled()
    snap_dir = unique_snapshot_dir(app["name"])
    os.makedirs(snap_dir, exist_ok=True)

    copied = []
    for item in candidates:
        try:
            copied.append(copy_candidate(snap_dir, item))
        except Exception as e:
            log_event("WARN", f"Copy failed for {item.get('source')}: {e}")

    manifest = {
        "type": "unified-game-snapshot",
        "appid": str(appid),
        "gameName": app["name"],
        "timestamp": os.path.basename(snap_dir),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "reason": reason,
        "createdAfterGameClose": reason in ("auto-close", "semi-close"),
        "saveMode": "guarantee" if guarantee_mode else "safe",
        "saveModeLabel": "Garantia" if guarantee_mode else "Seguro",
        "broadExternalScan": guarantee_mode,
        "size": dir_size(snap_dir),
        "fileCount": len(copied),
        "accounts": accounts_from_copied_files(copied),
        "files": copied,
    }
    with open(os.path.join(snap_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log_event("BACKUP", f"Snapshot created successfully: {app['name']} ({appid}) files={len(copied)} path={snap_dir}")
    return {"ok": True, "id": f"{sanitize(app['name'])}/{os.path.basename(snap_dir)}", "snapshot": manifest}


def list_achievement_snapshots():
    result = []
    root = achievements_root()
    if not os.path.exists(root):
        return result
    for game in os.listdir(root):
        game_dir = os.path.join(root, game)
        if not os.path.isdir(game_dir) or game.startswith("AchievementBackup-") or game.startswith("_"):
            continue
        for snap in os.listdir(game_dir):
            snap_dir = os.path.join(game_dir, snap)
            manifest_path = os.path.join(snap_dir, "manifest.json")
            if not os.path.isdir(snap_dir) or not os.path.exists(manifest_path):
                continue
            try:
                data = json.load(open(manifest_path, "r", encoding="utf-8"))
                if data.get("type") not in ("achievement-stats", "unified-game-snapshot"):
                    continue
                if not data.get("accounts"):
                    data["accounts"] = accounts_from_copied_files(data.get("files", []))
                data["id"] = f"{game}/{snap}"
                data["path"] = snap_dir
                data["size"] = data.get("size") or dir_size(snap_dir)
                result.append(data)
            except Exception as e:
                log_event("WARN", f"Failed reading snapshot {manifest_path}: {e}")
    result.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return result


def achievement_stats():
    snapshots = list_achievement_snapshots()
    safety_root = os.path.join(BACKUP_ROOT, "restore-safety")
    last_safety = None
    try:
        if os.path.isdir(safety_root):
            candidates = [
                os.path.join(safety_root, name)
                for name in os.listdir(safety_root)
                if os.path.isdir(os.path.join(safety_root, name))
            ]
            if candidates:
                candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
                last_safety = {
                    "path": candidates[0],
                    "name": os.path.basename(candidates[0]),
                    "createdAt": datetime.fromtimestamp(os.path.getmtime(candidates[0])).strftime("%Y/%m/%d %H:%M"),
                    "size": dir_size(candidates[0]),
                }
    except:
        last_safety = None
    return {
        "ok": True,
        "backupRoot": achievements_root(),
        "count": len(snapshots),
        "totalSize": sum(int(s.get("size") or 0) for s in snapshots),
        "currentAppID": get_running_appid(),
        "lastSafetyBackup": last_safety,
    }


def list_safety_backups():
    root = os.path.join(BACKUP_ROOT, "restore-safety")
    result = []
    if not os.path.isdir(root):
        return result
    for name in os.listdir(root):
        path = os.path.join(root, name)
        manifest_path = os.path.join(path, "manifest.json")
        if not os.path.isdir(path) or not os.path.exists(manifest_path):
            continue
        try:
            manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
            actual_files = []
            for item in manifest.get("files") or []:
                safety_rel = item.get("safetyRelative")
                marker_rel = item.get("deleteMarkerRelative")
                if not safety_rel and not marker_rel:
                    continue
                safety_file = os.path.normpath(os.path.join(path, safety_rel)) if safety_rel else ""
                marker_file = os.path.normpath(os.path.join(path, marker_rel)) if marker_rel else ""
                has_safety_file = safety_file and os.path.exists(safety_file) and is_under(path, safety_file)
                has_marker_file = marker_file and os.path.exists(marker_file) and is_under(path, marker_file)
                if has_safety_file or has_marker_file:
                    actual_files.append(item)
            if not actual_files:
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except:
                    pass
                continue
            result.append({
                "path": path,
                "name": name,
                "gameName": manifest.get("gameName") or "Jogo",
                "appid": manifest.get("appid"),
                "createdAt": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y/%m/%d %H:%M"),
                "size": dir_size(path),
                "fileCount": len(actual_files),
            })
        except Exception as e:
            log_event("WARN", f"Failed reading safety backup {manifest_path}: {e}")
    result.sort(key=lambda item: item.get("createdAt") or "", reverse=True)
    return result


def find_snapshot(snapshot_id):
    parts = str(snapshot_id or "").replace("\\", "/").split("/")
    if len(parts) < 2:
        return None
    game = sanitize(parts[0])
    snap = sanitize(parts[1])
    snap_dir = os.path.join(achievements_root(), game, snap)
    manifest = os.path.join(snap_dir, "manifest.json")
    if not is_under(achievements_root(), snap_dir) or not os.path.exists(manifest):
        return None
    data = json.load(open(manifest, "r", encoding="utf-8"))
    return snap_dir, data


def close_game(appid):
    app = get_installed_app(appid)
    common = app.get("common")
    if not common or not os.path.isdir(common):
        return True
    ps = (
        "$pattern = '" + common.replace("'", "''") + "\\*'; "
        "$targets = Get-Process | Where-Object {$_.Path -and $_.Path -like $pattern}; "
        "foreach ($p in $targets) { try { if ($p.MainWindowHandle -ne 0) { $null = $p.CloseMainWindow() } } catch {} }; "
        "Start-Sleep -Seconds 4; "
        "$targets = Get-Process | Where-Object {$_.Path -and $_.Path -like $pattern}; "
        "foreach ($p in $targets) { try { Stop-Process -Id $p.Id -Force } catch {} }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=12, creationflags=0x08000000)
    except Exception as e:
        log_event("WARN", f"close_game failed for {appid}: {e}")
    return True


def set_restore_flag(active):
    try:
        os.makedirs(os.path.dirname(RESTORE_FLAG_FILE), exist_ok=True)
        if active:
            with open(RESTORE_FLAG_FILE, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        elif os.path.exists(RESTORE_FLAG_FILE):
            os.remove(RESTORE_FLAG_FILE)
    except:
        pass


def close_steam():
    ps = (
        "$names = @('steam','steamwebhelper','steamerrorreporter'); "
        "foreach ($name in $names) { "
        "  Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object { "
        "    try { if ($_.MainWindowHandle -ne 0) { $null = $_.CloseMainWindow() } } catch {} "
        "  } "
        "} "
        "Start-Sleep -Seconds 5; "
        "foreach ($name in $names) { "
        "  Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object { "
        "    try { Stop-Process -Id $_.Id -Force } catch {} "
        "  } "
        "}"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=18, creationflags=0x08000000)
        return True
    except Exception as e:
        log_event("WARN", f"close_steam failed: {e}")
        return False


def start_steam():
    steam_exe = os.path.join(STEAM_PATH, "steam.exe")
    if not os.path.exists(steam_exe):
        log_event("WARN", f"Steam executable not found: {steam_exe}")
        return False
    try:
        subprocess.Popen([steam_exe], cwd=STEAM_PATH, creationflags=0x08000000)
        return True
    except Exception as e:
        log_event("WARN", f"start_steam failed: {e}")
        return False


def bat_value(value):
    return str(value).replace("%", "%%")


def restore_bucket_label(item):
    bucket = item.get("bucket") or ""
    category = item.get("category") or ""
    if bucket == "stats":
        return "stats/horas do jogo"
    if bucket == "achievements":
        return "conquistas/cache"
    if bucket == "userdata" and category == "userdata-app-config":
        return "configuracoes userdata do jogo"
    if bucket == "userdata":
        return "userdata do jogo"
    if bucket == "saves":
        return "saves Steam"
    if bucket == "external-saves":
        return "saves externos"
    if bucket == "lua-tools":
        return "Lua Tools"
    return bucket or "arquivos capturados"


def restore_summary_text(labels):
    return ", ".join(label.replace("|", "/") for label in labels if label)


def safety_bucket_name(item):
    bucket = item.get("bucket") or "arquivos"
    category = item.get("category") or ""
    if bucket == "stats":
        return "stats-horas-e-conquistas"
    if bucket == "achievements":
        return "conquistas-cache"
    if bucket == "userdata" and category == "userdata-app-config":
        return "userdata-config"
    if bucket == "userdata":
        return "userdata-saves-steam"
    if bucket == "saves":
        return "saves-steam"
    if bucket == "external-saves":
        return "saves-externos"
    if bucket == "lua-tools":
        return "lua-tools"
    return sanitize(bucket)


def safety_relative_path(item, index):
    rel = str(item.get("targetRelative") or "").replace("\\", "/").strip("/")
    if not rel:
        rel = os.path.basename(str(item.get("target") or f"arquivo_{index:04d}"))
    rel_parts = [sanitize(part) for part in rel.split("/") if part]
    if not rel_parts:
        rel_parts = [f"arquivo_{index:04d}"]
    return os.path.join(safety_bucket_name(item), *rel_parts)


def safety_marker_relative_path(safety_rel):
    rel = str(safety_rel or "").replace("\\", "/").strip("/")
    if not rel:
        rel = "arquivo-criado"
    return os.path.join("created-by-capture", rel + ".delete-marker.txt")


def neutralize_achievement_entry(entry):
    if not isinstance(entry, dict):
        return entry
    data = entry.get("data")
    if not isinstance(data, dict):
        return entry
    for key in ("vecHighlight", "vecUnachieved", "vecAchievedHidden"):
        value = data.get(key)
        if not isinstance(value, list):
            continue
        for idx, ach in enumerate(value):
            if not isinstance(ach, dict):
                continue
            clean = dict(ach)
            clean["bAchieved"] = False
            clean["rtUnlocked"] = 0
            if "flCurrentProgress" in clean:
                clean["flCurrentProgress"] = 0
            if "flAchieved" in clean:
                clean["flAchieved"] = 0
            value[idx] = clean
    total = data.get("nTotal")
    if not isinstance(total, int) or total <= 0:
        seen = set()
        for key in ("vecHighlight", "vecUnachieved", "vecAchievedHidden"):
            value = data.get(key)
            if isinstance(value, list):
                for ach in value:
                    if isinstance(ach, dict):
                        seen.add(str(ach.get("strID") or ach.get("strName") or json.dumps(ach, sort_keys=True)))
        data["nTotal"] = len(seen)
    data["nAchieved"] = 0
    return entry


def write_neutral_librarycache(source, dest):
    try:
        with open(source, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return False
        changed = False
        for row in data:
            if isinstance(row, list) and row and row[0] == "achievements" and len(row) > 1:
                row[1] = neutralize_achievement_entry(row[1])
                changed = True
        if not changed:
            return False
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        return True
    except Exception as e:
        log_event("WARN", f"Failed creating neutral achievement cache: {e}")
        return False


def prepare_safety_fallback(item, safety_root):
    try:
        target = os.path.normpath(str(item.get("target") or ""))
        source = os.path.normpath(str(item.get("source") or ""))
        safety_rel = item.get("safetyRelative")
        if not target or not source or not safety_rel:
            return False
        if os.path.exists(target) or not os.path.exists(source):
            return False
        lower_target = target.replace("\\", "/").lower()
        if item.get("category") == "userdata-app-config" and lower_target.endswith(f"/librarycache/{item.get('appid') or ''}.json"):
            fallback = os.path.normpath(os.path.join(safety_root, safety_rel))
            if write_neutral_librarycache(source, fallback):
                item["safetyFallback"] = "neutral-achievement-cache"
                return True
    except Exception as e:
        log_event("WARN", f"Failed preparing safety fallback: {e}")
    return False


def external_prune_stop(path, game_name):
    try:
        parts = os.path.normpath(str(path or "")).split(os.sep)
        wanted = sanitize(game_name or "").lower()
        if not wanted:
            return None
        for idx, part in enumerate(parts):
            if sanitize(part).lower() == wanted and idx > 0:
                return os.sep.join(parts[:idx])
    except:
        pass
    return None


def created_directory_info(target_dir, stop_dir):
    try:
        target_dir = os.path.normpath(str(target_dir or ""))
        stop_dir = os.path.normpath(str(stop_dir or ""))
        if not target_dir or not stop_dir or not is_under(stop_dir, target_dir):
            return None, None
        current = target_dir
        first_missing = None
        while current and is_under(stop_dir, current) and os.path.normcase(current) != os.path.normcase(stop_dir):
            if not os.path.exists(current):
                first_missing = current
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        if first_missing:
            return first_missing, stop_dir
    except:
        pass
    return None, None


def cleanup_stop_for_item(item, game_name):
    try:
        target = os.path.normpath(str(item.get("target") or ""))
        target_dir = os.path.dirname(target)
        bucket = item.get("bucket")
        category = item.get("category")
        root = os.path.normpath(str(item.get("targetRoot") or os.path.dirname(target)))
        if bucket == "external-saves":
            return external_prune_stop(target_dir, game_name) or os.path.dirname(root)
        if bucket in ("userdata", "achievements", "saves") or category == "userdata-app-config":
            parts = target.replace("\\", "/").split("/")
            if "userdata" in [p.lower() for p in parts]:
                idx = [p.lower() for p in parts].index("userdata")
                if len(parts) > idx + 1:
                    return os.path.normpath("/".join(parts[:idx + 2]))
        return root
    except:
        return os.path.normpath(str(item.get("targetRoot") or ""))


def find_latest_snapshot_file(appid, target_suffix):
    try:
        matches = []
        root = achievements_root()
        suffix = str(target_suffix or "").replace("\\", "/").lower().strip("/")
        for game in os.listdir(root):
            game_dir = os.path.join(root, game)
            if not os.path.isdir(game_dir):
                continue
            for snap in os.listdir(game_dir):
                snap_dir = os.path.join(game_dir, snap)
                manifest_path = os.path.join(snap_dir, "manifest.json")
                if not os.path.exists(manifest_path):
                    continue
                try:
                    manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
                except:
                    continue
                if str(manifest.get("appid") or "") != str(appid):
                    continue
                for item in manifest.get("files") or []:
                    rel = str(item.get("targetRelative") or "").replace("\\", "/").lower().strip("/")
                    if rel.endswith(suffix):
                        source = os.path.normpath(os.path.join(snap_dir, item.get("backupRelative", "")))
                        if os.path.exists(source) and is_under(snap_dir, source):
                            matches.append((os.path.getmtime(snap_dir), source))
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]
    except Exception as e:
        log_event("WARN", f"Failed finding latest snapshot file: {e}")
        return None


def ensure_neutral_librarycache_for_safety(safety_dir, manifest_item, appid):
    try:
        original = str(manifest_item.get("originalTarget") or "").replace("\\", "/").lower()
        if not original.endswith(f"/librarycache/{appid}.json"):
            return None
        safety_rel = manifest_item.get("safetyRelative")
        if not safety_rel:
            return None
        dest = os.path.normpath(os.path.join(safety_dir, safety_rel))
        if os.path.exists(dest):
            return dest
        source = find_latest_snapshot_file(appid, f"config/librarycache/{appid}.json")
        if source and write_neutral_librarycache(source, dest):
            return dest
    except Exception as e:
        log_event("WARN", f"Failed ensuring neutral librarycache for safety restore: {e}")
    return None


def launch_external_snapshot_restore(appid, game_name, files, create_safety_backup=True, restore_kind="snapshot"):
    steam_exe = os.path.join(STEAM_PATH, "steam.exe")
    if not os.path.exists(steam_exe):
        return {"ok": False, "message": "Steam executable not found"}

    temp_dir = tempfile.gettempdir()
    token = f"achievementbackup_snapshot_restore_{int(time.time())}"
    bat_path = os.path.join(temp_dir, token + ".bat")
    terminal_color = restore_terminal_color()
    safe_game = re.sub(r"[^A-Za-z0-9._-]+", "_", str(game_name or appid)).strip("_") or str(appid)
    safety_root = os.path.join(
        BACKUP_ROOT,
        "restore-safety",
        f"{safe_game}_{appid}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}",
    )
    safety_manifest = {
        "type": "restore-safety",
        "gameName": game_name,
        "appid": str(appid),
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "description": "Arquivos atuais do jogo copiados antes da captura sobrescrever qualquer coisa.",
        "files": [],
    }
    restored_labels = []
    for item in files:
        label = restore_bucket_label(item)
        if label not in restored_labels:
            restored_labels.append(label)
    if create_safety_backup:
        for idx, item in enumerate(files, start=1):
            safety_rel = safety_relative_path(item, idx)
            marker_rel = safety_marker_relative_path(safety_rel)
            item["safetyRelative"] = safety_rel
            item["deleteMarkerRelative"] = marker_rel
            target_root = os.path.normpath(str(item.get("targetRoot") or os.path.dirname(str(item.get("target") or ""))))
            item["rootExistedBefore"] = os.path.exists(target_root)
            prune_stop = cleanup_stop_for_item(item, game_name)
            target_dir = os.path.dirname(os.path.normpath(str(item.get("target") or "")))
            created_dir, created_stop = created_directory_info(target_dir, prune_stop)
            if created_dir:
                item["createdDirectory"] = created_dir
                item["createdDirectoryStop"] = created_stop
            if not item["rootExistedBefore"] or created_dir:
                item["pruneStop"] = prune_stop
            prepare_safety_fallback(item, safety_root)
            safety_manifest["files"].append({
                "bucket": item.get("bucket"),
                "category": item.get("category"),
                "originalTarget": item.get("target"),
                "originalRoot": item.get("targetRoot"),
                "rootExistedBefore": item.get("rootExistedBefore"),
                "pruneStop": item.get("pruneStop"),
                "createdDirectory": item.get("createdDirectory"),
                "createdDirectoryStop": item.get("createdDirectoryStop"),
                "safetyRelative": safety_rel,
                "deleteMarkerRelative": marker_rel,
                "safetyFallback": item.get("safetyFallback"),
                "label": restore_bucket_label(item),
            })
        try:
            os.makedirs(safety_root, exist_ok=True)
            with open(os.path.join(safety_root, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(safety_manifest, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_event("WARN", f"Failed writing restore safety manifest: {e}")
    summary = restore_summary_text(restored_labels or ["arquivos capturados"])
    is_safety_restore = str(restore_kind) == "safety"
    title_main = "AchievementBackup :: RESTORE DE SEGURANCA" if is_safety_restore else "AchievementBackup :: GAME CAPTURE RESTORE"
    window_title = "AchievementBackup - Restauracao de Seguranca" if is_safety_restore else "AchievementBackup - Restauracao de Captura"
    preparing_text = "Preparando copia de seguranca" if is_safety_restore else "Preparando restore da captura"
    restoring_text = "Aplicando copia de seguranca" if is_safety_restore else "Restaurando arquivos do jogo"
    items_title = "Itens tratados nesta copia de seguranca:" if is_safety_restore else "Itens restaurados nesta Captura:"
    done_title = "Copia de seguranca aplicada." if is_safety_restore else "Captura restaurada."
    lines = [
        "@echo off",
        "setlocal EnableExtensions EnableDelayedExpansion",
        f"title {window_title}",
        f"color {terminal_color}",
        "cls",
        f"set \"TITLE_MAIN={title_main}\"",
        f"set \"SUBTITLE={bat_value(game_name)}  AppID: {bat_value(appid)}\"",
        "set /a OK=0",
        "set /a COPYOK=0",
        "set /a REMOVED=0",
        "set /a FAIL=0",
        "set /a STEP=0",
        f"set /a STEPS={max(len(files) + 3, 4)}",
        f'set "LOGFILE={bat_value(os.path.join(PLUGIN_ROOT, "log.txt"))}"',
        'echo [%DATE% %TIME%] Restore de captura iniciado: ' + bat_value(game_name) + f' AppID {bat_value(appid)} >> "%LOGFILE%"',
    ]
    if create_safety_backup:
        lines.extend([
            f'set "SAFETY={bat_value(safety_root)}"',
            "set /a SAFETY_COUNT=0",
            'if not exist "%SAFETY%" mkdir "%SAFETY%" >nul 2>&1',
            'echo AchievementBackup restore safety > "%SAFETY%\\README.txt"',
            'echo Esta pasta guarda os arquivos antigos antes da Captura sobrescrever qualquer coisa. >> "%SAFETY%\\README.txt"',
            'echo Se um arquivo nao existia antes, ha um marcador para remove-lo ao desfazer o restore. >> "%SAFETY%\\README.txt"',
            'echo Use o manifest.json para ver o destino original de cada arquivo. >> "%SAFETY%\\README.txt"',
            'echo. >> "%SAFETY%\\README.txt"',
            'echo AchievementBackup restore safety mapping > "%SAFETY%\\mapping.txt"',
            f'echo Game: {bat_value(game_name)}  AppID: {bat_value(appid)} >> "%SAFETY%\\mapping.txt"',
            'echo. >> "%SAFETY%\\mapping.txt"',
        ])
    lines.extend([
        f"call :progress {preparing_text}",
        "call :progress Fechando processos da Steam",
        "taskkill /F /IM steam.exe >nul 2>&1",
        "taskkill /F /IM steamwebhelper.exe >nul 2>&1",
        "taskkill /F /IM steamerrorreporter.exe >nul 2>&1",
        "timeout /t 3 /nobreak >nul",
        f"call :progress {restoring_text}",
    ])

    for idx, item in enumerate(files, start=1):
        action = str(item.get("action") or "copy").lower()
        source = bat_value(os.path.normpath(item.get("source") or ""))
        target = bat_value(os.path.normpath(item["target"]))
        target_dir = bat_value(os.path.dirname(os.path.normpath(item["target"])))
        target_root = bat_value(os.path.normpath(item.get("targetRoot") or os.path.dirname(os.path.normpath(item["target"]))))
        prune_stop = bat_value(os.path.normpath(item.get("pruneStop") or item.get("targetRoot") or os.path.dirname(os.path.normpath(item["target"]))))
        created_dir = bat_value(os.path.normpath(item.get("createdDirectory") or ""))
        created_stop = bat_value(os.path.normpath(item.get("createdDirectoryStop") or item.get("pruneStop") or ""))
        cleanup_cloud = "1" if item.get("cleanupSteamAutoCloud") else "0"
        safe_file = bat_value(os.path.join(safety_root, item.get("safetyRelative") or f"arquivo_{idx:04d}"))
        safe_dir = bat_value(os.path.dirname(os.path.join(safety_root, item.get("safetyRelative") or f"arquivo_{idx:04d}")))
        marker_file = bat_value(os.path.join(safety_root, item.get("deleteMarkerRelative") or safety_marker_relative_path(item.get("safetyRelative") or f"arquivo_{idx:04d}")))
        marker_dir = bat_value(os.path.dirname(os.path.join(safety_root, item.get("deleteMarkerRelative") or safety_marker_relative_path(item.get("safetyRelative") or f"arquivo_{idx:04d}"))))
        lines.extend([
            "set /a STEP+=1",
            f"call :progress Arquivo {idx}/{len(files)} - {bat_value(os.path.basename(item['target']))}",
            f'set "DST={target}"',
            f'set "DSTDIR={target_dir}"',
            f'set "ROOTLIMIT={target_root}"',
            f'set "PRUNESTOP={prune_stop}"',
            f'set "CREATEDDIR={created_dir}"',
            f'set "CREATEDSTOP={created_stop}"',
            f'set "CLEANUPCLOUD={cleanup_cloud}"',
        ])
        if action == "delete":
            lines.extend([
                'if exist "%DST%" (',
                '  attrib -R "%DST%" >nul 2>&1',
                '  del /F /Q "%DST%" >nul 2>&1',
                '  if errorlevel 1 (set /a FAIL+=1 & echo FALHOU AO REMOVER: "%DST%" & echo [%DATE% %TIME%] FALHA captura remover ^| destino="%DST%" >> "%LOGFILE%") else (set /a OK+=1 & set /a REMOVED+=1 & echo REMOVIDO: "%DST%" & if "%CLEANUPCLOUD%"=="1" call :remove_external_cloud "%DSTDIR%" "%PRUNESTOP%" & call :remove_created_dir "%CREATEDDIR%" "%CREATEDSTOP%" & call :prune_empty_dirs "%DSTDIR%" "%PRUNESTOP%")',
                ') else (',
                '  set /a OK+=1',
                '  echo JA NAO EXISTIA: "%DST%"',
                '  if "%CLEANUPCLOUD%"=="1" call :remove_external_cloud "%DSTDIR%" "%PRUNESTOP%"',
                '  call :remove_created_dir "%CREATEDDIR%" "%CREATEDSTOP%"',
                '  call :prune_empty_dirs "%DSTDIR%" "%PRUNESTOP%"',
                ')',
            ])
            continue
        lines.extend([
            f'set "SRC={source}"',
            'if not exist "%DSTDIR%" mkdir "%DSTDIR%" >nul 2>&1',
            'if exist "%SRC%" (',
            '  if exist "%DST%" attrib -R "%DST%" >nul 2>&1',
        ])
        if create_safety_backup:
            lines.extend([
            f'set "SAFEFILE={safe_file}"',
            f'set "SAFEDIR={safe_dir}"',
            f'set "MARKERFILE={marker_file}"',
            f'set "MARKERDIR={marker_dir}"',
            '  if exist "%DST%" (',
            '    if not exist "%SAFEDIR%" mkdir "%SAFEDIR%" >nul 2>&1',
            '    copy /Y "%DST%" "%SAFEFILE%" >nul',
            '    echo "%DST%" --^> "%SAFEFILE%" >> "%SAFETY%\\mapping.txt"',
            '    set /a SAFETY_COUNT+=1',
            '  ) else (',
            '    if not exist "%MARKERDIR%" mkdir "%MARKERDIR%" >nul 2>&1',
            '    echo "%DST%" > "%MARKERFILE%"',
            '    echo "%DST%" --^> arquivo criado pela Captura, remover ao desfazer restore >> "%SAFETY%\\mapping.txt"',
            '    set /a SAFETY_COUNT+=1',
            '  )',
            ])
        lines.extend([
            '  copy /Y "%SRC%" "%DST%" >nul',
            '  if errorlevel 1 (set /a FAIL+=1 & echo FALHOU: "%DST%" & echo [%DATE% %TIME%] FALHA captura copiar ^| origem="%SRC%" ^| destino="%DST%" >> "%LOGFILE%") else (set /a OK+=1 & set /a COPYOK+=1 & echo OK: "%DST%")',
            ') else (',
            '  set /a FAIL+=1',
            '  echo FALTOU ORIGEM: "%SRC%"',
            '  echo [%DATE% %TIME%] FALHA captura origem ausente ^| origem="%SRC%" ^| destino="%DST%" >> "%LOGFILE%"',
            ')',
        ])

    lines.extend([
        f'del /F /Q "{bat_value(RESTORE_FLAG_FILE)}" >nul 2>&1',
        "set /a STEP=STEPS-1",
        "call :progress Finalizando restore",
        f'start "" "{bat_value(steam_exe)}"',
        f'set "RESTORE_FLAG={bat_value(str(restore_kind).replace("|", "/"))}|{bat_value(str(game_name).replace("|", "/"))}|{bat_value(str(appid).replace("|", "/"))}|{bat_value(summary)}|%OK%|{len(files)}|%FAIL%|{bat_value(str(safety_root).replace("|", "/")) if create_safety_backup else ""}|%REMOVED%|%COPYOK%"',
        f'echo(!RESTORE_FLAG! > "{bat_value(os.path.join(BACKUP_ROOT, "restore_success.flag"))}"',
        'echo [%DATE% %TIME%] Restore de captura finalizado ^| OK=%OK% ^| removidos=%REMOVED% ^| falhas=%FAIL% >> "%LOGFILE%"',
        "set /a STEP=STEPS",
        "call :progress Abrindo Steam novamente",
        "echo.",
        f"echo {items_title}",
    ])
    for label in restored_labels or ["arquivos capturados"]:
        lines.append(f"echo - {bat_value(label)}")
    lines.extend([
        "echo.",
        f"echo {done_title}",
        "echo Arquivos restaurados: %COPYOK%",
        "echo Arquivos removidos: %REMOVED%",
        "echo Falhas: %FAIL%",
        "echo.",
        "timeout /t 8 /nobreak >nul",
        '(goto) 2>nul & del "%~f0"',
        "",
        ":prune_empty_dirs",
        "set \"PRUNE_DIR=%~1\"",
        "set \"PRUNE_LIMIT=%~2\"",
        ":prune_loop",
        "if not defined PRUNE_DIR goto :eof",
        "if not defined PRUNE_LIMIT goto :eof",
        "if /I \"!PRUNE_DIR!\"==\"!PRUNE_LIMIT!\" goto :eof",
        "if not exist \"!PRUNE_DIR!\" (",
        "  for %%P in (\"!PRUNE_DIR!\\..\") do set \"PRUNE_DIR=%%~fP\"",
        "  goto prune_loop",
        ")",
        "rd \"!PRUNE_DIR!\" >nul 2>&1",
        "if exist \"!PRUNE_DIR!\" goto :eof",
        "for %%P in (\"!PRUNE_DIR!\\..\") do set \"PRUNE_DIR=%%~fP\"",
        "goto prune_loop",
        "",
        ":remove_created_dir",
        "set \"MADE_DIR=%~1\"",
        "set \"MADE_STOP=%~2\"",
        "if not defined MADE_DIR goto :eof",
        "if not defined MADE_STOP goto :eof",
        "if /I \"!MADE_DIR!\"==\"!MADE_STOP!\" goto :eof",
        "if exist \"!MADE_DIR!\" (",
        "  rd /S /Q \"!MADE_DIR!\" >nul 2>&1",
        "  if not exist \"!MADE_DIR!\" (set /a REMOVED+=1 & echo PASTA REMOVIDA: \"!MADE_DIR!\")",
        ")",
        "for %%P in (\"!MADE_DIR!\\..\") do call :prune_empty_dirs \"%%~fP\" \"!MADE_STOP!\"",
        "goto :eof",
        "",
        ":remove_external_cloud",
        "set \"CLOUD_DIR=%~1\"",
        "set \"CLOUD_LIMIT=%~2\"",
        ":cloud_loop",
        "if not defined CLOUD_DIR goto :eof",
        "if not defined CLOUD_LIMIT goto :eof",
        "if /I \"!CLOUD_DIR!\"==\"!CLOUD_LIMIT!\" goto :eof",
        "if exist \"!CLOUD_DIR!\\steam_autocloud.vdf\" (",
        "  del /F /Q \"!CLOUD_DIR!\\steam_autocloud.vdf\" >nul 2>&1",
        "  if not exist \"!CLOUD_DIR!\\steam_autocloud.vdf\" (set /a REMOVED+=1 & echo REMOVIDO: \"!CLOUD_DIR!\\steam_autocloud.vdf\")",
        ")",
        "for %%P in (\"!CLOUD_DIR!\\..\") do set \"CLOUD_DIR=%%~fP\"",
        "goto cloud_loop",
        "",
        ":progress",
        "set \"MSG=%~1\"",
        "set /a PCT=(STEP*100)/STEPS",
        "set \"BAR=\"",
        "for /L %%B in (1,1,28) do (",
        "  set /a LIM=STEP*28/STEPS",
        "  if %%B LEQ !LIM! (set \"BAR=!BAR!#\") else (set \"BAR=!BAR!-\")",
        ")",
        "cls",
        "echo !TITLE_MAIN!",
        "echo !SUBTITLE!",
        "echo.",
        "echo [!BAR!] !PCT!%%",
        "echo.",
        "echo Agora: !MSG!",
        "echo.",
        "goto :eof",
    ])

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    subprocess.Popen([bat_path], cwd=temp_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
    return {
        "ok": True,
        "restored": len(files),
        "summary": summary,
        "safetyBackup": safety_root if create_safety_backup else None,
        "steamRestarted": True,
        "accepted": True,
    }


def apply_snapshot_restore_direct(appid, game_name, files, create_safety_backup=True, restore_kind="snapshot"):
    steam_exe = os.path.join(STEAM_PATH, "steam.exe")
    safe_game = re.sub(r"[^A-Za-z0-9._-]+", "_", str(game_name or appid)).strip("_") or str(appid)
    safety_root = os.path.join(
        BACKUP_ROOT,
        "restore-safety",
        f"{safe_game}_{appid}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}",
    )
    labels = []
    label_counts = {}
    failures = []
    copied = 0
    removed = 0

    for item in files:
        label = restore_bucket_label(item)
        if label not in labels:
            labels.append(label)

    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Stop-Process -Name steam,steamwebhelper,steamerrorreporter -Force -ErrorAction SilentlyContinue",
            ],
            timeout=15,
            creationflags=0x08000000,
        )
        time.sleep(2)
    except Exception as e:
        log_event("WARN", f"Failed stopping Steam before restore: {e}")

    safety_manifest = {
        "type": "restore-safety",
        "gameName": game_name,
        "appid": str(appid),
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "description": "Arquivos atuais do jogo copiados antes da captura sobrescrever qualquer coisa.",
        "files": [],
    }
    if create_safety_backup:
        os.makedirs(safety_root, exist_ok=True)

    for idx, item in enumerate(files, start=1):
        target = os.path.normpath(str(item.get("target") or ""))
        source = os.path.normpath(str(item.get("source") or ""))
        action = str(item.get("action") or "copy").lower()
        try:
            if action == "delete":
                if os.path.exists(target):
                    os.remove(target)
                    removed += 1
                    label_counts[label] = label_counts.get(label, 0) + 1
                continue

            if not os.path.exists(source):
                raise FileNotFoundError(f"Origem nao encontrada: {source}")

            target_dir = os.path.dirname(target)
            os.makedirs(target_dir, exist_ok=True)

            if create_safety_backup:
                safety_rel = safety_relative_path(item, idx)
                safety_path = os.path.join(safety_root, safety_rel)
                os.makedirs(os.path.dirname(safety_path), exist_ok=True)
                if os.path.exists(target):
                    shutil.copy2(target, safety_path)
                else:
                    marker_rel = safety_marker_relative_path(safety_rel)
                    marker_path = os.path.join(safety_root, marker_rel)
                    os.makedirs(os.path.dirname(marker_path), exist_ok=True)
                    with open(marker_path, "w", encoding="utf-8") as f:
                        f.write(target)
                safety_manifest["files"].append({
                    "bucket": item.get("bucket"),
                    "category": item.get("category"),
                    "originalTarget": target,
                    "originalRoot": item.get("targetRoot"),
                    "safetyRelative": safety_rel,
                    "label": restore_bucket_label(item),
                })

            shutil.copy2(source, target)
            copied += 1
            label_counts[label] = label_counts.get(label, 0) + 1
        except PermissionError as e:
            failures.append(f"Acesso bloqueado: {target}. Permita Python/Steam no Acesso controlado a pastas do Windows ou desative temporariamente para restaurar.")
            log_event("ERROR", f"Restore permission blocked: {target}: {e}")
        except Exception as e:
            failures.append(f"{target}: {e}")
            log_event("ERROR", f"Direct snapshot restore failed for {target}: {e}")

    if create_safety_backup:
        try:
            with open(os.path.join(safety_root, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(safety_manifest, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_event("WARN", f"Failed writing restore safety manifest: {e}")

    steam_started = False
    try:
        if os.path.exists(RESTORE_FLAG_FILE):
            os.remove(RESTORE_FLAG_FILE)
        steam_started = start_steam_client(steam_exe)
    except Exception as e:
        log_event("WARN", f"Failed restarting Steam after restore: {e}")

    summary = restore_summary_text(labels or ["arquivos capturados"])
    try:
        failure_file = os.path.join(BACKUP_ROOT, "restore_failures.log")
        if failures:
            with open(failure_file, "w", encoding="utf-8") as f:
                for item in failures:
                    text = str(item).replace("\n", " ").replace("|", "/")
                    path = text.split(": ", 1)[0]
                    f.write(f"ERRO|captura|{path}|\n")
        elif os.path.exists(os.path.join(BACKUP_ROOT, "restore_failures.log")):
            os.remove(os.path.join(BACKUP_ROOT, "restore_failures.log"))
        flag = "|".join([
            str(restore_kind).replace("|", "/"),
            str(game_name).replace("|", "/"),
            str(appid).replace("|", "/"),
            summary.replace("|", "/"),
            str(copied + removed),
            str(len(files)),
            str(len(failures)),
            str(safety_root if create_safety_backup else "").replace("|", "/"),
            str(removed),
            str(copied),
        ])
        with open(os.path.join(BACKUP_ROOT, "restore_success.flag"), "w", encoding="utf-8") as f:
            f.write(flag)
    except Exception:
        pass

    if failures:
        first = failures[0]
        more = f" Mais {len(failures) - 1} falhas." if len(failures) > 1 else ""
        return {
            "ok": False,
            "message": f"Restore parcial: {copied} copiados, {removed} removidos, {len(failures)} falhas. {first}{more}",
            "restored": copied + removed,
            "failed": len(failures),
            "failures": failures,
            "labels": labels,
            "labelCounts": label_counts,
            "copiedCount": copied,
            "removedCount": removed,
            "totalFiles": len(files),
            "safetyBackup": safety_root if create_safety_backup else None,
            "steamRestarted": steam_started,
        }
    return {
        "ok": True,
        "message": f"Captura restaurada: {copied} arquivos copiados, {removed} removidos. Steam {'aberta novamente' if steam_started else 'nao abriu automaticamente'}.",
        "restored": copied + removed,
        "summary": summary,
        "labels": labels,
        "labelCounts": label_counts,
        "copiedCount": copied,
        "removedCount": removed,
        "failed": 0,
        "failures": [],
        "totalFiles": len(files),
        "safetyBackup": safety_root if create_safety_backup else None,
        "steamRestarted": steam_started,
    }


def launch_worker_snapshot_restore(appid, game_name, files, create_safety_backup=True, restore_kind="snapshot"):
    temp_dir = tempfile.gettempdir()
    token = f"achievementbackup_restore_{int(time.time())}"
    payload_path = os.path.join(temp_dir, token + ".json")
    worker_path = os.path.join(temp_dir, token + ".py")
    bat_path = os.path.join(temp_dir, token + ".bat")
    terminal_color = restore_terminal_color()
    payload = {
        "appid": str(appid),
        "gameName": game_name,
        "files": files,
        "createSafetyBackup": bool(create_safety_backup),
        "restoreKind": restore_kind,
        "moduleDir": os.path.dirname(os.path.abspath(__file__)),
    }
    with open(payload_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    worker_code = r'''
import json
import os
import sys
import traceback

payload_path = sys.argv[1]
with open(payload_path, "r", encoding="utf-8") as f:
    payload = json.load(f)
sys.path.insert(0, payload["moduleDir"])
from achievement_backup import apply_snapshot_restore_direct

print("AchievementBackup :: Restore de Captura")
print(f"{payload.get('gameName') or 'Jogo'}  AppID: {payload.get('appid')}")
print()
print("Este restore fecha a Steam, aplica a captura do jogo e tenta abrir a Steam novamente.")
if payload.get("createSafetyBackup", True):
    print("Uma copia de seguranca automatica sera guardada antes de sobrescrever.")
print()
try:
    print("[1/4] Fechando Steam")
    print("[2/4] Criando copia de seguranca automatica")
    print("[3/4] Aplicando arquivos da captura")
    print("[4/4] Abrindo Steam novamente")
    print()
    result = apply_snapshot_restore_direct(
        payload.get("appid"),
        payload.get("gameName"),
        payload.get("files") or [],
        payload.get("createSafetyBackup", True),
        payload.get("restoreKind") or "snapshot",
    )
    print()
    print(result.get("message") or ("Restore concluido." if result.get("ok") else "Restore finalizado com erro."))
    if result.get("steamRestarted"):
        print("Steam abriu novamente.")
    else:
        print("Nao consegui confirmar a Steam aberta. Abra a Steam manualmente se ela nao aparecer.")
    failures = result.get("failures") or []
    for item in failures[:8]:
        print("-", item)
    sys.exit(0 if result.get("ok") else 2)
except Exception:
    traceback.print_exc()
    sys.exit(1)
'''
    with open(worker_path, "w", encoding="utf-8") as f:
        f.write(worker_code)

    lines = [
        "@echo off",
        "setlocal EnableExtensions EnableDelayedExpansion",
        f"title AchievementBackup - Restore de Captura",
        f"color {terminal_color}",
        "cls",
        "echo ================================================",
        "echo AchievementBackup :: Restore de Captura",
        "echo ================================================",
        f"echo {bat_value(game_name)}  AppID: {bat_value(appid)}",
        "echo.",
        "echo Esta janela mostra o progresso do restore.",
        "echo Nao feche ate aparecer a mensagem final.",
        "echo.",
        f'"{bat_value(sys.executable)}" "{bat_value(worker_path)}" "{bat_value(payload_path)}"',
        "set RESULT=%ERRORLEVEL%",
        "echo.",
        "if \"%RESULT%\"==\"0\" (echo Tudo pronto.) else (echo Restore terminou com avisos ou erro. Codigo: %RESULT%)",
        "echo.",
        "timeout /t 10 /nobreak >nul",
        f'del /F /Q "{bat_value(worker_path)}" >nul 2>&1',
        f'del /F /Q "{bat_value(payload_path)}" >nul 2>&1',
        '(goto) 2>nul & del "%~f0"',
    ]
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    subprocess.Popen([bat_path], cwd=temp_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
    return {
        "ok": True,
        "message": "Restore iniciado em janela externa. A Steam sera aberta novamente no final.",
        "restored": len(files),
        "steamRestarted": True,
        "accepted": True,
    }


def is_cloud_syncing(appid):
    cloud_log = os.path.join(STEAM_PATH, "logs", "cloud_log.txt")
    try:
        raw = open(cloud_log, "r", encoding="utf-8", errors="ignore").read()[-16000:]
    except:
        return False
    last = ""
    for line in raw.splitlines():
        if str(appid) in line:
            last = line.lower()
    if not last:
        return False
    if any(word in last for word in ("finished", "complete", "success", "up to date")):
        return False
    return any(word in last for word in ("sync", "upload", "download", "pending", "queued"))


def wait_for_cloud_sync(appid, max_seconds=20):
    deadline = time.time() + max_seconds
    while is_cloud_syncing(appid) and time.time() < deadline:
        time.sleep(2)
    return not is_cloud_syncing(appid)


def restore_achievement_snapshot(snapshot_id, create_safety_backup=None):
    found = find_snapshot(snapshot_id)
    if not found:
        return {"ok": False, "message": "Snapshot not found"}
    snap_dir, manifest = found
    appid = manifest.get("appid")
    game_name = manifest.get("gameName")

    if get_running_appid() == int(appid or 0):
        close_game(appid)
    if not wait_for_cloud_sync(appid, 20):
        return {"ok": False, "message": "Steam Cloud still appears to be syncing"}

    restore_files = []
    for item in manifest.get("files", []):
        bucket = item.get("bucket")
        root = item.get("sourceRoot")
        if bucket == "stats":
            root = root or os.path.join(STEAM_PATH, "appcache", "stats")
        elif bucket in ("userdata", "achievements"):
            root = root or os.path.join(STEAM_PATH, "userdata")
        elif bucket == "saves":
            root = root or STEAM_PATH
        elif bucket == "external-saves":
            root = root or item.get("sourceRoot")
        elif bucket == "lua-tools":
            root = root or item.get("sourceRoot")
        if not root:
            continue
        target_relative = str(item.get("targetRelative") or "")
        source = os.path.normpath(os.path.join(snap_dir, item.get("backupRelative", "")))
        target = os.path.normpath(os.path.join(root, target_relative))
        if not os.path.exists(source) or not is_under(root, target):
            continue
        target_root = root
        if bucket in ("userdata", "achievements"):
            parts = [part for part in target_relative.replace("\\", "/").split("/") if part]
            if parts and parts[0].isdigit():
                target_root = os.path.join(root, parts[0])
        restore_files.append({
            "source": source,
            "target": target,
            "targetRoot": target_root,
            "appid": str(appid),
            "bucket": bucket,
            "category": item.get("category"),
            "targetRelative": target_relative,
        })

    if not restore_files:
        return {"ok": False, "message": "Snapshot has no restorable files"}
    # Sempre guarda uma copia silenciosa dos arquivos atuais antes de sobrescrever.
    # Volta ao comportamento da primeira versao: a captura e restaurada pelo .bat
    # externo, sem worker Python intermediario.
    create_safety_backup = False

    set_restore_flag(True)
    try:
        result = launch_external_snapshot_restore(appid, game_name, restore_files, bool(create_safety_backup))
        if not result.get("ok"):
            set_restore_flag(False)
            return result
        log_event("RESTORE", f"External snapshot restore started: {game_name} ({appid}) files={len(restore_files)}")
        return result
    except Exception as e:
        set_restore_flag(False)
        log_event("ERROR", f"External snapshot restore failed to start: {e}")
        return {"ok": False, "message": str(e)}


def restore_safety_backup(safety_path):
    safety_dir = os.path.normpath(str(safety_path or ""))
    safety_root = os.path.normpath(os.path.join(BACKUP_ROOT, "restore-safety"))
    if not safety_dir or not is_under(safety_root, safety_dir):
        return {"ok": False, "message": "Safety backup not allowed"}
    manifest_path = os.path.join(safety_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return {"ok": False, "message": "Safety manifest not found"}
    try:
        manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "message": f"Failed reading safety manifest: {e}"}

    appid = manifest.get("appid") or "0"
    game_name = manifest.get("gameName") or "Backup antes do restore"
    restore_files = []
    for item in manifest.get("files") or []:
        safety_rel = item.get("safetyRelative")
        marker_rel = item.get("deleteMarkerRelative")
        original_target = item.get("originalTarget")
        if not original_target:
            continue
        source = os.path.normpath(os.path.join(safety_dir, safety_rel)) if safety_rel else ""
        marker = os.path.normpath(os.path.join(safety_dir, marker_rel)) if marker_rel else ""
        target = os.path.normpath(str(original_target))
        target_root = os.path.normpath(str(item.get("originalRoot") or os.path.dirname(target)))
        prune_stop = os.path.normpath(str(item.get("pruneStop") or target_root))
        created_directory = os.path.normpath(str(item.get("createdDirectory") or "")) if item.get("createdDirectory") else ""
        created_directory_stop = os.path.normpath(str(item.get("createdDirectoryStop") or item.get("pruneStop") or "")) if (item.get("createdDirectoryStop") or item.get("pruneStop")) else ""
        if item.get("bucket") == "external-saves" and (not item.get("rootExistedBefore", False) or (marker and os.path.exists(marker) and not os.path.exists(source))):
            prune_stop = os.path.normpath(str(item.get("pruneStop") or external_prune_stop(target_root, game_name) or os.path.dirname(target_root)))
            cleanup_cloud = True
        else:
            cleanup_cloud = False
        if not created_directory and marker and os.path.exists(marker):
            inferred_stop = item.get("pruneStop") or cleanup_stop_for_item({
                "target": target,
                "targetRoot": target_root,
                "bucket": item.get("bucket"),
                "category": item.get("category"),
            }, game_name)
            inferred_dir, inferred_stop = created_directory_info(os.path.dirname(target), inferred_stop)
            if inferred_dir and not os.path.exists(inferred_dir):
                created_directory = inferred_dir
                created_directory_stop = inferred_stop
        if (not source or not os.path.exists(source)) and marker and os.path.exists(marker):
            neutral_source = ensure_neutral_librarycache_for_safety(safety_dir, item, appid)
            if neutral_source:
                source = neutral_source
        if source and os.path.exists(source) and is_under(safety_dir, source):
            restore_files.append({
                "action": "copy",
                "source": source,
                "target": target,
                "targetRoot": target_root,
                "pruneStop": prune_stop,
                "createdDirectory": created_directory,
                "createdDirectoryStop": created_directory_stop,
                "cleanupSteamAutoCloud": cleanup_cloud,
                "bucket": item.get("bucket"),
                "category": item.get("category"),
                "targetRelative": item.get("safetyRelative") or os.path.basename(target),
            })
        elif (marker and os.path.exists(marker) and is_under(safety_dir, marker)) or safety_rel:
            restore_files.append({
                "action": "delete",
                "source": marker or source,
                "target": target,
                "targetRoot": target_root,
                "pruneStop": prune_stop,
                "createdDirectory": created_directory,
                "createdDirectoryStop": created_directory_stop,
                "cleanupSteamAutoCloud": cleanup_cloud,
                "bucket": item.get("bucket"),
                "category": item.get("category"),
                "targetRelative": item.get("safetyRelative") or os.path.basename(target),
            })

    if not restore_files:
        return {"ok": False, "message": "Esta copia de seguranca nao tem arquivos ou marcadores validos para restaurar"}

    if get_running_appid() == int(appid or 0):
        close_game(appid)

    set_restore_flag(True)
    try:
        result = launch_external_snapshot_restore(
            appid,
            game_name,
            restore_files,
            create_safety_backup=False,
            restore_kind="safety",
        )
        if not result.get("ok"):
            set_restore_flag(False)
            return result
        log_event("RESTORE", f"Safety restore started: {game_name} ({appid}) files={len(restore_files)}")
        return result
    except Exception as e:
        set_restore_flag(False)
        log_event("ERROR", f"Safety restore failed to start: {e}")
        return {"ok": False, "message": str(e)}
