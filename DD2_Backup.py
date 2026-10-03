"""Dragon's Dogma 2 存檔備份。

自動尋找 Steam 的 DD2 存檔資料夾（userdata\\<帳號>\\2054970\\remote\\win64_save），
與最新一份備份比對，內容有變才建立新備份，最多保留 MAX_BACKUPS 份。

config.ini 可用的設定：
    backup_output_path  備份輸出資料夾（相對路徑以本資料夾為基準）
    save_path           手動指定存檔資料夾；留空或省略時自動偵測

結束代碼：0 = 成功或無需備份，1 = 失敗
"""

import filecmp
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# =========================
# 設定
# =========================

CONFIG_FILE = Path(__file__).with_name("config.ini")

# Dragon's Dogma 2 的 Steam App ID 與存檔相對路徑
STEAM_APP_ID = "2054970"
SAVE_SUBDIR = Path(STEAM_APP_ID) / "remote" / "win64_save"

# SteamID64 與 userdata 資料夾名稱（AccountID）之間的差值
STEAMID64_BASE = 76561197960265728

# 最多保留幾份備份
MAX_BACKUPS = 20


# =========================
# 設定檔
# =========================

def load_config():
    """讀取簡單的 key=value 設定檔，回傳 dict（鍵為小寫）。"""
    if not CONFIG_FILE.is_file():
        raise FileNotFoundError(f"找不到設定檔：{CONFIG_FILE}")

    config = {}
    with CONFIG_FILE.open("r", encoding="utf-8-sig") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if "=" not in line:
                raise ValueError(f"設定檔第 {line_number} 行格式錯誤，應為 key=value")
            key, value = line.split("=", 1)
            config[key.strip().lower()] = value.strip().strip('"')
    return config


def resolve_backup_folder(config):
    backup_path = config.get("backup_output_path")
    if not backup_path:
        raise ValueError("config.ini 缺少 backup_output_path 設定")

    path = Path(os.path.expandvars(backup_path))
    if not path.is_absolute():
        path = CONFIG_FILE.parent / path
    return str(path.resolve())


# =========================
# 偵測 Steam 存檔資料夾
# =========================

def get_steam_paths():
    """列出可能的 Steam 安裝資料夾（登錄檔優先，其次常見路徑），只回傳存在的。"""
    candidates = []

    if sys.platform == "win32":
        import winreg

        registry_keys = [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ]
        for hive, key_path, value_name in registry_keys:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                if value:
                    candidates.append(Path(str(value)))
            except OSError:
                continue

    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / "Steam")

    candidates.append(Path(r"C:\Program Files (x86)\Steam"))
    candidates.append(Path(r"C:\Program Files\Steam"))

    result = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen or not resolved.is_dir():
            continue
        seen.add(key)
        result.append(resolved)
    return result


def find_save_folders(steam_path: Path):
    """回傳該 Steam 資料夾底下所有帳號的 DD2 存檔資料夾：[(account_id, path), ...]。"""
    userdata = steam_path / "userdata"
    if not userdata.is_dir():
        return []

    found = []
    for child in sorted(userdata.iterdir()):
        if not child.is_dir() or not child.name.isdigit():
            continue
        save_folder = child / SAVE_SUBDIR
        if save_folder.is_dir():
            found.append((child.name, save_folder.resolve()))
    return found


def get_login_account_ids(steam_path: Path):
    """從 config/loginusers.vdf 取得帳號清單，最近登入者排前面。回傳 AccountID 字串列表。"""
    vdf = steam_path / "config" / "loginusers.vdf"
    if not vdf.is_file():
        return []

    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    accounts = []
    for match in re.finditer(r'"(\d{17})"\s*\{([^{}]*)\}', text):
        steam_id64, body = match.group(1), match.group(2)
        most_recent = re.search(r'"MostRecent"\s*"1"', body) is not None
        timestamp_match = re.search(r'"Timestamp"\s*"(\d+)"', body)
        timestamp = int(timestamp_match.group(1)) if timestamp_match else 0
        account_id = str(int(steam_id64) - STEAMID64_BASE)
        accounts.append((most_recent, timestamp, account_id))

    accounts.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [account_id for _, _, account_id in accounts]


