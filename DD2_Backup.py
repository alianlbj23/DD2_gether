import filecmp
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# =========================
# 設定
# =========================

SOURCE_FOLDER = r"C:\Program Files (x86)\Steam\userdata\1018662919\2054970\remote\win64_save"

CONFIG_FILE = Path(__file__).with_name("config.ini")


def load_config():
    """讀取簡單的 key=value 設定檔。"""
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

    backup_path = config.get("backup_output_path")
    if not backup_path:
        raise ValueError("config.ini 缺少 backup_output_path 設定")

    path = Path(backup_path)
    if not path.is_absolute():
        path = CONFIG_FILE.parent / path
    return str(path.resolve())


try:
    BACKUP_FOLDER = load_config()
except (OSError, ValueError) as error:
    print(f"❌ 無法讀取設定：{error}")
    sys.exit(1)

# 最多保留幾份備份
MAX_BACKUPS = 20


def create_backup():

    if not os.path.isdir(SOURCE_FOLDER):
        print("❌ 找不到存檔資料夾：")
        print(SOURCE_FOLDER)
        input("\n按 Enter 關閉...")
        return

    os.makedirs(BACKUP_FOLDER, exist_ok=True)

    latest_backup = get_latest_backup()
    if latest_backup and folders_are_equal(SOURCE_FOLDER, latest_backup):
        print("ℹ️ 存檔內容與最新備份相同，本次不建立新備份。")
        print("最新備份：")
        print(latest_backup)
        return

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    backup_name = f"DD2_Save_{timestamp}"

    destination = os.path.join(
        BACKUP_FOLDER,
        backup_name
    )

    print("正在備份龍族教義 2 存檔...")
    print()
    print("來源：")
    print(SOURCE_FOLDER)
    print()
    print("目的地：")
    print(destination)
    print()

    try:

        shutil.copytree(
            SOURCE_FOLDER,
            destination
        )

        print("✅ 備份成功")

        delete_old_backups()

    except Exception as e:

        print("❌ 備份失敗")
        print(e)

    # input("\n按 Enter 關閉...")


def get_backup_folders():
    folders = []

    if not os.path.isdir(BACKUP_FOLDER):
        return folders

    for name in os.listdir(BACKUP_FOLDER):
        path = os.path.join(BACKUP_FOLDER, name)
        if os.path.isdir(path) and name.startswith("DD2_Save_"):
            folders.append(path)

    folders.sort(key=os.path.getmtime, reverse=True)
    return folders


def get_latest_backup():
    folders = get_backup_folders()
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


def delete_old_backups():
    folders = get_backup_folders()

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


if __name__ == "__main__":
    create_backup()
