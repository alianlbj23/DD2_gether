"""DD2gether 自動更新。

從 GitHub（But-Frog/dd2-together-release）取得最新的 DD2gether 版本，
若比本機安裝的版本新，就下載、解壓到新資料夾、搬移使用者設定，
並更新 config.ini 的 dd2gether_path。

若本機完全沒有 DD2gether（例如剛 clone 下來），會直接下載最新版並建立 config.ini。

結束代碼：
    0 = 已是最新版，或已成功更新
    1 = 檢查/更新失敗（舊版仍可正常使用）

可選參數：
    --check-only   只比對版本，不下載
    --zip <路徑>   使用本機已下載的 zip 進行安裝（離線測試用）
"""

import json
import re
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# =========================
# 設定
# =========================

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.ini"
TEMP_DIR = ROOT / "_dd2gether_update"

DEFAULT_REPO = "But-Frog/dd2-together-release"
ASSET_PATTERN = re.compile(r"^DD2gether-alpha-(\d+(?:\.\d+)*)\.zip$", re.IGNORECASE)
VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)+)")

HTTP_TIMEOUT = 30
USER_AGENT = "DD2-Auto-Backup-Updater"

# 更新時從舊版複製到新版的使用者資料（相對於啟動器資料夾）
USER_DATA_DIRS = ["data"]


# =========================
# 設定檔
# =========================

DEFAULT_CONFIG_LINES = [
    "# DD2gether executable path",
    "dd2gether_path=",
    "",
    "# Backup output folder",
    "backup_output_path=Backups",
    "",
    "# Auto-update DD2gether from GitHub before launch (1=on, 0=off)",
    "auto_update=1",
    "",
    "# GitHub repository that publishes DD2gether releases",
    f"dd2gether_repo={DEFAULT_REPO}",
]


def read_config_lines():
    """讀取 config.ini；不存在時回傳預設內容（之後由 write_config_path 寫入）。"""
    if not CONFIG_FILE.is_file():
        return list(DEFAULT_CONFIG_LINES)
    with CONFIG_FILE.open("r", encoding="utf-8-sig") as file:
        return file.read().splitlines()


def parse_config(lines):
    config = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip().lower()] = value.strip().strip('"')
    return config


def is_truthy(value, default=True):
    if value is None or value == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def write_config_path(lines, new_exe: Path, old_was_relative: bool):
    """只改寫 dd2gether_path 那一行，其餘內容保持原樣。"""
    if old_was_relative:
        try:
            new_value = str(new_exe.relative_to(ROOT))
        except ValueError:
            new_value = str(new_exe)
    else:
        new_value = str(new_exe)

    replaced = False
    result = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if "=" in stripped and not stripped.startswith(("#", ";")):
            key = stripped.split("=", 1)[0].strip().lower()
            if key == "dd2gether_path":
                result.append(f"dd2gether_path={new_value}")
                replaced = True
                continue
        result.append(raw_line)

    if not replaced:
        result.append(f"dd2gether_path={new_value}")

    with CONFIG_FILE.open("w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(result) + "\n")

    return new_value


# =========================
# 版本
# =========================

def parse_version(text):
    """從字串中取出第一個 x.y[.z] 版本號，回傳整數 tuple。"""
    if not text:
        return None
    match = VERSION_PATTERN.search(text)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def version_to_str(version):
    return ".".join(str(part) for part in version)


def get_local_version(launcher_dir: Path):
    """本機版本：優先讀 payload_manifest.json，其次 version.lua，最後看資料夾名稱。"""
    manifest = launcher_dir / "payload" / "payload_manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8-sig"))
            version = parse_version(str(data.get("version", "")))
            if version:
                return version, "payload_manifest.json"
        except (OSError, ValueError):
            pass

    version_lua = launcher_dir / "payload" / "reframework" / "autorun" / "coop" / "version.lua"
    if version_lua.is_file():
        try:
            version = parse_version(version_lua.read_text(encoding="utf-8", errors="ignore"))
            if version:
                return version, "version.lua"
        except OSError:
            pass

    version = parse_version(launcher_dir.name)
    if version:
        return version, "資料夾名稱"

    return None, None


