# Lingua

Lingua 是以 Python 與 PySide6 製作的本機桌面教材編輯器。現在的 GUI MVP 可建立、瀏覽與編輯 P1 `course.json` 和 P2 `units.json`，並提供外部 ChatGPT 課綱討論 Prompt；不需要 API 金鑰或網路服務。

## Windows 安裝與啟動

需求：Python 3.11 或更新版本。

在 repository 根目錄開啟 PowerShell：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python run.py
```

請先確認第一行顯示 Python 3.11 或更新版本。使用者教材會存入 repository 內已忽略的 `library/`，不會被 Git 追蹤。

## 現有功能

- 首頁可進入既有教材或建立新教材。
- 建立表單直接對應 `course.json` 六欄；可建立空白教材，或複製「落地生根」所選 Stage。預設 Stage 0+1 共 44 Units，Stage 0–3 共 128 Units。
- 教材工作區以 Stage → Context → Scenario 瀏覽課綱；可編輯 Course 與單一 Unit，新增、確認刪除及上下移動 Unit。
- Unit 個別 `level` 會覆蓋教材的 `default_level`；兩者都空白時顯示「未指定」。
- 儲存前驗證固定六／七欄資料契約、型別與唯一 ID；JSON 以 UTF-8 原子寫入。錯誤匯入或寫入失敗不會破壞原檔。
- 離開或切換 Unit 前會處理未儲存變更；Unit 編輯可還原。
- P2 規劃視窗從 `prompts/course_to_units.md` 的 `text` fence 組裝完整 Prompt，可複製到外部 ChatGPT；回傳的 `units.json` 必須先驗證、顯示數量並確認，才會取代目前課綱。
- 「學習介面示意」提供短對話、詞彙與未來 GPT 區域的版面預覽；示意資料不會寫入教材。
- `Ctrl++`、`Ctrl+-`、`Ctrl+0`（以及 Ctrl+滑鼠滾輪）調整 80–200% 字體，並以 `QSettings` 保存縮放與視窗幾何。

## 尚未提供

本 MVP 沒有 P3 詞彙生成、P4 教材生成、LLM API、真正的 GPT 對話、TTS、播放、錄音、口說辨識、評分、資料庫或雲端同步。示意頁沒有假裝可用的音訊或 AI 控制項。

P2 匯入是經確認後取代整份 `units.json`，不是自動合併。刪除 Unit 也會在確認後立即儲存；目前沒有版本歷史或復原已確認刪除的功能。

## 測試

```powershell
python -m pytest -q
python -m compileall -q src run.py
```

目前自動測試涵蓋 Stage 數量、六／七欄驗證、Unicode、資料夾碰撞與路徑保護、空白與範本教材、儲存／重開、原子寫入失敗、Unit 編輯／排序、未存檔取消、Prompt 展開、匯入確認、縮放，以及 900×600／200% 的 Qt offscreen 版面 smoke test。

本次驗收環境為 Windows、Python 3.14.6、PySide6 6.11.2，Qt 使用 offscreen 平台。實際螢幕上的繁體中文字型、Windows 顯示縮放與不同 DPI 的視覺觀感仍需人工啟動 `python run.py` 檢查。
