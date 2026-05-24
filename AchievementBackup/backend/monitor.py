import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
import winreg
from datetime import datetime

from config import BACKUP_ROOT, BACKUP_TARGETS, RESTORE_FLAG_FILE, SESSION_STATE_FILE, is_ignored_appid, ignored_appids, pending_file, user_config_file
from ui import show_notification

BACKUP_PREFIX = "AchievementBackup-"
META_FILE = "achievementbackup_meta.json"


def get_game_name_global(appid):
    if not appid or appid == 0:
        return "Steam Session"
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
            if str(appid) in data and data[str(appid)]["success"]:
                return data[str(appid)]["data"]["name"]
    except:
        pass
    return f"AppID {appid}"


def write_session_state(state):
    try:
        os.makedirs(os.path.dirname(SESSION_STATE_FILE), exist_ok=True)
        with open(SESSION_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except:
        pass


def read_backup_mode():
    backup_mode = "semi"
    if os.path.exists(user_config_file):
        try:
            with open(user_config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if "backup_mode" in cfg:
                    backup_mode = cfg["backup_mode"]
                elif cfg.get("semi_auto", False):
                    backup_mode = "semi"
                if backup_mode == "auto" and not cfg.get("auto_mode_warning_ack", False):
                    backup_mode = "semi"
        except:
            pass
    return backup_mode


def restore_in_progress():
    if not os.path.exists(RESTORE_FLAG_FILE):
        return False
    try:
        if time.time() - os.path.getmtime(RESTORE_FLAG_FILE) > 10 * 60:
            os.remove(RESTORE_FLAG_FILE)
            return False
    except:
        pass
    return True


def accounts_from_userdata_backup(dest_folder):
    accounts = []
    userdata = os.path.join(dest_folder, "userdata")
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


def do_backup(appid, game_name=None, reason="auto-close"):
    from achievement_backup import backup_external_saves_for_all_games, log_event, wait_for_cloud_sync

    try:
        appid = int(appid or 0)
    except:
        appid = 0
    if not game_name:
        game_name = get_game_name_global(appid)

    if appid > 0:
        log_event("WAITING", "Waiting Steam sync...")
        wait_for_cloud_sync(appid, 20)

    os.makedirs(BACKUP_ROOT, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder_name = f"{BACKUP_PREFIX}{timestamp}"
    dest_folder = os.path.join(BACKUP_ROOT, folder_name)
    success_count = 0
    copied_targets = []

    log_event("BACKUP", f"Full backup started: {game_name} ({appid or 'all'}) path={dest_folder}")
    for target in BACKUP_TARGETS:
        src = target["src"]
        dst = os.path.join(dest_folder, target["name"])
        try:
            if not os.path.exists(src):
                continue
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            success_count += 1
            copied_targets.append(target["name"])
        except Exception as e:
            log_event("WARN", f"Full backup copy failed for {target['name']}: {e}")

    if success_count <= 0:
        log_event("WARN", "Full backup skipped: no configured targets were copied")
        return {"ok": False, "message": "No configured backup targets were copied"}

    external_result = backup_external_saves_for_all_games(dest_folder)

    meta = {
        "appid": appid,
        "game_name": game_name,
        "nickname": None,
        "timestamp": timestamp,
        "reason": reason,
        "scope": "full-steam",
        "targets": copied_targets,
        "accounts": accounts_from_userdata_backup(dest_folder),
        "external_save_files": external_result.get("count", 0),
        "external_save_bytes": external_result.get("bytes", 0),
        "external_save_scan_enabled": bool(external_result.get("enabled")),
        "external_save_skipped_bytes": external_result.get("skippedBytes", 0),
        "externalFiles": external_result.get("files", []),
    }
    try:
        with open(os.path.join(dest_folder, META_FILE), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event("WARN", f"Full backup metadata failed: {e}")

    log_event("BACKUP", f"Full backup created successfully: filesets={success_count} path={dest_folder}")
    show_notification("AchievementBackup", f"Backup completo criado após fechar {game_name}.")
    return {"ok": True, "id": folder_name, "folder": folder_name, "path": dest_folder, "meta": meta}


class BackupManager(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.last_appid = 0
        self.last_seen_appid = 0
        self.active_appid = 0
        self.active_game_name = None
        self.active_sessions = {}
        self.closing_sessions = set()
        self.installed_apps_cache = []
        self.installed_apps_cache_time = 0
        self.session_started_at = None
        self.last_auto_backup = None
        self.initialized = False

    def get_running_appid(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            val, _ = winreg.QueryValueEx(key, "RunningAppID")
            winreg.CloseKey(key)
            return int(val)
        except:
            return 0

    def get_running_games(self):
        running = {}
        ignored = ignored_appids()
        try:
            from achievement_backup import installed_apps, is_under
            output = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Process | Where-Object {$_.Path} | Select-Object -ExpandProperty Path"],
                timeout=6,
                creationflags=0x08000000,
            ).decode("utf-8", errors="ignore")
            process_paths = [line.strip() for line in output.splitlines() if line.strip()]
            if not self.installed_apps_cache or time.time() - self.installed_apps_cache_time > 60:
                self.installed_apps_cache = installed_apps()
                self.installed_apps_cache_time = time.time()
            apps = self.installed_apps_cache
            for app in apps:
                if str(app.get("appid") or "") in ignored:
                    continue
                common = app.get("common")
                if not common or not os.path.isdir(common):
                    continue
                for path in process_paths:
                    if is_under(common, path):
                        running[str(app["appid"])] = app
                        break
        except:
            pass

        current = self.get_running_appid()
        if current > 0 and not is_ignored_appid(current) and str(current) not in running:
            try:
                from achievement_backup import get_installed_app
                running[str(current)] = get_installed_app(current, get_game_name_global(current))
            except:
                running[str(current)] = {"appid": str(current), "name": get_game_name_global(current)}
        return running

    def force_backup(self):
        running = self.get_running_games()
        current = self.get_running_appid()
        target = current if current > 0 and not is_ignored_appid(current) else self.last_appid
        if target and is_ignored_appid(target):
            target = 0
        if not target and running:
            target = int(next(iter(running.keys())))

        if target > 0:
            game_name = get_game_name_global(target)
            print(f"[AchievementBackup] Hotkey acionada para {game_name}")
            show_notification("AchievementBackup", f"Quick-Save: {game_name}")
            do_backup(target, game_name, reason="manual")
        else:
            print("[AchievementBackup] Hotkey acionada mas nenhum jogo detectado")
            show_notification("AchievementBackup", "Nenhum jogo detectado para backup.")

    def stop(self):
        self.running = False

    def write_multi_session_state(self, status="monitoring"):
        current_ids = sorted(self.active_sessions.keys())
        current_games = [self.active_sessions[appid]["name"] for appid in current_ids]
        write_session_state({
            "active": bool(current_ids),
            "currentAppID": int(current_ids[0]) if len(current_ids) == 1 and current_ids[0].isdigit() else 0,
            "currentGame": current_games[0] if len(current_games) == 1 else (", ".join(current_games) if current_games else None),
            "activeGames": [
                {
                    "appid": int(appid) if str(appid).isdigit() else appid,
                    "name": data.get("name"),
                    "startedAt": data.get("startedAt"),
                }
                for appid, data in self.active_sessions.items()
            ],
            "status": status,
            "lastAutoBackup": self.last_auto_backup,
        })

    def start_session(self, appid, game_name=None):
        from achievement_backup import log_event

        appid = str(appid)
        if is_ignored_appid(appid):
            log_event("INFO", f"Ignored app session skipped: {game_name or appid} ({appid})")
            return
        game_name = game_name or get_game_name_global(appid)
        if appid in self.active_sessions or appid in self.closing_sessions:
            return
        self.active_appid = int(appid) if appid.isdigit() else 0
        self.active_game_name = game_name
        started_at = datetime.now().isoformat(timespec="seconds")
        self.session_started_at = started_at
        self.active_sessions[appid] = {"appid": appid, "name": game_name, "startedAt": started_at}
        self.last_appid = int(appid) if appid.isdigit() else 0
        log_event("SESSION START", f"{game_name} detected")
        self.write_multi_session_state("monitoring")

    def finish_session(self, appid=None):
        from achievement_backup import log_event

        if appid is None:
            appid = str(self.active_appid)
        appid = str(appid)
        if appid in self.closing_sessions:
            return
        self.closing_sessions.add(appid)
        session = self.active_sessions.get(appid, {})
        closed_appid = int(appid) if appid.isdigit() else 0
        game_name = session.get("name") or self.active_game_name or get_game_name_global(closed_appid)
        if is_ignored_appid(closed_appid):
            log_event("INFO", f"Ignored app removed from active session without backup: {game_name} ({closed_appid})")
            self.active_sessions.pop(appid, None)
            self.closing_sessions.discard(appid)
            if not self.active_sessions:
                self.active_appid = 0
                self.active_game_name = None
                self.session_started_at = None
            self.write_multi_session_state("idle" if not self.active_sessions else "monitoring")
            return
        if restore_in_progress():
            log_event("INFO", f"Auto backup skipped during snapshot restore: {game_name} ({closed_appid})")
            self.active_sessions.pop(appid, None)
            self.closing_sessions.discard(appid)
            self.write_multi_session_state("restore_in_progress")
            return

        log_event("SESSION END", f"{game_name} closed")
        log_event("WAITING", "Waiting Steam sync...")
        write_session_state({
            "active": False,
            "currentAppID": closed_appid,
            "currentGame": game_name,
            "status": "waiting_sync",
            "lastAutoBackup": self.last_auto_backup,
        })

        time.sleep(15)
        backup_mode = read_backup_mode()

        if backup_mode == "semi":
            try:
                with open(pending_file, "w", encoding="utf-8") as f:
                    json.dump({"appid": closed_appid, "game_name": game_name}, f, ensure_ascii=False)
                show_notification("AchievementBackup", f"Aguardando confirmacao de captura para {game_name}.")
            except:
                pass
        elif backup_mode == "auto":
            from achievement_backup import create_achievement_snapshot
            result = create_achievement_snapshot(closed_appid, game_name, reason="auto-close")
            if result and result.get("ok"):
                self.last_auto_backup = {
                    "appid": closed_appid,
                    "gameName": game_name,
                    "backupId": result.get("id"),
                    "message": "Captura criada apos fechar jogo",
                    "time": datetime.now().isoformat(timespec="seconds"),
                }
        else:
            log_event("INFO", f"Close capture skipped for {game_name}; mode={backup_mode}")

        self.active_sessions.pop(appid, None)
        self.closing_sessions.discard(appid)
        if not self.active_sessions:
            self.active_appid = 0
            self.active_game_name = None
            self.session_started_at = None
        self.write_multi_session_state("idle" if not self.active_sessions else "monitoring")

    def run(self):
        print("[AchievementBackup] Monitor ativo (Game Awareness ON).")
        while self.running:
            running_games = self.get_running_games()
            current_appid = self.get_running_appid()
            visible_current = 0 if is_ignored_appid(current_appid) else current_appid

            if not self.initialized:
                self.initialized = True
                self.last_seen_appid = visible_current
                self.active_sessions = {}
                write_session_state({
                    "active": False,
                    "currentAppID": visible_current,
                    "currentGame": get_game_name_global(visible_current) if visible_current else None,
                    "activeGames": [],
                    "status": "idle" if not running_games else "monitor_started_with_game_already_running",
                    "lastAutoBackup": self.last_auto_backup,
                })
                if running_games:
                    try:
                        from achievement_backup import log_event
                        log_event("INFO", f"Monitor started with games already running: {', '.join(running_games.keys())}; waiting for next clean launch")
                    except:
                        pass
                time.sleep(2)
                continue

            for appid, app in running_games.items():
                if appid not in self.active_sessions:
                    self.start_session(appid, app.get("name"))

            for appid in list(self.active_sessions.keys()):
                if appid not in running_games:
                    threading.Thread(target=self.finish_session, args=(appid,), daemon=True).start()

            if self.active_sessions:
                self.write_multi_session_state("monitoring")

            self.last_seen_appid = visible_current
            time.sleep(2)