# =========================
# GitHub
# =========================

def http_get(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    return urllib.request.urlopen(request, timeout=HTTP_TIMEOUT)


def find_latest_release(repo: str):
    """回傳 (版本 tuple, 版本字串, 下載網址, 檔案大小, release 名稱)。

    DD2gether 的 release 是標記為 pre-release 的滾動版本（tag = alpha），
    所以不能用 /releases/latest，要列出 releases 後自行挑選。
    """
    url = f"https://api.github.com/repos/{repo}/releases?per_page=10"
    with http_get(url) as response:
        releases = json.load(response)

    best = None
    for release in releases:
        if release.get("draft"):
            continue
        for asset in release.get("assets", []):
            match = ASSET_PATTERN.match(asset.get("name", ""))
            if not match:
                continue
            version = parse_version(match.group(1))
            if version and (best is None or version > best[0]):
                best = (
                    version,
                    match.group(1),
                    asset["browser_download_url"],
                    int(asset.get("size") or 0),
                    release.get("name") or release.get("tag_name") or "",
                )

    if best is None:
        raise RuntimeError("在 GitHub release 中找不到 DD2gether-alpha-x.y.zip")
    return best


def download_file(url: str, destination: Path, expected_size: int):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with http_get(url) as response, destination.open("wb") as file:
        total = expected_size or int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        last_percent = -1
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            file.write(chunk)
            downloaded += len(chunk)
            if total:
                percent = downloaded * 100 // total
                if percent // 10 != last_percent // 10:
                    last_percent = percent
                    print(f"    下載中 {percent:3d}%  ({downloaded / 1e6:.1f} / {total / 1e6:.1f} MB)")
    if expected_size and downloaded != expected_size:
        raise RuntimeError(f"下載大小不符：{downloaded} != {expected_size}")


# =========================
# 安裝
# =========================

def extract_zip(zip_path: Path, extract_dir: Path) -> Path:
    """解壓並回傳包含 DD2gether.exe 的資料夾。"""
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)

    candidates = sorted(extract_dir.rglob("DD2gether.exe"), key=lambda p: len(p.parts))
    if not candidates:
        raise RuntimeError("壓縮檔內找不到 DD2gether.exe")
    return candidates[0].parent


def migrate_user_data(old_dir: Path, new_dir: Path):
    """把舊版的使用者資料（例如 data/coop_config.json）帶到新版，不覆蓋新版已有的檔案。"""
    copied = []
    for rel in USER_DATA_DIRS:
        source = old_dir / rel
        if not source.is_dir():
            continue
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            target = new_dir / path.relative_to(old_dir)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append(str(path.relative_to(old_dir)))
    return copied


def install(new_root: Path, version_str: str, old_launcher_dir) -> Path:
    target = ROOT / f"DD2gether-alpha-{version_str}"

    if old_launcher_dir is not None and target.resolve() == old_launcher_dir.resolve():
        raise RuntimeError(f"目標資料夾與目前安裝相同：{target}")

    if target.exists():
        print(f"    移除先前未完成的安裝：{target.name}")
        shutil.rmtree(target)

    shutil.move(str(new_root), str(target))

    new_exe = target / "DD2gether.exe"
    if not new_exe.is_file():
        raise RuntimeError(f"安裝後找不到：{new_exe}")

    copied = migrate_user_data(old_launcher_dir, target) if old_launcher_dir else []
    if copied:
        print("    已沿用舊版設定：")
        for name in copied:
            print(f"      - {name}")

    return new_exe


# =========================
# 主流程
# =========================

