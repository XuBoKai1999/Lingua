# 粗決議 03：教材總規範與 Units JSON 初版設計

> **紀錄日期**：2026-10-27  
> **狀態**：初步採納的資料格式草案；供後續 Lingua 開發與 Prompt 規格討論參考，仍可修改  
> **前序**：[粗決議 01](001_教材架構與生成流程_粗決議.md) · [粗決議 02](002_落地生根模板與Prompt工作流_討論紀錄.md)  
> **本次實際產物**：[course.template.json](../templates/course.template.json) · [units.template.json](../templates/units.template.json)

## 1. 設計原則與本輪共識

Lingua 的教材建立仍分四步：

1. **教材總規範**：使用 GUI／人工或其他外部討論方法建立 `course.json`。
2. **具體 Units**：透過現成課綱、人工編輯，或選擇性以 AI 討論和清洗後建立 `units.json`。
3. **單字表**：以指定 Unit 與相關上層規範組裝 Prompt，交由 AI 生成。
4. **學習材料**：以詞彙表與相關規範組裝 Prompt，交由 AI 生成文字材料；音檔由程式使用 TTS 生成。

第一、二步的**交付物是 JSON，不是 AI 對話或 Prompt**；在設計特殊課綱（例如 TOEIC）時，可另外提供一個 **P2-A 討論 Prompt** 和一個 **P2-B 定稿清洗 Prompt**。是否使用 AI 不應影響 `units.json` 格式。

本輪進一步確定：

- `course.json` 增設獨立的 `goal`，不再將目的只藏於自由文字 `requirements`。
- `template` **不放在最小 `course.json`**：既有課綱模板只是建立教材時的來源，不應成為已建立教材的永久依賴。
- Unit 的 `title`、`topic` **改名並重新定義為 `context`（大情境）及 `scenario`（子情境）**。
- 原有 `description` 保留，主要描述**學完這個 Unit 後能實際做什麼**，而非重複標題。
- **Unit 個別程度優先，教材預設程度作為後備值**；輸出生成 Prompt 時繼承計算，不需要將計算後的程度反寫到每個 Unit。
- 重視最小資料結構；目前不增加獨立的主題表、巢狀情境樹、額外排序欄位或資料庫模型。

## 2. `course.json`：教材總規範

模板檔：`templates/course.template.json`。

| 欄位 | 型別（草案） | 語意 |
| --- | --- | --- |
| `name` | string | GUI 中的教材名稱 |
| `language` | string | 目標語言 |
| `region` | string 或 null | 目標國家／地區，未指定可為 null |
| `goal` | string | **學習目標與這份教材為何存在** |
| `default_level` | string 或 null | 未單獨指定程度的 Units 使用的預設難度 |
| `requirements` | string | 教材的長期規範，例如實戰導向、在地化及不安排文法課 |

**重要界線：**

- `goal` 著重預期能力；`requirements` 著重內容生成時應遵循的規則與偏好。
- `region` 未指定時，不應擅自把單一國家的習慣當作所有地區的標準。
- 程度可依語言或任務指定不同體系；此階段不綁死 CEFR 或固定 enum。
- `requirements` 可保留自然語言，避免為少見用途新增大量僅供 Prompt 閱讀的欄位。
- `template` 的來源追溯如未來有需要再決定，不要求現在保存。

模板內使用「英文／落地生根」作為**可編輯的示範值**；它不是已正式建立的使用者教材。

## 3. `units.json`：大情境下的子情境

模板檔：`templates/units.template.json`。

```json
{
  "units": [
    {
      "id": "U001",
      "stage": 2,
      "context": "看醫生",
      "scenario": "預約門診與掛號",
      "description": "能預約門診、確認時間與地點，並在抵達診所或醫院時完成基本報到。",
      "level": null,
      "requirements": ""
    },
    {
      "id": "U002",
      "stage": 2,
      "context": "看醫生",
      "scenario": "描述症狀與詢問用藥",
      "description": "能向醫護人員描述症狀、持續時間與重要過敏資訊，並確認基本用藥指示。",
      "level": null,
      "requirements": ""
    }
  ]
}
```

**這是示例，不是已確認的落地生根正式兩個 Units 或完整清單。**

| 欄位 | 型別（草案） | 語意 |
| --- | --- | --- |
| `id` | string | 在同一份教材中穩定且唯一的識別碼；不與階段或順序綁定 |
| `stage` | integer 或 null | 有階段的課綱可指定階段，否則 null；與程度不同 |
| `context` | string | **大情境／領域**，例如「看醫生」「搭車」「餐飲」 |
| `scenario` | string | **子情境／本 Unit 的具體任務場景**，例如「門診掛號」 |
| `description` | string | 學完後能完成的具體溝通任務 |
| `level` | string 或 null | Unit 專屬程度，null 時繼承教材預設值 |
| `requirements` | string | 對本 Unit 下游生成適用的長期補充要求 |

