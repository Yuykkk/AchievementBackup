import os
import json
import threading
import urllib.parse
import urllib.request
import subprocess
import shutil
import zipfile
import io
import uuid
import re
import time
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from config import BACKUP_ROOT, PLUGIN_ROOT, SERVER_PORT, SESSION_STATE_FILE, STEAM_PATH, default_backup_root, get_backup_root, ignored_appids, is_ignored_appid, load_user_config, refresh_backup_root, restore_terminal_color, save_user_config, user_config_file, pending_file
from updater import check_update_status, consume_update_result, install_confirmed_update

EXPORT_TASKS = {}
PLUGIN_INSTANCE = None
APP_NAME_CACHE = {}
ACCOUNT_CACHE = None
APP_IMAGE_CACHE = {}
BACKUP_PREFIX = "AchievementBackup-"
META_FILE = "achievementbackup_meta.json"

class AchievementBackupThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def _is_full_backup_folder(name):
    return str(name or "").startswith(BACKUP_PREFIX)

def _strip_backup_prefix(name):
    text = str(name or "")
    if text.startswith(BACKUP_PREFIX):
        return text[len(BACKUP_PREFIX):]
    return text

def _meta_path(folder):
    return os.path.join(folder, META_FILE)

def _send_json(handler, payload, status=200):
    handler.send_response(status)
    handler.send_header('Content-type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Connection', 'close')
    handler.end_headers()
    handler.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))

def _sync_backup_root():
    global BACKUP_ROOT
    BACKUP_ROOT = refresh_backup_root()
    try:
        import achievement_backup
        achievement_backup.BACKUP_ROOT = BACKUP_ROOT
    except:
        pass
    try:
        import monitor
        monitor.BACKUP_ROOT = BACKUP_ROOT
    except:
        pass
    return BACKUP_ROOT

def _pick_backup_folder():
    script = r'''
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.StartPosition = "CenterScreen"
$owner.Width = 1
$owner.Height = 1
$owner.Opacity = 0
$owner.Load.Add({ $owner.Activate() })
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "Escolha onde o AchievementBackup vai salvar backups"
$dialog.ShowNewFolderButton = $true
$result = $dialog.ShowDialog($owner)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::UTF8
  Write-Output $dialog.SelectedPath
}
$owner.Dispose()
'''
    result = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=0x08000000,
    )
    path = (result.stdout or "").strip().splitlines()
    return path[-1].strip() if path else ""

def _pick_export_zip_file(default_name):
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", str(default_name or "achievementbackup-export.zip"))
    if not safe_name.lower().endswith(".zip"):
        safe_name += ".zip"
    script = rf'''
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.StartPosition = "CenterScreen"
$owner.Width = 1
$owner.Height = 1
$owner.Opacity = 0
$owner.Load.Add({{ $owner.Activate() }})
$dialog = New-Object System.Windows.Forms.SaveFileDialog
$dialog.Title = "Salvar exportação do AchievementBackup"
$dialog.Filter = "Arquivo ZIP (*.zip)|*.zip"
$dialog.FileName = "{safe_name}"
$dialog.AddExtension = $true
$dialog.DefaultExt = "zip"
$dialog.OverwritePrompt = $true
$result = $dialog.ShowDialog($owner)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::UTF8
  Write-Output $dialog.FileName
}}
$owner.Dispose()
'''
    result = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=0x08000000,
    )
    path = (result.stdout or "").strip().splitlines()
    return path[-1].strip() if path else ""

def _pick_import_zip_file():
    script = r'''
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.StartPosition = "CenterScreen"
$owner.Width = 1
$owner.Height = 1
$owner.Opacity = 0
$owner.Load.Add({ $owner.Activate() })
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "Escolha o ZIP exportado pelo AchievementBackup"
$dialog.Filter = "Arquivo ZIP (*.zip)|*.zip"
$dialog.CheckFileExists = $true
$dialog.Multiselect = $false
$result = $dialog.ShowDialog($owner)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::UTF8
  Write-Output $dialog.FileName
}
$owner.Dispose()
'''
    result = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=0x08000000,
    )
    path = (result.stdout or "").strip().splitlines()
    return path[-1].strip() if path else ""