def detect_save_folder(config, steam_paths=None):
    """決定要備份的存檔資料夾。

    1. config.ini 有 save_path 就直接用。
    2. 否則掃描所有 Steam 安裝位置的 userdata。
       找到多個帳號時，優先用最近登入的 Steam 帳號，其次用最近修改的。
    """
    override = config.get("save_path")
    if override:
        path = Path(os.path.expandvars(override))
        if not path.is_absolute():
            path = CONFIG_FILE.parent / path
        if not path.is_dir():
            raise FileNotFoundError(
                f"config.ini 的 save_path 指向的資料夾不存在：\n{path}"
            )
        return path.resolve(), "config.ini save_path"

    if steam_paths is None:
        steam_paths = get_steam_paths()

    found = []
    seen = set()
    for steam_path in steam_paths:
        for account_id, save_folder in find_save_folders(steam_path):
            key = str(save_folder).lower()
            if key not in seen:
                seen.add(key)
                found.append((steam_path, account_id, save_folder))

    if not found:
        searched = "\n".join(f"  - {path / 'userdata'}" for path in steam_paths) or "  （找不到任何 Steam 安裝位置）"
        raise FileNotFoundError(
            "找不到 Dragon's Dogma 2 的存檔資料夾。\n"
            "已搜尋：\n"
            f"{searched}\n\n"
            "請確認遊戲至少儲存過一次，或在 config.ini 加上：\n"
            f"save_path=<Steam>\\userdata\\<你的帳號ID>\\{SAVE_SUBDIR}"
        )

    if len(found) == 1:
        _, account_id, save_folder = found[0]
        return save_folder, f"自動偵測（Steam 帳號 {account_id}）"

    for steam_path in steam_paths:
        for account_id in get_login_account_ids(steam_path):
            for _, found_account_id, save_folder in found:
                if found_account_id == account_id:
                    return save_folder, f"自動偵測（最近登入的 Steam 帳號 {account_id}）"

    _, account_id, save_folder = max(found, key=lambda item: item[2].stat().st_mtime)
    return save_folder, f"自動偵測（最近修改的 Steam 帳號 {account_id}）"


# =========================
# 備份
# =========================

def get_backup_folders(backup_folder):
    folders = []

    if not os.path.isdir(backup_folder):
        return folders

    for name in os.listdir(backup_folder):
        path = os.path.join(backup_folder, name)
        if os.path.isdir(path) and name.startswith("DD2_Save_"):
            folders.append(path)

    folders.sort(key=os.path.getmtime, reverse=True)
    return folders


def get_latest_backup(backup_folder):
    folders = get_backup_folders(backup_folder)
    return folders[0] if folders else None


def folders_are_equal(left_folder, right_folder):
    """比較資料夾結構與所有檔案內容，忽略修改時間。"""
    left_root = Path(left_folder)
    right_root = Path(right_folder)

    left_dirs = {
        path.relative_to(left_root)
        for path in left_root.rglob("*")
        if path.is_dir()
    }
    right_dirs = {
        path.relative_to(right_root)
        for path in right_root.rglob("*")
        if path.is_dir()
    }
    if left_dirs != right_dirs:
        return False

    left_files = {
        path.relative_to(left_root)
        for path in left_root.rglob("*")
        if path.is_file()
    }
    right_files = {
        path.relative_to(right_root)
        for path in right_root.rglob("*")
        if path.is_file()
    }
    if left_files != right_files:
        return False

    return all(
        filecmp.cmp(left_root / relative_path, right_root / relative_path, shallow=False)
        for relative_path in left_files
    )


def delete_old_backups(backup_folder):
    folders = get_backup_folders(backup_folder)

    old_backups = folders[MAX_BACKUPS:]

    for folder in old_backups:

        try:
            shutil.rmtree(folder)

            print(
                "🗑 已刪除舊備份：",
                os.path.basename(folder)
            )

        except Exception as e:

            print(
                "⚠ 無法刪除：",
                folder,
                e
            )


def create_backup(source_folder, backup_folder):
    """回傳 True 表示成功（含「無需備份」），False 表示失敗。"""

    os.makedirs(backup_folder, exist_ok=True)

    latest_backup = get_latest_backup(backup_folder)
    if latest_backup and folders_are_equal(source_folder, latest_backup):
        print("ℹ️ 存檔內容與最新備份相同，本次不建立新備份。")
        print("最新備份：")
        print(latest_backup)
        return True

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    backup_name = f"DD2_Save_{timestamp}"

    destination = os.path.join(
        backup_folder,
        backup_name
    )

    print("正在備份龍族教義 2 存檔...")
    print()
    print("來源：")
    print(source_folder)
    print()
    print("目的地：")
    print(destination)
    print()

    try:

        shutil.copytree(
            source_folder,
            destination
        )

        print("✅ 備份成功")

        delete_old_backups(backup_folder)
        return True

    except Exception as e:

        print("❌ 備份失敗")
        print(e)
        return False


# =========================
# 主流程
# =========================

def main():
    try:
        config = load_config()
        backup_folder = resolve_backup_folder(config)
    except (OSError, ValueError) as error:
        print(f"❌ 無法讀取設定：{error}")
        return 1

    try:
        source_folder, how = detect_save_folder(config)
    except (OSError, ValueError) as error:
        print(f"❌ {error}")
        return 1

    print(f"存檔資料夾：{source_folder}")
    print(f"（{how}）")
    print()

    return 0 if create_backup(str(source_folder), backup_folder) else 1


if __name__ == "__main__":
    sys.exit(main())