def main(argv):
    check_only = "--check-only" in argv
    local_zip = None
    if "--zip" in argv:
        index = argv.index("--zip")
        if index + 1 >= len(argv):
            print("❌ --zip 需要指定檔案路徑")
            return 1
        local_zip = Path(argv[index + 1])

    lines = read_config_lines()
    config = parse_config(lines)
    repo = config.get("dd2gether_repo") or DEFAULT_REPO

    # ---- 判斷本機安裝狀態 ----
    exe_value = config.get("dd2gether_path")
    launcher_dir = None
    local_version, source = None, None
    old_was_relative = True  # 全新安裝時用相對路徑寫入 config.ini

    if exe_value:
        exe_path = Path(exe_value)
        old_was_relative = not exe_path.is_absolute()
        if old_was_relative:
            exe_path = ROOT / exe_path
        exe_path = exe_path.resolve()
        if exe_path.is_file():
            launcher_dir = exe_path.parent
        else:
            print(f"⚠ 找不到 DD2gether.exe：{exe_path}")

    if launcher_dir is None:
        print("本機尚未安裝 DD2gether，將下載最新版進行全新安裝。")
    else:
        if not is_truthy(config.get("auto_update"), default=True):
            print("ℹ️ config.ini 已關閉自動更新（auto_update=0），略過檢查。")
            return 0
        local_version, source = get_local_version(launcher_dir)
        if local_version:
            print(f"本機版本：{version_to_str(local_version)}  （來源：{source}）")
        else:
            print("本機版本：無法判斷（將視為需要更新）")

    # ---- 取得最新版 ----
    if local_zip:
        remote_str = (ASSET_PATTERN.match(local_zip.name) or VERSION_PATTERN.search(local_zip.name))
        if not remote_str:
            print(f"❌ 無法從檔名判斷版本：{local_zip.name}")
            return 1
        remote_str = remote_str.group(1)
        remote_version = parse_version(remote_str)
        download_url = None
        asset_size = local_zip.stat().st_size
        release_name = f"(本機檔案) {local_zip.name}"
    else:
        print(f"正在查詢 GitHub：{repo} ...")
        try:
            remote_version, remote_str, download_url, asset_size, release_name = find_latest_release(repo)
        except urllib.error.URLError as error:
            print(f"⚠ 無法連線到 GitHub：{error.reason}")
            return 1
        except Exception as error:  # noqa: BLE001
            print(f"⚠ 查詢最新版本失敗：{error}")
            return 1

    print(f"最新版本：{remote_str}  （{release_name}）")

    if local_version and remote_version <= local_version:
        print("✅ DD2gether 已是最新版。")
        return 0

    print()
    print(f"🔔 發現新版 DD2gether：{version_to_str(local_version) if local_version else '?'} → {remote_str}")

    if check_only:
        print("（--check-only：不進行下載）")
        return 0

    # ---- 下載 ----
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if local_zip:
            zip_path = local_zip
        else:
            zip_path = TEMP_DIR / f"DD2gether-alpha-{remote_str}.zip"
            print(f"正在下載 {asset_size / 1e6:.1f} MB ...")
            download_file(download_url, zip_path, asset_size)

        # ---- 解壓 / 安裝 ----
        print("正在解壓縮 ...")
        new_root = extract_zip(zip_path, TEMP_DIR / "extract")

        print("正在安裝 ...")
        new_exe = install(new_root, remote_str, launcher_dir)

        new_value = write_config_path(lines, new_exe, old_was_relative)
        print()
        if launcher_dir is None:
            print("✅ DD2gether 已安裝完成")
            print(f"    路徑：{new_value}")
            print(f"    設定檔：{CONFIG_FILE}")
        else:
            print("✅ DD2gether 已更新完成")
            print(f"    新版路徑：{new_value}")
            print(f"    舊版保留於：{launcher_dir.name}（確認新版正常後可自行刪除）")
        return 0

    except urllib.error.URLError as error:
        print(f"⚠ 下載失敗：{error.reason}")
        return 1
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        print(f"⚠ 更新失敗：{error}")
        return 1
    finally:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError) as error:
        print(f"❌ {error}")
        sys.exit(1)