def _import_zip_archive(source):
    imported = 0
    with zipfile.ZipFile(source, 'r') as zf:
        names = [name.replace("\\", "/") for name in zf.namelist()]
        snapshot_roots = set()
        for name in names:
            parts = [part for part in name.split("/") if part]
            if len(parts) >= 3 and parts[2].lower() == "manifest.json":
                snapshot_roots.add((parts[0], parts[1]))
        for member in zf.namelist():
            normalized = member.replace("\\", "/")
            parts = [part for part in normalized.split('/') if part]
            if not parts:
                continue
            top = parts[0]
            allowed = _is_full_backup_folder(top) or (len(parts) >= 2 and (parts[0], parts[1]) in snapshot_roots)
            unsafe = any(part in ("", ".", "..") for part in parts) or os.path.isabs(normalized)
            if not allowed or unsafe:
                continue
            dest = os.path.normpath(os.path.join(BACKUP_ROOT, *parts))
            if not _backup_is_under_root(dest):
                continue
            if member.endswith('/'):
                os.makedirs(dest, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(member) as src, open(dest, 'wb') as out:
                    shutil.copyfileobj(src, out)
            imported += 1
    return imported

def _local_app_image(appid):
    appid = str(appid or "").strip()
    if not appid.isdigit():
        return None
    root = os.path.join(STEAM_PATH, "appcache", "librarycache", appid)
    if not os.path.isdir(root):
        return None
    preferred = [
        "library_header.jpg",
        "header.jpg",
        "library_capsule.jpg",
        "library_600x900.jpg",
        "library_hero.jpg",
        "logo.png",
    ]
    for name in preferred:
        direct = os.path.join(root, name)
        if os.path.isfile(direct):
            return direct
    for current, _dirs, files in os.walk(root):
        for name in preferred:
            if name in files:
                return os.path.join(current, name)
    fallback = []
    for current, _dirs, files in os.walk(root):
        for name in files:
            if os.path.splitext(name)[1].lower() in (".jpg", ".jpeg", ".png", ".webp"):
                full = os.path.join(current, name)
                try:
                    fallback.append((os.path.getsize(full), full))
                except:
                    fallback.append((0, full))
    if fallback:
        fallback.sort(reverse=True)
        return fallback[0][1]
    return None

def _remote_app_image_url(appid):
    appid = str(appid or "").strip()
    if not appid.isdigit():
        return None
    cached = APP_IMAGE_CACHE.get(appid)
    if cached:
        return cached
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic"
        req = urllib.request.Request(url, headers={"User-Agent": "AchievementBackup/1.0"})
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8", errors="ignore"))
        info = data.get(appid) or {}
        details = info.get("data") or {}
        image = details.get("capsule_image") or details.get("header_image")
        if image:
            APP_IMAGE_CACHE[appid] = image
            return image
    except Exception as e:
        _log_event("WARN", f"Steam app image lookup failed for {appid}: {e}")
    return None

def _log_event(level, message):
    try:
        from achievement_backup import log_event
        log_event(level, message)
    except:
        try:
            print(f"[AchievementBackup:{level}] {message}")
        except:
            pass

def _collect_backup_files(scope):
    files = []
    if scope == 'all':
        if os.path.exists(BACKUP_ROOT):
            for d in os.listdir(BACKUP_ROOT):
                full = os.path.join(BACKUP_ROOT, d)
                if not os.path.isdir(full) or d.startswith("_"):
                    continue
                if _is_full_backup_folder(d):
                    for root, _, fs in os.walk(full):
                        for name in fs:
                            fpath = os.path.join(root, name)
                            arc = os.path.relpath(fpath, BACKUP_ROOT)
                            files.append((fpath, arc))
                    continue
                for snap in os.listdir(full):
                    snap_dir = os.path.join(full, snap)
                    manifest_path = os.path.join(snap_dir, "manifest.json")
                    if not os.path.isdir(snap_dir) or not os.path.exists(manifest_path):
                        continue
                    for root, _, fs in os.walk(snap_dir):
                        for name in fs:
                            fpath = os.path.join(root, name)
                            arc = os.path.relpath(fpath, BACKUP_ROOT)
                            files.append((fpath, arc))
    else:
        target = os.path.normpath(os.path.join(BACKUP_ROOT, scope))
        if os.path.isdir(target) and _backup_is_under_root(target):
            for root, _, fs in os.walk(target):
                for name in fs:
                    fpath = os.path.join(root, name)
                    arc = os.path.relpath(fpath, BACKUP_ROOT)
                    files.append((fpath, arc))
    return files

def _backup_is_under_root(path):
    try:
        root_abs = os.path.abspath(BACKUP_ROOT).lower()
        path_abs = os.path.abspath(path).lower()
        return path_abs == root_abs or path_abs.startswith(root_abs + os.sep)
    except:
        return False

def _is_under(base, child):
    try:
        base_abs = os.path.abspath(base).lower()
        child_abs = os.path.abspath(child).lower()
        return child_abs == base_abs or child_abs.startswith(base_abs + os.sep)
    except:
        return False

def _parse_acf_value(text, key):
    match = re.search(rf'"{re.escape(key)}"\s+"([^"]+)"', text, re.I)
    return match.group(1) if match else None

def _steamapps_folders():
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

def _app_name(appid):
    appid = str(appid or "").strip()
    if not appid:
        return "App desconhecido"
    if appid in APP_NAME_CACHE:
        return APP_NAME_CACHE[appid]
    for steamapps in _steamapps_folders():
        manifest = os.path.join(steamapps, f"appmanifest_{appid}.acf")
        if not os.path.exists(manifest):
            continue
        try:
            raw = open(manifest, "r", encoding="utf-8", errors="ignore").read()
            name = _parse_acf_value(raw, "name")
            if name:
                APP_NAME_CACHE[appid] = name
                return name
        except:
            pass
    APP_NAME_CACHE[appid] = f"AppID {appid}"
    return APP_NAME_CACHE[appid]

def _account_names():
    global ACCOUNT_CACHE
    if ACCOUNT_CACHE is not None:
        return ACCOUNT_CACHE
    result = {}
    loginusers = os.path.join(STEAM_PATH, "config", "loginusers.vdf")
    try:
        raw = open(loginusers, "r", encoding="utf-8", errors="ignore").read()
        for match in re.finditer(r'"(\d+)"\s*\{(.*?)\n\s*\}', raw, re.S):
            steamid = match.group(1)
            block = match.group(2)
            name = _parse_acf_value(block, "PersonaName") or _parse_acf_value(block, "AccountName")
            if name:
                result[steamid] = name
                try:
                    account_id = str(int(steamid) - 76561197960265728)
                    if int(account_id) > 0:
                        result[account_id] = name
                except:
                    pass
    except:
        pass
    userdata_root = os.path.join(STEAM_PATH, "userdata")
    try:
        for account_id in os.listdir(userdata_root):
            localconfig = os.path.join(userdata_root, account_id, "config", "localconfig.vdf")
            if not account_id.isdigit() or not os.path.exists(localconfig):
                continue
            raw = open(localconfig, "r", encoding="utf-8", errors="ignore").read()
            direct = re.search(rf'"{re.escape(account_id)}"\s*\{{.*?"NameHistory"\s*\{{.*?"0"\s+"([^"]+)"', raw, re.S)
            name = direct.group(1) if direct else _parse_acf_value(raw, "PersonaName")
            if name:
                result[account_id] = name
    except:
        pass
    ACCOUNT_CACHE = result
    return result

def _format_accounts(accounts, include_unknown=False):
    names = _account_names()
    formatted = []
    for account in accounts or []:
        sid = str(account)
        name = names.get(sid)
        if not name and not include_unknown:
            continue
        formatted.append({"id": sid, "name": name or "Nome nao encontrado"})
    return formatted

def _accounts_from_backup_dir(path):
    accounts = []
    userdata = os.path.join(path, "userdata")
    if not os.path.isdir(userdata):
        return accounts
    try:
        for name in os.listdir(userdata):
            full = os.path.join(userdata, name)
            if os.path.isdir(full) and name.isdigit():
                accounts.append(name)
    except:
        pass
    return sorted(dict.fromkeys(accounts))

def _accounts_from_manifest(manifest):
    accounts = []
    for item in manifest.get("files", []):
        rel = str(item.get("targetRelative") or item.get("backupRelative") or "").replace("\\", "/")
        parts = [p for p in rel.split("/") if p]
        if not parts:
            continue
        if parts[0].isdigit():
            accounts.append(parts[0])
        elif len(parts) >= 2 and parts[1].isdigit():
            accounts.append(parts[1])
    return sorted(dict.fromkeys(accounts))

def _folder_stats(path):
    total_size = 0
    total_files = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                total_files += 1
                try:
                    total_size += os.path.getsize(os.path.join(root, name))
                except:
                    pass
    except:
        pass
    return total_size, total_files

def _has_external_saved_files(path, manifest=None):
    try:
        if isinstance(manifest, dict):
            for item in manifest.get("files") or []:
                category = str(item.get("category") or "").lower()
                bucket = str(item.get("bucket") or "").lower()
                if bucket.startswith("external") and category not in ("ludusavi-manifest", "game-save"):
                    return True
            external_items = manifest.get("externalFiles") or manifest.get("external_files") or []
            if isinstance(external_items, list):
                for item in external_items:
                    category = str((item or {}).get("category") or "").lower()
                    if category not in ("ludusavi-manifest", "game-save"):
                        return True
        if os.path.isdir(os.path.join(path, "external-saves")):
            return True
        for root, dirs, _files in os.walk(path):
            if "external-saves" in dirs:
                return True
            rel = os.path.relpath(root, path).replace("\\", "/").lower()
            if rel.startswith("external-saves"):
                return True
    except:
        pass
    return False

def _has_known_save_files(path, manifest=None):
    try:
        if isinstance(manifest, dict):
            for item in manifest.get("files") or []:
                category = str(item.get("category") or "").lower()
                if category in ("ludusavi-manifest", "game-save"):
                    return True
            for item in (manifest.get("externalFiles") or manifest.get("external_files") or []):
                category = str((item or {}).get("category") or "").lower()
                if category in ("ludusavi-manifest", "game-save"):
                    return True
    except:
        pass
    return False

def _iter_snapshots():
    if not os.path.exists(BACKUP_ROOT):
        return
    for game in os.listdir(BACKUP_ROOT):
        game_dir = os.path.join(BACKUP_ROOT, game)
        if not os.path.isdir(game_dir) or game.startswith("_"):
            continue
        if _is_full_backup_folder(game):
            meta_path = _meta_path(game_dir)
            meta_data = {}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)
                except:
                    pass
            yield {
                "folder": game,
                "nickname": meta_data.get("nickname") or meta_data.get("name"),
                "game_name": meta_data.get("game_name"),
                "appid": meta_data.get("appid"),
                "type": "full-backup",
                "timestamp": meta_data.get("timestamp") or game,
                "accounts": _format_accounts(meta_data.get("accounts") or _accounts_from_backup_dir(game_dir)),
            }
            continue
        for snap in os.listdir(game_dir):
            snap_dir = os.path.join(game_dir, snap)
            manifest_path = os.path.join(snap_dir, "manifest.json")
            if not os.path.isdir(snap_dir) or not os.path.exists(manifest_path):
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                if manifest.get("type") not in ("achievement-stats", "unified-game-snapshot"):
                    continue
                yield {
                    "folder": f"{game}/{snap}",
                    "nickname": manifest.get("nickname"),
                    "game_name": manifest.get("gameName") or game,
                    "appid": manifest.get("appid"),
                    "type": "snapshot",
                    "timestamp": manifest.get("timestamp") or snap,
                    "message": "Captura criada apos fechar jogo" if manifest.get("createdAfterGameClose") else "Captura manual",
                    "file_count": manifest.get("fileCount"),
                    "size": manifest.get("size"),
                    "saveMode": manifest.get("saveMode") or ("guarantee" if manifest.get("broadExternalScan") else "safe"),
                    "saveModeLabel": manifest.get("saveModeLabel") or ("Garantia" if manifest.get("broadExternalScan") else "Seguro"),
                    "hasKnownSaves": _has_known_save_files(snap_dir, manifest),
                    "hasExternalSaves": bool(manifest.get("broadExternalScan")) and _has_external_saved_files(snap_dir, manifest),
                    "accounts": _format_accounts(manifest.get("accounts") or _accounts_from_manifest(manifest)),
                }
            except:
                pass

