# Codex 開工 Prompt — Lingua GUI MVP（自主完成至可驗收）

以下是給 **Codex 在 `XuBoKai1999/Lingua` repository 工作目錄中執行**的指令。請直接複製下方 Prompt；不要把此 Markdown 的說明文字當成任務輸入。

~~~text
請在目前的 XuBoKai1999/Lingua repository 中，從頭到尾實作可運行、可供我實際給 GUI 意見的第一版桌面 APP。

【工作模式】
- 這是一次「連續自主施工」任務，不是請你只提出計畫。
- 先審查現況與相依規範，再依 steps.md 的 Step 0→7 逐段實作、測試、修正、繼續到完整 GUI MVP。
- 不要每個 phase 結束就停下來向我請示；我會離開電腦。遇到一般可逆的設計細節，依 arch.md 和如無必要勿增實體原則做最小合理決定。
- 確有重大不明確或無法安全繼續的阻礙時，記錄原因；先把其他能完成的事項做完，再在結尾清楚報告。不可假裝完成。
- 不需要預估完成時間。完成後給我可執行指令、測試結果、commit 與 PR。

【先讀，再開發】
1. 本 repo：
   - arch.md（本次 GUI MVP 的架構契約）
   - steps.md（完整、可驗收施工步驟；請一口氣完成）
   - decisions/003_教材與Units_JSON初版設計決議.md
   - decisions/004_落地生根v0.2與對話式教材構想.md
   - templates/course.template.json
   - templates/units.template.json
   - templates/units/落地生根.json
   - templates/units/落地生根.md
   - prompts/course_to_units.md
2. 參考 repository（唯讀，沒有權限或無法存取時明確註記，勿阻擋主線）：
   - XuBoKai1999/Ultimate_English_Learner：src/gui.py、src/views/new_article.py。了解首頁導航、Prompt 編輯／複製／貼回工作流。
   - XuBoKai1999/calibration：src/calibration/ui/main_window.py、src/calibration/ui/case_editor.py、src/calibration/app.py。觀察 PySide6 layout、QScrollArea、QSettings 與縮放方式。
3. 不要照搬兩個專案的整套程式；Lingua 是新 APP，資料結構與用途不同。

【明確的設計限制】
- 使用 Python 3.11+、PySide6，Windows desktop 為主要使用環境。
- 一定要有真正可啟動的 Home、創建教材、教材瀏覽、課程編輯、Unit 瀏覽／編輯，以及可展示的學習對話示意。
- 直接讀取現存 P1／P2 JSON 範例與「落地生根」v0.2 課綱，絕不可為了 GUI 方便而改寫已核准的 128 Units 或歷史決議。
- 創建落地生根教材時預設階段 0、1，共 44 Units；可選擇其他階段。另一選項為空白教材。
- course.json 六欄；units.json 每個 Unit 七欄：沿用 arch.md，禁止新增無需求的 metadata／另一套 schema。
- Unit 層級程度可覆蓋 course.default_level；若兩者皆空，不得擅自當成 A1。
- GUI 編輯、JSON 驗證、保存／重開、未存檔提醒、錯誤提示、匯入確認等都是真功能，不得只有外觀。
- P2 Prompt 預覽／複製與 GPT 回傳 units.json 匯入需要可用：從已存在 prompts/course_to_units.md 讀取並完整填入變數。
- P3/P4 的真 AI、TTS、麥克風、口說辨識、考試評分等 **不要實作**。可提供清楚標示的短對話「示意」介面，但不可讓不可用按鈕看起來可以正常操作。
- PySide6 一律採 QLayout/QSplitter/QScrollArea 的自適應版型；不要固定座標、硬塞固定寬高，避免改視窗大小或 DPI 後跑版；提供並保存字體縮放。
- 本地 library/ 的使用者教材必須 gitignore；不要把個人教材或測試生成檔 push 上去。
- **如無必要，勿增實體**：盡量合併合理職責；拒絕額外抽象層、通用框架、過度模組化、資料庫、Web 前端或雲端服務。

【安全施工與版控】
- 先 git status、確認 main 最新內容與乾淨狀態；不可覆蓋任何未提交的使用者修改。
- 從 main 建立 feature/gui-foundation（若已有同名分支，採不破壞既有工作的安全方案）；全部程式碼變更在此 feature branch 完成。
- 可連續多個邏輯 commit 並 push；完成後建立 PR 到 main 供我回來檢查。
- 不要自動 merge，不要 force push，不要重設或重寫 main。
- 若沒有 GitHub PR 操作權限，推上 feature branch 並提供比較／分支連結；不要因 PR 建立失敗而放棄完成程式。
- 若本地環境無法開視窗，使用 QT_QPA_PLATFORM=offscreen 做 GUI smoke tests；不要聲稱已親眼檢查真實 Windows 顯示效果。

【驗收】
- Windows 安裝與啟動：README 有準確的 PowerShell 指令（例如 python -m pip install -e ".[test]"、python run.py）。
- 從 Home 建一個 English 落地生根教材，預設選 0+1 → 44 Units；選 0–3 → 128 Units。可在左側樹狀瀏覽到 U037 的旅行社交。
- 修改 Course 與 Unit，存檔、關閉、重開仍存在；原始 template 檔不變。
- 能建立空白教材、匯入有效 units.json；遇到不合法 JSON、ID 重複或取消操作不可損壞原資料。
- 可複製完整替換過 placeholder 的 P2 討論 Prompt。
- 對話展示區清楚、有意義，但沒有假裝成功的 TTS/GPT。
- 縮放與縮小視窗時不重疊，長表單可捲動；測試以 pytest + Qt offscreen、storage 單元測試與基本導航測試為主。
- 更新 steps.md 勾選真正完成的步驟，README 說明現狀與已知限制；自我 review 並修正明顯問題。
- 最終交代 repo/branch/commit/PR、實際完成畫面、測試命令與結果、仍需我人工檢查的 GUI 細節。不要把未測試說成測試通過。

請立即按照 arch.md 與 steps.md 開始實作；不中途停在一份計畫或只做第一階段。持續到 GUI MVP 能啟動、可驗收，或所有可安全完成的工作均已完成為止。
~~~

## 此 Prompt 的作用

- 用於啟動 **Codex 實作 GUI MVP**，不是產生另一份架構建議。
- `arch.md` 定義功能與資料邊界；`steps.md` 定義施工與驗收；本檔為自主工作指令。
- 指令要求使用 feature branch 與 PR，使一口氣施工留下明確的人工審查點。
- 可用結果的最低標準是「能啟動並實際操作教材與 Units 的 GUI」，不是僅有首頁草圖。
