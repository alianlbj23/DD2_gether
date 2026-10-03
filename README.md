# Dragon's Dogma 2 - DD2gether 自動備份啟動器

一鍵啟動 [DD2gether](https://github.com/But-Frog/dd2-together-release)（龍族教義 2 連線合作 Mod），
並在遊戲前後自動備份存檔，同時在啟動前自動檢查並更新 DD2gether 到最新版。

## 功能

- **啟動前自動更新 DD2gether**：查詢 GitHub release，發現新版就自動下載、解壓並切換路徑，舊版會保留以便回退。
- **遊戲前備份**：啟動 DD2gether 前先備份一次存檔。
- **遊戲後備份**：偵測到 `DD2.exe` 關閉後再備份一次。
- **最終檢查**：DD2gether 啟動器關閉後再比對一次，有變化才會新增備份。
- 備份內容相同時不會重複建立，最多保留 20 份，超過自動刪除最舊的。

## 需求

- Windows 10 / 11
- [Python 3](https://www.python.org/downloads/)（安裝時勾選 `py launcher`，腳本透過 `py` 指令執行）
- Steam 版 Dragon's Dogma 2
- 可連線 GitHub（首次執行會自動下載 DD2gether，之後自動更新）

## 安裝

1. 下載或 `git clone` 本專案到任意資料夾。
2. 執行 `Play_DD2_With_Backup.bat`。第一次執行會：
   - 找不到 DD2gether 時，自動從 GitHub 下載最新版並解壓到 `DD2gether-alpha-<版本>` 資料夾
   - 自動建立 `config.ini`
   - 自動從 Steam 找出你的 DD2 存檔資料夾（不需要手動填 Steam ID）

   不需要修改任何程式碼。

   若你已經有手動下載好的 DD2gether，直接解壓到本專案資料夾底下的任何子資料夾即可，
   腳本會自動找到 `DD2gether.exe` 並沿用，不會重複下載。

## 使用方式

每次要玩就執行 `Play_DD2_With_Backup.bat`，流程如下：

1. 檢查 DD2gether 是否有新版 → 有就自動更新
2. 遊戲前備份
3. 啟動 DD2gether，在它的視窗按「Launch Dragon's Dogma 2」
4. 等待遊戲關閉 → 遊戲後備份
5. 等待 DD2gether 啟動器關閉 → 最終備份檢查
6. 顯示結果，按 Enter 或 Q 關閉

## config.ini

第一次執行會自動產生，內容如下：

```ini
# DD2gether 執行檔路徑（可用相對路徑）
dd2gether_path=DD2gether-alpha-0.32.1\DD2gether.exe

# 存檔備份的輸出資料夾
backup_output_path=Backups

# 存檔資料夾。留空時自動從 Steam userdata 偵測
# 範例：C:\Program Files (x86)\Steam\userdata\<帳號ID>\2054970\remote\win64_save
save_path=

# 啟動前自動從 GitHub 檢查並更新 DD2gether（1=開啟，0=關閉）
auto_update=1

# 發佈 DD2gether 的 GitHub 倉庫
dd2gether_repo=But-Frog/dd2-together-release
```

| 鍵 | 說明 |
| --- | --- |
| `dd2gether_path` | `DD2gether.exe` 的路徑，自動更新後會由腳本改寫成新版路徑 |
| `backup_output_path` | 存檔備份的輸出資料夾，相對路徑以本專案資料夾為基準 |
| `save_path` | 存檔資料夾。留空自動偵測；偵測不到或想指定別的帳號時才需要填 |
| `auto_update` | `1` 開啟自動更新，`0` 關閉 |
| `dd2gether_repo` | GitHub 倉庫，一般不需要改 |

## 自動更新細節

- 本機版本從 `payload/payload_manifest.json` 讀取；GitHub 端從 release 的 `DD2gether-alpha-x.y.zip` 檔名判斷版本。
- 新版會解壓到 `DD2gether-alpha-<版本>` 資料夾，舊版資料夾保留，確認新版正常後可自行刪除。
- 更新時會把舊版 `data/` 內的設定（例如 `coop_config.json`，記錄遊戲安裝路徑）複製到新版。
- 若無法連線 GitHub 或下載失敗，會顯示警告並沿用目前版本繼續啟動，不會中斷流程（全新安裝時沒有可沿用的版本，會停止並顯示錯誤）。
- DD2gether 已在執行時會略過更新檢查。

也可以手動執行：

```
py -X utf8 DD2gether_Update.py --check-only   # 只比對版本
py -X utf8 DD2gether_Update.py                # 檢查並更新
```

## 存檔資料夾自動偵測

`DD2_Backup.py` 會依序：

1. 若 `config.ini` 有填 `save_path`，直接使用。
2. 從登錄檔（`HKCU\Software\Valve\Steam\SteamPath`、`HKLM\...\Valve\Steam\InstallPath`）
   與常見路徑找出 Steam 安裝位置。
3. 掃描 `Steam\userdata\<帳號ID>\2054970\remote\win64_save`。
   - 只有一個帳號：直接使用。
   - 多個帳號：優先用 `config\loginusers.vdf` 中最近登入的帳號，其次用最近修改的。
4. 都找不到時會列出搜尋過的位置，並提示在 `config.ini` 填 `save_path`。

Python 方面，bat 會自動尋找 `py` 啟動器或 PATH 上的 `python`，兩者皆可。

## 檔案說明

| 檔案 | 說明 |
| --- | --- |
| `Play_DD2_With_Backup.bat` | 主程式，串起更新、備份、啟動與等待流程 |
| `DD2gether_Update.py` | DD2gether 自動更新腳本 |
| `DD2_Backup.py` | 存檔備份腳本（自動偵測存檔位置、比對內容、保留最多 20 份） |
| `config.ini` | 本機設定，自動產生，不納入版控 |

## 注意事項

- DD2gether 的授權禁止再散佈，本專案不包含 DD2gether 本體，`.gitignore` 已排除其資料夾。
- 存檔備份資料夾 `DD2_Save_*` 也不納入版控。
- DD2gether 目前仍是 Alpha，更新後若遇到問題，可將 `config.ini` 的 `dd2gether_path` 改回舊版資料夾並暫時設定 `auto_update=0`。