def _iter_full_backups():
    if not os.path.exists(BACKUP_ROOT):
        return
    for d in os.listdir(BACKUP_ROOT):
        full = os.path.join(BACKUP_ROOT, d)
        if not os.path.isdir(full) or not _is_full_backup_folder(d):
            continue
        meta_path = _meta_path(full)
        meta_data = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta_data = json.load(f)
            except:
                pass
        size, file_count = _folder_stats(full)
        yield {
            "folder": d,
            "nickname": meta_data.get("nickname") or meta_data.get("name"),
            "game_name": meta_data.get("game_name"),
            "appid": meta_data.get("appid"),
            "timestamp": meta_data.get("timestamp") or _strip_backup_prefix(d),
            "accounts": _format_accounts(meta_data.get("accounts") or _accounts_from_backup_dir(full)),
            "size": size,
            "file_count": file_count,
            "hasKnownSaves": _has_known_save_files(full, meta_data),
            "hasExternalSaves": _has_external_saved_files(full, meta_data),
        }

def _account_from_file_item(item):
    rel = str(item.get("targetRelative") or item.get("backupRelative") or "").replace("\\", "/")
    parts = [p for p in rel.split("/") if p]
    if not parts:
        return None
    if parts[0].isdigit():
        return parts[0]
    if len(parts) >= 2 and parts[1].isdigit():
        return parts[1]
    return None

def _add_game_detail(games, appid, category, count=1, account=None):
    appid = str(appid or "").strip()
    if not appid or not appid.isdigit():
        return
    if appid not in games:
        games[appid] = {"appid": appid, "name": _app_name(appid), "categories": {}, "totalFiles": 0, "rawAccounts": set()}
    games[appid]["categories"][category] = games[appid]["categories"].get(category, 0) + count
    games[appid]["totalFiles"] += count
    if account and str(account).isdigit():
        games[appid]["rawAccounts"].add(str(account))

def _appid_from_external_folder(name):
    match = re.search(r"\((\d+)\)\s*$", str(name or ""))
    return match.group(1) if match else None

def _finalize_game_details(games):
    details = []
    for game in games.values():
        raw_accounts = sorted(game.pop("rawAccounts", set()))
        game["accounts"] = _format_accounts(raw_accounts)
        details.append(game)
    def sort_key(game):
        name = str(game.get("name") or "")
        unknown = 1 if name.lower().startswith("appid ") else 0
        return (unknown, name.lower(), str(game.get("appid") or ""))
    return sorted(details, key=sort_key)

def _backup_details(folder):
    target = os.path.normpath(os.path.join(BACKUP_ROOT, folder))
    if not _backup_is_under_root(target) or not os.path.isdir(target):
        return None
    meta_path = _meta_path(target)
    meta = {}
    if os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path, "r", encoding="utf-8"))
        except:
            meta = {}
    accounts = meta.get("accounts") or _accounts_from_backup_dir(target)
    games = {}
    global_items = []

    stats_root = os.path.join(target, "appcache_stats")
    if os.path.isdir(stats_root):
        for _root, _dirs, files in os.walk(stats_root):
            for name in files:
                user_stats = re.match(r"UserGameStats_(\d+)_(\d+)\.bin$", name, re.I)
                schema = re.match(r"UserGameStatsSchema_(\d+)\.bin$", name, re.I)
                if user_stats:
                    account, appid = user_stats.groups()
                    _add_game_detail(games, appid, "stats", 1, account)
                elif schema:
                    _add_game_detail(games, schema.group(1), "stats/schema", 1)

    userdata_root = os.path.join(target, "userdata")
    if os.path.isdir(userdata_root):
        for account in os.listdir(userdata_root):
            account_root = os.path.join(userdata_root, account)
            if not os.path.isdir(account_root):
                continue
            for appid in os.listdir(account_root):
                app_root = os.path.join(account_root, appid)
                if not os.path.isdir(app_root) or not appid.isdigit():
                    continue
                count = 0
                for _root, _dirs, files in os.walk(app_root):
                    count += len(files)
                if count:
                    _add_game_detail(games, appid, "userdata/saves", count, account)
            librarycache = os.path.join(account_root, "config", "librarycache")
            if os.path.isdir(librarycache):
                for name in os.listdir(librarycache):
                    appid = os.path.splitext(name)[0]
                    if appid.isdigit():
                        _add_game_detail(games, appid, "achievements/cache", 1, account)

    stplugin_root = os.path.join(target, "stplug-in")
    if os.path.isdir(stplugin_root):
        for name in os.listdir(stplugin_root):
            appid = os.path.splitext(name)[0]
            if appid.isdigit():
                _add_game_detail(games, appid, "lua-tools", 1)

    external_files = meta.get("externalFiles") or meta.get("external_files") or []
    if isinstance(external_files, list) and external_files:
        for item in external_files:
            _add_game_detail(games, item.get("appid") or meta.get("appid"), "external-saves", 1)
    else:
        external_root = os.path.join(target, "external-saves")
        if os.path.isdir(external_root):
            used_new_layout = False
            for game_folder in os.listdir(external_root):
                game_root = os.path.join(external_root, game_folder)
                appid = _appid_from_external_folder(game_folder)
                if not os.path.isdir(game_root) or not appid:
                    continue
                used_new_layout = True
                count = 0
                for _root, _dirs, files in os.walk(game_root):
                    count += len(files)
                if count:
                    _add_game_detail(games, appid, "external-saves", count)
            if not used_new_layout:
                count = 0
                for _root, _dirs, files in os.walk(external_root):
                    count += len(files)
                if count:
                    _add_game_detail(games, meta.get("appid"), "external-saves", count)

    for folder_name, label in (("depotcache", "depotcache"), ("lua", "config/lua")):
        root = os.path.join(target, folder_name)
        if os.path.isdir(root):
            count = 0
            for _r, _d, files in os.walk(root):
                count += len(files)
            if count:
                global_items.append({"name": label, "count": count})

    return {
        "ok": True,
        "type": "backup",
        "folder": folder,
        "timestamp": meta.get("timestamp") or _strip_backup_prefix(folder),
        "accounts": _format_accounts(accounts),
        "games": _finalize_game_details(games),
        "globalItems": global_items,
    }