### 3.1 為何分成 `context` 與 `scenario`

過去 `title` 與 `topic` 的界線不清楚，可能變成一個簡短標題搭配一串未排序的關鍵字。現在用明確的**大情境 → 子情境**理解：

```text
看醫生（context）
├── 預約門診與掛號（scenario，Unit U001）
└── 描述症狀與詢問用藥（scenario，Unit U002）
```

這是**概念上的分組**。資料仍維持扁平的 `units` 陣列，每個 Unit 都自行寫 `context`；**不增加巢狀 `contexts` JSON 或獨立的 context ID 表**。

GUI 可以將相同 `context` 的 Units 視覺分組，並以 `scenario` 作為 Unit 的簡短顯示文字。是否自動分組、跨 context 排序、重複命名檢查，留待 GUI 階段確認。

### 3.2 `description` 的任務

`description` 應是 AI 選詞與選材的具體指引，例如「能向醫護人員說明症狀持續時間、確認藥物使用方式」。不應僅寫「學習醫療相關單字」。

### 3.3 ID、順序與 stage

- 使用 `U001` 等穩定的 Unit ID，不用 `S0-U01` 綁定所在階段。
- `units` 陣列的順序就是目前的預設順序，暫時不增 `order`。
- `stage` 用於「落地生根」等有階段的課綱；不等於 `level`。非階段式教材可以設為 `null`。
- 同一個 `context` 可以在不同 `stage` 反覆出現，以對應不同深度、不同子情境的練習。

## 4. 程度繼承與 Prompt 裝配

有效難度：

```text
effective_level = unit.level
                  if unit.level is not null
                  else course.default_level
```

- `unit.level = "C1"`、`course.default_level = "B2"` → 用 C1。
- `unit.level = null`、`course.default_level = "B2"` → 用 B2。
- 兩者都是 `null` → 沒有明定程度；下游不得聲稱原規範已指定某個級別，可依情境或另行補充需求。

P3（單字表）至少可讀取：教材 `language/region/goal/requirements`、有效程度、指定 Unit 的 `context/scenario/description/requirements`。P4（學習材料）還要取得該 Unit 的已確認單字表。

無需每次把整份 `units.json` 無條件加入 Prompt。可依需求選擇性傳入相關 Unit 摘要、其他已學詞彙等。

使用者可在各次生成加入**臨時額外需求**；與存在 `course.json`／`units.json` 的持久需求分開，不應因某次 Prompt 修改而悄悄覆寫持久設定。

## 5. 模板與教材實例的邊界

此時 repository 新增的：

```text
templates/
├── course.template.json
└── units.template.json
```

是**通用的 P1/P2 欄位結構範例（valid JSON）**，不是已完成的「落地生根」128 Units 課綱，也不是正式 JSON Schema 驗證定義。日後要建立新教材時，可複製再修改。

「落地生根」是另外一種**已規劃內容的課綱模板**，理想上可直接選取階段 0～3 的 Units，不強迫 AI 重排；但完整條目尚待確認並落成資料。

教材支持**持續／局部生成**：可先有 course 和部分 Units 的規劃，再逐 Unit 生成詞彙與材料；新增 Units 不應強制重做既有教材。

P1/P2 不存放單字表、文章、TTS 音檔、學習進度或生成狀態，避免規範資料與運作狀態混雜。

## 6. 暫未決定的事項

1. 真正的 JSON Schema、必填值驗證、語言代碼、程度標準及版本遷移策略。
2. `context` 未來是否有必要獨立為某種 group 實體；**目前不增加**。
3. 對「非落地生根」教材，是否需要比 `stage` 更通用的群組欄位；**目前不增加**。
4. P2-A／P2-B 的正式 Prompt 文字，以及課綱編輯 GUI。
5. P3 單字表及 P4 材料的資料格式、評估與品質控制。
6. 落地生根各階段的**正式逐筆 Unit 清單**。
7. 從既有模板增補 Units 時的 ID 合併／衝突處理機制。
8. TTS、逐句同步、口說、閱讀及寫作功能的具體實作範圍。

本次先只落地**設計紀錄與兩份 JSON 範例**，不增其他程式、模型、測試或模板。遵循「如無必要，勿增實體」。
