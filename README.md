# Lingua

Lingua 是以 Python 與 PySide6 製作的本機桌面教材編輯器。可建立、瀏覽與編輯 P1 `course.json` 和 P2 `units.json`，並逐一製作單元詞彙、教材與收聽。AI 內容沿用外部 ChatGPT Prompt／JSON 匯入，不需內建 API 金鑰；Edge TTS 語音生成需要網路。

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

沒有內建 LLM API、批量生成、真正的 GPT 對話、錄音、口說辨識、評分、資料庫或雲端同步。原「學習介面示意」仍是示意；實際學習請使用「製作／學習目前 Unit」。

## 學到哪裡，製作哪個單元

1. 開啟／建立落地生根教材，在課綱選 U037（或任一單元），按「製作／學習目前 Unit」。
2. 製作頁選 `vocabulary`，填本次要求後複製 Prompt 到外部 AI。貼回／載入 UTF-8 JSON，按「驗證並預覽」，閱讀後「確認保存」。
3. 選 `lesson`；Prompt 會帶入已保存詞彙。再次貼回完整 JSON、驗證預覽並確認。兩個 Prompt 均包含課程、Unit 與有效程度；本次要求不改長期設定。
4. 詞彙頁左選詞／片語，右看詞類、中文義及目標語言／中文例句；詞與例句可分別播放。教材頁顯示逐行雙語對話，按「產生／播放本單元教材」。
5. 確認 Edge 語音與目標語言相符（預設 `en-US-AriaNeural`，英國英語可用 `en-GB-SoniaNeural`，其他語言需換相應 Edge voice）；語速格式 `+0%`、`-20%`。首次生成會傳送朗讀文字到 Microsoft，失敗保留文字可重試。已產生的相符音檔可離線播放。
6. 播放／繼續、暫停、停止、重播及進度條控制目前音檔。教材逐行播放，進度顯示目前第幾行音檔與秒數；換行可能有短暫間隔。目前行依真實 WordBoundary 與播放器位置標示並捲動；缺少時間戳時明確停用同步，不估算。
7. 關閉後重開同一教材與 Unit，詞彙、教材和音檔仍在。更新詞彙會使舊教材失效；更改文字或語音設定不會播放舊的不匹配音檔。

詞彙 JSON：`{"unit_id":"U037","cards":[{"text":"seat taken","pos":"phrase","meaning_zh":"座位有人坐","example":"Is this seat taken?","example_zh":"這個座位有人坐嗎？"}]}`。

教材 JSON：`{"unit_id":"U037","lines":[{"speaker":"A","text":"Is this seat taken?","translation_zh":"這個座位有人坐嗎？"}]}`。示例不是數量限制，實際 Prompt 要求足夠詞彙與涵蓋能力目標的完整對話。

P1/P2 舊檔相容。新資料僅存 `library/<教材>/materials/<雜湊ID>.json` 與 `audio/`；Unit ID 不直接當路徑。課綱刪除／變更單元會把已製作資料保留為 `.retired-*.json`，不誤配給重用 ID；其他單元不變。課程規範改變時舊製作資料停用，確認取代前仍保留。備份教材請複製整個教材資料夾。

2026-11-09 後續修正：最低版本提升至 edge-tts 7.3.1，既有環境請重跑安裝指令。7.2.8 的測試曾回傳 HTTP 403；升級實際執行環境至 7.3.1 後，以全新暫存目錄、固定文字 `Hello! Is this seat taken?`、`en-US-AriaNeural`、`+0%` 成功取得 21,456 bytes MP3 與 5 筆有效 WordBoundary，Qt 解碼及播放／暫停／跳轉／繼續／停止通過（約 3.58 秒，靜音測試）。人工聽辨音質及畫面與語音的主觀同步仍待驗收；不能把所有 HTTP 403 都歸因於版本。

P2 匯入是經確認後取代整份 `units.json`，不是自動合併。刪除 Unit 也會在確認後立即儲存；目前沒有版本歷史或復原已確認刪除的功能。

## 測試

```powershell
python -m pytest -q
python -m compileall -q src run.py
```

目前自動測試涵蓋 Stage 數量、六／七欄驗證、Unicode、資料夾碰撞與路徑保護、空白與範本教材、儲存／重開、原子寫入失敗、Unit 編輯／排序、未存檔取消、Prompt 展開、匯入確認、縮放，以及 900×600／200% 的 Qt offscreen 版面 smoke test。

2026-11-09：共 44 項測試通過，另涵蓋單元 P3/P4 保存與重開、ID／規範失配、課綱變更與失敗回復、語音快取失配、時間戳及無時間戳分支、QProcess 交接與實際 Qt 合成 WAV 解碼／播放控制。合成 WAV 與 mock 不代表線上 TTS 已驗收。

本次驗收環境為 Windows、Python 3.14.6、PySide6 6.11.2，Qt 使用 offscreen 平台。實際螢幕上的繁體中文字型、Windows 顯示縮放與不同 DPI 的視覺觀感仍需人工啟動 `python run.py` 檢查。