def _snapshot_details(scope):
    parts = str(scope or "").replace("\\", "/").split("/")
    if len(parts) < 2:
        return None
    snap_dir = os.path.normpath(os.path.join(BACKUP_ROOT, parts[0], parts[1]))
    manifest_path = os.path.join(snap_dir, "manifest.json")
    if not _backup_is_under_root(snap_dir) or not os.path.exists(manifest_path):
        return None
    manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
    games = {}
    appid = manifest.get("appid")
    for item in manifest.get("files", []):
        bucket = item.get("bucket") or "arquivos"
        _add_game_detail(games, item.get("appid") or appid, bucket, 1, _account_from_file_item(item))
    accounts = manifest.get("accounts") or _accounts_from_manifest(manifest)
    return {
        "ok": True,
        "type": "snapshot",
        "folder": scope,
        "timestamp": manifest.get("timestamp"),
        "accounts": _format_accounts(accounts),
        "games": _finalize_game_details(games),
        "globalItems": [],
        "saveMode": manifest.get("saveMode") or ("guarantee" if manifest.get("broadExternalScan") else "safe"),
        "saveModeLabel": manifest.get("saveModeLabel") or ("Garantia" if manifest.get("broadExternalScan") else "Seguro"),
    }

def _start_export_task(scope, output_path=None):
    tid = str(uuid.uuid4())
    files = _collect_backup_files(scope)
    total_bytes = 0
    for fpath, _ in files:
        try:
            total_bytes += os.path.getsize(fpath)
        except:
            pass
    zip_name = f'achievementbackup-backups-{scope}.zip' if scope != 'all' else 'achievementbackup-backups-all.zip'
    zip_path = os.path.abspath(output_path) if output_path else os.path.join(os.environ.get("TEMP", BACKUP_ROOT), zip_name)
    if not zip_path.lower().endswith(".zip"):
        zip_path += ".zip"
    zip_name = os.path.basename(zip_path)
    task = {
        "id": tid,
        "scope": scope,
        "status": "preparing",
        "total_bytes": total_bytes,
        "done_bytes": 0,
        "total_files": len(files),
        "done_files": 0,
        "zip_path": zip_path,
        "filename": zip_name,
        "output_path": zip_path,
        "cancel": False,
    }
    EXPORT_TASKS[tid] = task

    def _runner():
        try:
            os.makedirs(os.path.dirname(zip_path), exist_ok=True)
            task["status"] = "zipping"
            with zipfile.ZipFile(zip_path, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
                for fpath, arc in files:
                    if task.get("cancel"):
                        task["status"] = "canceled"
                        return
                    try:
                        zf.write(fpath, arcname=arc)
                        task["done_files"] += 1
                        try:
                            task["done_bytes"] += os.path.getsize(fpath)
                        except:
                            pass
                    except:
                        pass
            task["status"] = "ready"
        except:
            task["status"] = "error"

    threading.Thread(target=_runner, daemon=True).start()
    return tid

class AchievementBackupRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/ui.js'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            js_path = os.path.join(plugin_root, "public", "index.js")
            try:
                with open(js_path, 'rb') as f:
                    self.wfile.write(f.read())
            except Exception as e:
                self.wfile.write(f"console.error('AchievementBackup UI unavailable', {json.dumps(str(e))});".encode('utf-8'))

        elif self.path.startswith('/asset/app/'):
            appid = urllib.parse.unquote(self.path.split('/asset/app/', 1)[1].split('?', 1)[0])
            image = _local_app_image(appid)
            if not image:
                remote = _remote_app_image_url(appid)
                if remote:
                    self.send_response(302)
                    self.send_header('Location', remote)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.end_headers()
                    return
                self.send_error(404)
                return
            try:
                content_type = mimetypes.guess_type(image)[0] or "image/jpeg"
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                with open(image, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            except:
                self.send_error(500)

        elif self.path.startswith('/assets/'):
            plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            rel = urllib.parse.unquote(self.path.split('/assets/', 1)[1].split('?', 1)[0]).replace("\\", "/")
            rel = rel.strip("/")
            asset_root = os.path.abspath(os.path.join(plugin_root, "public", "assets"))
            target = os.path.abspath(os.path.join(asset_root, rel))
            if not target.startswith(asset_root + os.sep) or not os.path.isfile(target):
                self.send_error(404)
                return
            try:
                content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                with open(target, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
            except:
                self.send_error(500)

        elif self.path == '/check_restore':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            flag_file = os.path.join(BACKUP_ROOT, "restore_success.flag")
            was_restored = False
            restore_type = "backup"
            game_name = None
            appid = None
            summary = None
            ok_count = None
            total_count = None
            fail_count = None
            safety_backup = None
            removed_count = None
            copied_count = None
            if os.path.exists(flag_file):
                was_restored = True
                try:
                    raw = open(flag_file, "r", encoding="utf-8", errors="ignore").read().strip()
                    parts = raw.split("|")
                    if parts and parts[0] in ("snapshot", "safety"):
                        restore_type = parts[0]
                        game_name = parts[1] if len(parts) > 1 else None
                        appid = parts[2] if len(parts) > 2 else None
                        summary = parts[3] if len(parts) > 3 else None
                        ok_count = parts[4] if len(parts) > 4 else None
                        total_count = parts[5] if len(parts) > 5 else None
                        fail_count = parts[6] if len(parts) > 6 else None
                        safety_backup = parts[7] if len(parts) > 7 else None
                        removed_count = parts[8] if len(parts) > 8 else None
                        copied_count = parts[9] if len(parts) > 9 else None
                    elif parts and parts[0] == "backup":
                        restore_type = "backup"
                        summary = parts[1] if len(parts) > 1 else None
                        ok_count = parts[2] if len(parts) > 2 else None
                        total_count = parts[3] if len(parts) > 3 else None
                        fail_count = parts[4] if len(parts) > 4 else None
                    else:
                        summary = None
                        ok_count = None
                        total_count = None
                        fail_count = None
                        safety_backup = None
                        removed_count = None
                        copied_count = None
                except:
                    summary = None
                    ok_count = None
                    total_count = None
                    fail_count = None
                    safety_backup = None
                    removed_count = None
                    copied_count = None
                    pass
                try: os.remove(flag_file) 
                except: pass
            self.wfile.write(json.dumps({
                "restored": was_restored,
                "type": restore_type,
                "gameName": game_name,
                "appid": appid,
                "summary": summary,
                "okCount": ok_count,
                "totalCount": total_count,
                "failCount": fail_count,
                "safetyBackup": safety_backup,
                "removedCount": removed_count,
                "copiedCount": copied_count,
            }).encode())

        elif self.path.startswith('/update/status'):
            try:
                force = "force=1" in self.path
                _send_json(self, check_update_status(force=force))
            except Exception as e:
                _send_json(self, {"ok": False, "available": False, "message": str(e)}, 500)

        elif self.path == '/update/result':
            try:
                result = consume_update_result()
                _send_json(self, {"ok": True, "updated": bool(result), "result": result or {}})
            except Exception as e:
                _send_json(self, {"ok": False, "updated": False, "message": str(e)}, 500)

        elif self.path == '/list':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            backups = list(_iter_full_backups() or [])
            backups.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            self.wfile.write(json.dumps(backups).encode())

        elif self.path == '/settings':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            config = load_user_config()
            config["backup_default_path"] = default_backup_root()
            config["backup_current_path"] = get_backup_root()
            try:
                with open(os.path.join(PLUGIN_ROOT, "plugin.json"), "r", encoding="utf-8") as f:
                    config["plugin_version"] = json.load(f).get("version") or "0.0.0"
            except:
                config["plugin_version"] = "0.0.0"
            self.wfile.write(json.dumps(config).encode())

        elif self.path == '/settings/pick-backup-folder':
            try:
                path = _pick_backup_folder()
                if not path:
                    _send_json(self, {"ok": False, "cancelled": True, "message": "Nenhuma pasta escolhida."}, 409)
                    return
                path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
                os.makedirs(path, exist_ok=True)
                _send_json(self, {"ok": True, "path": path})
            except Exception as e:
                _log_event("ERROR", f"/settings/pick-backup-folder failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)

        elif self.path == '/installed-apps':
            try:
                from achievement_backup import installed_apps
                ignored = ignored_appids()
                apps = []
                for app in installed_apps():
                    appid = str(app.get("appid") or "")
                    apps.append({
                        "appid": appid,
                        "name": app.get("name") or f"AppID {appid}",
                        "common": app.get("common") or "",
                        "ignored": appid in ignored,
                    })
                apps.sort(key=lambda item: (item.get("name") or "").lower())
                _send_json(self, {"ok": True, "apps": apps, "ignored_appids": sorted(ignored)})
            except Exception as e:
                _log_event("ERROR", f"/installed-apps failed: {e}")
                _send_json(self, {"ok": False, "message": str(e), "apps": []}, 500)

        elif self.path.startswith('/pending'):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            pending_data = {"pending": False}
            if os.path.exists(pending_file):
                try:
                    with open(pending_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            if is_ignored_appid(data.get("appid")):
                                try:
                                    os.remove(pending_file)
                                except:
                                    pass
                            else:
                                data["pending"] = True
                                pending_data = data
                except:
                    pass
            self.wfile.write(json.dumps(pending_data).encode())

        elif self.path.startswith('/export/') and not (self.path.startswith('/export/progress/') or self.path.startswith('/export/download/') or self.path.startswith('/export/start')):
            scope = 'all'
            parts = self.path.split('/')
            if len(parts) >= 3 and parts[2]:
                scope = urllib.parse.unquote(parts[2])
            mem = io.BytesIO()
            try:
                with zipfile.ZipFile(mem, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
                    for fpath, arc in _collect_backup_files(scope):
                        zf.write(fpath, arcname=arc)
                mem.seek(0)
                filename = f'achievementbackup-backups-{scope}.zip' if scope != 'all' else 'achievementbackup-backups-all.zip'
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.end_headers()
                self.wfile.write(mem.read())
            except:
                self.send_error(500)
        elif self.path == '/export/start':
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length).decode('utf-8')) if length > 0 else {}
                scope = data.get("scope") or "all"
                output_path = data.get("output_path") or data.get("outputPath")
                tid = _start_export_task(scope, output_path)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"id": tid}).encode())
            except:
                self.send_error(500)
        elif self.path.startswith('/export/progress/'):
            tid = self.path.split('/')[-1]
            task = EXPORT_TASKS.get(tid)
            if not task:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": task["status"],
                "total_bytes": task["total_bytes"],
                "done_bytes": task["done_bytes"],
                "total_files": task["total_files"],
                "done_files": task["done_files"],
                "filename": task["filename"],
                "output_path": task.get("output_path"),
            }).encode())
        elif self.path.startswith('/export/download/'):
            tid = self.path.split('/')[-1]
            task = EXPORT_TASKS.get(tid)
            if not task or task.get("status") != "ready":
                self.send_error(404)
                return
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Disposition', f'attachment; filename="{task["filename"]}"')
                self.end_headers()
                with open(task["zip_path"], 'rb') as f:
                    shutil.copyfileobj(f, self.wfile)
            except:
                self.send_error(500)
        elif self.path == '/achievements/list':
            try:
                from achievement_backup import list_achievement_snapshots
                snapshots = [
                    item for item in list_achievement_snapshots()
                    if not is_ignored_appid(item.get("appid"))
                ]
                for item in snapshots:
                    item["accounts"] = _format_accounts(item.get("accounts") or _accounts_from_manifest(item))
                    item["hasKnownSaves"] = _has_known_save_files(item.get("path") or "", item)
                    item["hasExternalSaves"] = bool(item.get("broadExternalScan")) and _has_external_saved_files(item.get("path") or "", item)
                _send_json(self, snapshots)
            except Exception as e:
                _log_event("ERROR", f"/achievements/list failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)
        elif self.path == '/achievements/stats':
            try:
                from achievement_backup import achievement_stats, get_installed_app
                data = achievement_stats()
                current = data.get("currentAppID") or 0
                if current and is_ignored_appid(current):
                    data["currentAppID"] = 0
                    data["currentGame"] = None
                    data["ignoredCurrentApp"] = False
                elif current:
                    data["currentGame"] = get_installed_app(current)
                _send_json(self, data)
            except Exception as e:
                _log_event("ERROR", f"/achievements/stats failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)
        elif self.path == '/achievements/safety_list':
            _send_json(self, [])
        elif self.path == '/achievements/open':
            try:
                os.makedirs(BACKUP_ROOT, exist_ok=True)
                subprocess.Popen(["explorer", BACKUP_ROOT])
                _send_json(self, {"ok": True, "path": BACKUP_ROOT})
            except Exception as e:
                _log_event("ERROR", f"/achievements/open failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)
        elif self.path == '/session':
            data = {"active": False, "status": "idle", "lastAutoBackup": None}
            try:
                if os.path.exists(SESSION_STATE_FILE):
                    with open(SESSION_STATE_FILE, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data.update(loaded)
            except:
                pass
            _send_json(self, data)
        elif self.path.startswith('/details'):
            try:
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)
                scope = urllib.parse.unquote((qs.get("scope") or [""])[0])
                kind = (qs.get("type") or ["backup"])[0]
                data = _snapshot_details(scope) if kind == "snapshot" else _backup_details(scope)
                if not data:
                    _send_json(self, {"ok": False, "message": "Details not found"}, 404)
                else:
                    _send_json(self, data)
            except Exception as e:
                _log_event("ERROR", f"/details failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)
        elif self.path == '/stats':
            try:
                backup_bytes = 0
                backup_count = 0
                snapshot_bytes = 0
                snapshot_count = 0
                if os.path.exists(BACKUP_ROOT):
                    try:
                        backups = list(_iter_full_backups() or [])
                        snapshots = [item for item in (_iter_snapshots() or []) if item.get("type") == "snapshot"]
                        backup_count = len(backups)
                        snapshot_count = len(snapshots)
                        for backup in backups:
                            full = os.path.join(BACKUP_ROOT, backup.get("folder", ""))
                            if not os.path.isdir(full):
                                continue
                            for root, _, files in os.walk(full):
                                for name in files:
                                    fpath = os.path.join(root, name)
                                    try:
                                        backup_bytes += os.path.getsize(fpath)
                                    except:
                                        pass
                        for snapshot in snapshots:
                            full = os.path.join(BACKUP_ROOT, snapshot.get("folder", ""))
                            if not os.path.isdir(full):
                                continue
                            for root, _, files in os.walk(full):
                                for name in files:
                                    fpath = os.path.join(root, name)
                                    try:
                                        snapshot_bytes += os.path.getsize(fpath)
                                    except:
                                        pass
                    except:
                        pass
                try:
                    usage = shutil.disk_usage(BACKUP_ROOT if os.path.exists(BACKUP_ROOT) else os.getcwd())
                    disk_total_bytes = int(usage.total)
                    disk_free_bytes = int(usage.free)
                except:
                    disk_total_bytes = 0
                    disk_free_bytes = 0
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "backup_bytes": backup_bytes + snapshot_bytes,
                    "backup_only_bytes": backup_bytes,
                    "snapshot_bytes": snapshot_bytes,
                    "backup_count": backup_count,
                    "snapshot_count": snapshot_count,
                    "disk_total_bytes": disk_total_bytes,
                    "disk_free_bytes": disk_free_bytes
                }).encode())
            except:
                self.send_error(500)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b""

        if self.path == '/open_path':
            try:
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
                target_path = os.path.normpath(str(data.get("path") or ""))
                if os.path.exists(target_path) and _backup_is_under_root(target_path):
                    subprocess.Popen(["explorer", target_path])
                    _send_json(self, {"ok": True})
                else:
                    _send_json(self, {"ok": False, "message": "Path not allowed"}, 403)
            except Exception as e:
                _send_json(self, {"ok": False, "message": str(e)}, 500)
            return

        if self.path == '/export/pick-file':
            try:
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
                default_name = data.get("filename") or "achievementbackup-backups-all.zip"
                path = _pick_export_zip_file(default_name)
                if not path:
                    _send_json(self, {"ok": False, "cancelled": True, "message": "Nenhum arquivo escolhido."}, 409)
                    return
                path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
                if not path.lower().endswith(".zip"):
                    path += ".zip"
                os.makedirs(os.path.dirname(path), exist_ok=True)
                _send_json(self, {"ok": True, "path": path, "filename": os.path.basename(path)})
            except Exception as e:
                _log_event("ERROR", f"/export/pick-file failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)
            return

        if self.path == '/achievements/backup':
            try:
                from achievement_backup import create_achievement_snapshot, get_running_appid
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
                appid = data.get("appid") or get_running_appid()
                if is_ignored_appid(appid):
                    _send_json(self, {"ok": False, "message": "Este app esta na lista de ignorados."}, 400)
                    return
                game_name = data.get("game_name") or data.get("gameName")
                result = create_achievement_snapshot(appid, game_name, reason=data.get("reason") or "manual")
                _send_json(self, result, 200 if result.get("ok") else 400)
            except Exception as e:
                _log_event("ERROR", f"/achievements/backup failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)
            return

        if self.path == '/backup/full':
            try:
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
                from monitor import do_backup
                result = do_backup(
                    data.get("appid") or 0,
                    data.get("game_name") or data.get("gameName") or "Steam Session",
                    reason=data.get("reason") or "manual-ui",
                )
                if isinstance(result, dict):
                    _send_json(self, result, 200 if result.get("ok", True) else 400)
                else:
                    _send_json(self, {"ok": True, "result": result})
            except Exception as e:
                _log_event("ERROR", f"/backup/full failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)
            return

        if self.path == '/achievements/restore':
            try:
                from achievement_backup import restore_achievement_snapshot
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
                result = restore_achievement_snapshot(data.get("id"), data.get("createSafetyBackup"))
                _send_json(self, result, 200 if result.get("ok") else 409)
            except Exception as e:
                _log_event("ERROR", f"/achievements/restore failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)
            return

        if self.path == '/achievements/restore_safety':
            _send_json(self, {"ok": False, "message": "Retorno foi desativado."}, 410)
            return
        
        if self.path == '/settings':
            try:
                data = json.loads(raw_body.decode('utf-8'))
                
                cfg = load_user_config()
                
                if "semi_auto" in data:
                    cfg["backup_mode"] = "semi" if data["semi_auto"] else "auto"
                    cfg["semi_auto"] = data["semi_auto"]
                
                # Novo campo backup_mode
                if "backup_mode" in data:
                    mode = str(data["backup_mode"] or "semi")
                    if mode not in ("auto", "semi", "manual"):
                        mode = "semi"
                    cfg["backup_mode"] = mode
                    cfg["semi_auto"] = (mode == "semi")

                if "auto_mode_warning_ack" in data:
                    cfg["auto_mode_warning_ack"] = bool(data.get("auto_mode_warning_ack"))

                if "theme" in data:
                    theme = str(data.get("theme") or "red")
                    if theme in ("red", "purple", "blue", "green"):
                        cfg["theme"] = theme

                if "use_save_location_api" in data:
                    cfg["use_save_location_api"] = bool(data.get("use_save_location_api"))

                if "broad_external_scan" in data:
                    cfg["broad_external_scan"] = bool(data.get("broad_external_scan"))

                if "backup_all_external_saves" in data:
                    cfg["backup_all_external_saves"] = bool(data.get("backup_all_external_saves"))

                if "backup_path" in data:
                    backup_path = str(data.get("backup_path") or "").strip()
                    if backup_path:
                        backup_path = os.path.abspath(os.path.expandvars(os.path.expanduser(backup_path)))
                        os.makedirs(backup_path, exist_ok=True)
                    cfg["backup_path"] = backup_path

                if "capture_restore_safety_mode" in data:
                    mode = str(data.get("capture_restore_safety_mode") or "ask")
                    if mode not in ("ask", "always", "never"):
                        mode = "ask"
                    cfg["capture_restore_safety_mode"] = mode

                if "ignored_appids" in data:
                    raw = data.get("ignored_appids") or []
                    if isinstance(raw, list):
                        cfg["ignored_appids"] = sorted({str(v) for v in raw if str(v).isdigit()}, key=lambda x: int(x))
                        try:
                            if os.path.exists(pending_file):
                                pending_data = json.load(open(pending_file, "r", encoding="utf-8"))
                                if is_ignored_appid(pending_data.get("appid")) or str(pending_data.get("appid") or "") in cfg["ignored_appids"]:
                                    os.remove(pending_file)
                        except:
                            pass
                
                cfg = save_user_config(cfg)
                _sync_backup_root()
                cfg["backup_default_path"] = default_backup_root()
                cfg["backup_current_path"] = get_backup_root()
                
                _send_json(self, {"status": "ok", "config": cfg})
            except Exception as e:
                self.send_error(500, str(e))
            return

        if self.path == '/settings/hotkey':
            try:
                data = json.loads(raw_body.decode('utf-8'))
                enabled = data.get("enabled", False)
                mod = data.get("mod", 0)
                vk = data.get("vk", 0)
                hk_str = data.get("str", "")
                
                cfg = load_user_config()
                
                cfg["hotkey_enabled"] = enabled
                cfg["hotkey_mod"] = mod
                cfg["hotkey_vk"] = vk
                cfg["hotkey_str"] = hk_str
                
                cfg = save_user_config(cfg)
                
                # Atualizar runtime
                if PLUGIN_INSTANCE and PLUGIN_INSTANCE.hotkey:
                    if enabled and vk > 0:
                        PLUGIN_INSTANCE.hotkey.update(mod, vk)
                    else:
                        PLUGIN_INSTANCE.hotkey.stop()
                
                _send_json(self, {"status": "ok", "hotkey_enabled": enabled, "hotkey_mod": mod, "hotkey_vk": vk, "hotkey_str": hk_str})
            except Exception as e:
                self.send_error(500, str(e))
            return

        if self.path.startswith('/restore/'):
            backup_name = self.path.replace('/restore/', '')
            backup_name = urllib.parse.unquote(backup_name)
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"status": "accepted"}')
            threading.Thread(target=trigger_external_restore, args=(backup_name,), daemon=True).start()
        elif self.path == '/update/install':
            try:
                result = install_confirmed_update(restart=True)
                _send_json(self, result)
            except Exception as e:
                _log_event("ERROR", f"/update/install failed: {e}")
                _send_json(self, {"ok": False, "installed": False, "message": str(e)}, 500)
        elif self.path.startswith('/delete/'):
            backup_name = self.path.replace('/delete/', '')
            backup_name = urllib.parse.unquote(backup_name)
            target_path = os.path.join(BACKUP_ROOT, backup_name)
            if os.path.exists(target_path) and os.path.isdir(target_path) and _backup_is_under_root(target_path):
                try:
                    shutil.rmtree(target_path)
                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'{"status": "deleted"}')
                except: self.send_error(500)
            else:
                self.send_error(404)
        elif self.path.startswith('/rename'):
            try:
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
                folder = data.get("folder")
                new_nickname = data.get("new_name")
                if folder:
                    snap_dir = os.path.join(BACKUP_ROOT, folder)
                    manifest_path = os.path.join(snap_dir, "manifest.json")
                    meta_path = _meta_path(snap_dir)
                    if os.path.exists(manifest_path):
                        try:
                            manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
                            manifest["nickname"] = new_nickname
                            with open(manifest_path, "w", encoding="utf-8") as f:
                                json.dump(manifest, f, ensure_ascii=False, indent=2)
                        except:
                            pass
                    current_meta = {}
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r', encoding='utf-8') as f:
                                current_meta = json.load(f)
                        except: pass
                    current_meta["nickname"] = new_nickname
                    with open(meta_path, 'w', encoding='utf-8') as f:
                        json.dump(current_meta, f, ensure_ascii=False)
                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'{"status": "renamed"}')
                else:
                    self.send_error(400)
            except: self.send_error(500)

        elif self.path == '/settings':
            try:
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
                current_config = load_user_config()
                current_config["semi_auto"] = bool(data.get("semi_auto", False))
                current_config["backup_mode"] = "semi" if current_config["semi_auto"] else "manual"
                save_user_config(current_config)

                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"status": "saved"}')
            except:
                self.send_error(500)

        elif self.path == '/pending/action':
            try:
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
                action = data.get("action")

                if os.path.exists(pending_file):
                    try:
                        os.remove(pending_file)
                    except:
                        pass

                if action == "confirm":
                    appid = data.get("appid")
                    game_name = data.get("game_name")
                    if not is_ignored_appid(appid):
                        from achievement_backup import create_achievement_snapshot
                        threading.Thread(target=create_achievement_snapshot, args=(appid, game_name, "semi-close"), daemon=True).start()

                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            except:
                self.send_error(500)

        elif self.path == '/export/start':
            try:
                data = json.loads(raw_body.decode('utf-8')) if raw_body else {}
                scope = data.get("scope") or "all"
                output_path = data.get("output_path") or data.get("outputPath")
                tid = _start_export_task(scope, output_path)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"id": tid}).encode())
            except:
                self.send_error(500)

        elif self.path == '/import':
            try:
                mem = io.BytesIO(raw_body or b"")
                imported = _import_zip_archive(mem)
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "imported", "files": imported}).encode())
            except:
                self.send_error(500)

        elif self.path == '/import/pick-file':
            try:
                path = _pick_import_zip_file()
                if not path:
                    _send_json(self, {"ok": False, "cancelled": True, "message": "Nenhum arquivo escolhido."}, 409)
                    return
                path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
                if not os.path.isfile(path):
                    _send_json(self, {"ok": False, "message": "Arquivo não encontrado."}, 404)
                    return
                imported = _import_zip_archive(path)
                _send_json(self, {"ok": True, "status": "imported", "files": imported, "path": path})
            except Exception as e:
                _log_event("ERROR", f"/import/pick-file failed: {e}")
                _send_json(self, {"ok": False, "message": str(e)}, 500)

    def log_message(self, format, *args): return

