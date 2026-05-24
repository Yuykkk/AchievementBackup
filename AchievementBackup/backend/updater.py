import json
import os
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile

from config import PLUGIN_ROOT

REPO_OWNER = "Yuykkk"
REPO_NAME = "AchievementBackup"
BRANCH = "main"
REMOTE_PLUGIN_JSON = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}/AchievementBackup/plugin.json"
REMOTE_ZIP = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/archive/refs/heads/{BRANCH}.zip"
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
FIRST_CHECK_DELAY_SECONDS = 45
PRESERVED_TOP_LEVEL = {"profile", "backups", "logs", "cache", ".git"}
PRESERVED_FILES = {
    os.path.normcase(os.path.join("backend", "user_config.json")),
    os.path.normcase(os.path.join("backend", "pending.json")),
}


def _log(message):
    try:
        print(f"[AchievementBackup:Updater] {message}")
    except:
        pass


def _read_local_plugin_json():
    path = os.path.join(PLUGIN_ROOT, "plugin.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def _fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AchievementBackup-Updater/2.1"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8", errors="ignore"))


def _version_tuple(value):
    parts = []
    for chunk in str(value or "0").replace("-", ".").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def update_available():
    local = _read_local_plugin_json()
    remote = _fetch_json(REMOTE_PLUGIN_JSON)
    local_version = local.get("version") or "0.0.0"
    remote_version = remote.get("version") or "0.0.0"
    return _version_tuple(remote_version) > _version_tuple(local_version), local_version, remote_version


def _copy_tree_contents(source_root):
    for name in os.listdir(source_root):
        if name in PRESERVED_TOP_LEVEL:
            continue
        source = os.path.join(source_root, name)
        target = os.path.join(PLUGIN_ROOT, name)
        if os.path.isdir(source):
            for current, dirs, files in os.walk(source):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                rel_dir = os.path.relpath(current, source_root)
                for filename in files:
                    rel_file = os.path.normpath(os.path.join(rel_dir, filename))
                    if os.path.normcase(rel_file) in PRESERVED_FILES:
                        continue
                    src_file = os.path.join(current, filename)
                    dst_file = os.path.join(PLUGIN_ROOT, rel_file)
                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                    shutil.copy2(src_file, dst_file)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)


def install_latest():
    with tempfile.TemporaryDirectory(prefix="achievementbackup-update-") as tmp:
        zip_path = os.path.join(tmp, "repo.zip")
        req = urllib.request.Request(REMOTE_ZIP, headers={"User-Agent": "AchievementBackup-Updater/2.1"})
        with urllib.request.urlopen(req, timeout=120) as response, open(zip_path, "wb") as out:
            shutil.copyfileobj(response, out)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)
        roots = [
            os.path.join(tmp, name)
            for name in os.listdir(tmp)
            if os.path.isdir(os.path.join(tmp, name)) and name.startswith(f"{REPO_NAME}-")
        ]
        if not roots:
            raise RuntimeError("Pacote do GitHub sem pasta do plugin.")
        plugin_source = os.path.join(roots[0], "AchievementBackup")
        if not os.path.isdir(plugin_source):
            plugin_source = roots[0]
        _copy_tree_contents(plugin_source)


def check_once():
    try:
        available, local_version, remote_version = update_available()
        if not available:
            _log(f"Atualizado ({local_version}).")
            return False
        _log(f"Atualizacao encontrada: {local_version} -> {remote_version}.")
        install_latest()
        _log("Atualizacao instalada. Reinicie a Steam para carregar todos os arquivos novos.")
        return True
    except Exception as exc:
        _log(f"Falha ao verificar atualizacao: {exc}")
        return False


def start_auto_update():
    def _runner():
        time.sleep(FIRST_CHECK_DELAY_SECONDS)
        while True:
            check_once()
            time.sleep(CHECK_INTERVAL_SECONDS)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return thread