def trigger_external_restore(backup_folder_name):
    backup_src = os.path.join(BACKUP_ROOT, backup_folder_name)
    steam_exe = os.path.join(STEAM_PATH, "steam.exe")
    temp_bat = os.path.join(os.environ["TEMP"], "achievementbackup_restore.bat")
    flag_file = os.path.join(BACKUP_ROOT, "restore_success.flag")
    terminal_color = restore_terminal_color()
    def _b(value):
        return str(value).replace("%", "%%")
    restore_labels = []
    label_sources = [
        ("userdata", "userdata"),
        ("appcache_stats", "appcache/stats"),
        ("depotcache", "depotcache"),
        ("lua", "config/lua"),
        ("stplug-in", "stplug-in"),
    ]
    for folder, label in label_sources:
        if os.path.exists(os.path.join(backup_src, folder)):
            restore_labels.append(label)
    restore_file_total = 0
    for folder, _label in label_sources:
        root = os.path.join(backup_src, folder)
        if os.path.isdir(root):
            for _r, _d, files in os.walk(root):
                restore_file_total += len(files)
    external_restore_entries = []
    try:
        meta_path = _meta_path(backup_src)
        meta = json.load(open(meta_path, "r", encoding="utf-8")) if os.path.exists(meta_path) else {}
        for item in meta.get("externalFiles") or []:
            root = item.get("sourceRoot")
            rel = item.get("targetRelative")
            backup_rel = item.get("backupRelative")
            if not root or not rel or not backup_rel:
                continue
            source = os.path.normpath(os.path.join(backup_src, backup_rel))
            target = os.path.normpath(os.path.join(root, rel))
            if os.path.exists(source) and _is_under(backup_src, source) and _is_under(root, target):
                external_restore_entries.append({
                    "source": source,
                    "target": target,
                    "label": item.get("gameName") or item.get("appid") or "external-save",
                })
    except:
        external_restore_entries = []
    restore_file_total += len(external_restore_entries)
    bat_content = [
        "@echo off",
        "setlocal EnableExtensions EnableDelayedExpansion",
        "title AchievementBackup - Restauracao Completa",
        f"color {terminal_color}",
        "cls",
        "set \"TITLE_MAIN=AchievementBackup :: FULL BACKUP RESTORE\"",
        "set \"SUBTITLE=Restaurando seu Steam backup com seguranca.\"",
        "set /a OK=0",
        "set /a FAIL=0",
        "set /a TOTAL=0",
        "set /a FILE_DONE=0",
        f"set /a FILE_TOTAL={max(restore_file_total, 1)}",
        "set /a STEP=0",
        "set /a STEPS=8",
        "call :progress Preparando restore",
        "timeout /t 3 /nobreak >nul",
        "call :progress Fechando processos da Steam",
        "taskkill /F /IM steam.exe >nul 2>&1",
        "taskkill /F /IM steamwebhelper.exe >nul 2>&1",
        "taskkill /F /IM steamerrorreporter.exe >nul 2>&1",
        "timeout /t 3 /nobreak >nul",
        "set /a STEP=1",
        "call :progress Steam fechada com seguranca",
        f'set "BACKUP={_b(backup_src)}"',
        f'set "STEAM={_b(STEAM_PATH)}"',
        "call :copytree userdata \"%BACKUP%\\userdata\" \"%STEAM%\\userdata\"",
        "call :copytree appcache_stats \"%BACKUP%\\appcache_stats\" \"%STEAM%\\appcache\\stats\"",
        "call :copytree depotcache \"%BACKUP%\\depotcache\" \"%STEAM%\\depotcache\"",
        "call :copytree lua \"%BACKUP%\\lua\" \"%STEAM%\\config\\lua\"",
        "call :copytree stplug-in \"%BACKUP%\\stplug-in\" \"%STEAM%\\config\\stplug-in\"",
    ]
    if external_restore_entries:
        restore_labels.append("saves externos")
        bat_content.extend([
            "call :progress Restaurando saves externos",
        ])
        for idx, item in enumerate(external_restore_entries, start=1):
            target_dir = os.path.dirname(item["target"])
            bat_content.extend([
                f"call :progress Save externo {idx}/{len(external_restore_entries)} - {_b(os.path.basename(item['target']))}",
                f'set "SRC={_b(item["source"])}"',
                f'set "DST={_b(item["target"])}"',
                f'set "DSTDIR={_b(target_dir)}"',
                "set /a TOTAL+=1",
                'if not exist "%DSTDIR%" mkdir "%DSTDIR%" >nul 2>&1',
                'if exist "%SRC%" (',
                '  if exist "%DST%" attrib -R "%DST%" >nul 2>&1',
                '  copy /Y "%SRC%" "%DST%" >nul',
                '  if errorlevel 1 (set /a FAIL+=1) else (set /a OK+=1)',
                ') else (',
                '  set /a FAIL+=1',
                ')',
                "set /a FILE_DONE+=1",
            ])
    summary_text = ", ".join(restore_labels or ["backup da Steam"])
    bat_content.extend([
        f'set "RESTORE_FLAG=backup|{_b(summary_text)}|%OK%|%TOTAL%|%FAIL%"',
        f'echo(!RESTORE_FLAG! > "{flag_file}"',
        "set /a STEP=STEPS-1",
        "call :progress Registrando restore",
        f'start "" "{_b(steam_exe)}"',
        "set /a STEP=STEPS",
        "call :progress Abrindo Steam novamente",
        "echo.",
        "echo Itens restaurados neste backup:",
    ])
    for label in restore_labels or ["backup da Steam"]:
        bat_content.append(f"echo - {_b(label)}")
    bat_content.extend([
        "echo.",
        "echo Restauracao concluida.",
        "echo Arquivos copiados: %OK% de %TOTAL%",
        "echo Falhas estimadas: %FAIL%",
        "echo.",
        "timeout /t 8 /nobreak >nul",
        '(goto) 2>nul & del "%~f0"',
        "",
        ":progress",
        "set \"MSG=%~1\"",
        "if %FILE_TOTAL% LEQ 0 set /a FILE_TOTAL=1",
        "set /a PCT100=(FILE_DONE*10000)/FILE_TOTAL",
        "set /a PCT_INT=PCT100/100",
        "set /a PCT_FRAC=PCT100%%100",
        "if !PCT_FRAC! LSS 10 (set \"PCT=!PCT_INT!,0!PCT_FRAC!\") else (set \"PCT=!PCT_INT!,!PCT_FRAC!\")",
        "set \"BAR=\"",
        "for /L %%B in (1,1,28) do (",
        "  set /a LIM=FILE_DONE*28/FILE_TOTAL",
        "  if %%B LEQ !LIM! (set \"BAR=!BAR!#\") else (set \"BAR=!BAR!-\")",
        ")",
        "cls",
        "echo !TITLE_MAIN!",
        "echo !SUBTITLE!",
        "echo.",
        "echo [!BAR!] !PCT!%%",
        "echo.",
        "echo Agora: !MSG!",
        "echo Arquivos: !FILE_DONE! de !FILE_TOTAL!  ^|  OK: !OK!  Falhas: !FAIL!",
        "echo.",
        "goto :eof",
        "",
        ":copytree",
        "set \"LABEL=%~1\"",
        "set \"SRC=%~2\"",
        "set \"DST=%~3\"",
        "set /a STEP+=1",
        "if %STEP% GTR %STEPS% set /a STEP=STEPS",
        "call :progress Restaurando %LABEL%",
        "if not exist \"%SRC%\" (echo IGNORADO: origem ausente & goto :eof)",
        "set /a COUNT=0",
        "for /R \"%SRC%\" %%F in (*) do set /a COUNT+=1",
        "set /a TOTAL+=COUNT",
        "if not exist \"%DST%\" mkdir \"%DST%\" >nul 2>&1",
        "for /R \"%SRC%\" %%F in (*) do (",
        "  set \"REL=%%F\"",
        "  set \"REL=!REL:%SRC%\\=!\"",
        "  set \"OUT=%DST%\\!REL!\"",
        "  for %%D in (\"!OUT!\") do if not exist \"%%~dpD\" mkdir \"%%~dpD\" >nul 2>&1",
        "  if exist \"!OUT!\" attrib -R \"!OUT!\" >nul 2>&1",
        "  copy /Y \"%%F\" \"!OUT!\" >nul",
        "  if errorlevel 1 (set /a FAIL+=1) else (set /a OK+=1)",
        "  set /a FILE_DONE+=1",
        "  call :progress \"%LABEL% - !REL!\"",
        ")",
        "goto :eof",
    ])
    try:
        with open(temp_bat, "w") as f:
            f.write("\n".join(bat_content))
        subprocess.Popen([temp_bat], creationflags=subprocess.CREATE_NEW_CONSOLE)
    except: pass

def start_server(plugin_instance=None):
    global PLUGIN_INSTANCE
    PLUGIN_INSTANCE = plugin_instance
    
    # Carregar hotkey inicial
    try:
        cfg = load_user_config()
        if cfg.get("hotkey_enabled", False):
            mod = cfg.get("hotkey_mod", 0)
            vk = cfg.get("hotkey_vk", 0)
            if PLUGIN_INSTANCE and PLUGIN_INSTANCE.hotkey:
                PLUGIN_INSTANCE.hotkey.update(mod, vk)
    except:
        pass

    server_address = ('localhost', SERVER_PORT)
    while True:
        try:
            httpd = AchievementBackupThreadingHTTPServer(server_address, AchievementBackupRequestHandler)
            httpd.timeout = 2
            print(f"[AchievementBackup] Servidor rodando na porta {SERVER_PORT}")
            httpd.serve_forever()
            break
        except OSError as e:
            _log_event("WARN", f"Server bind failed on port {SERVER_PORT}: {e}; retrying")
            time.sleep(2)
        except Exception as e:
            _log_event("ERROR", f"Server crashed: {e}; retrying")
            time.sleep(2)
