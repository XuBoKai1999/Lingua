"""Single-unit P3/P4 contracts, prompts and atomic persistence."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from lingua.storage import (
    _check_fields, _require_text, _read_json, _write_json_atomic,
    effective_level, load_course, validate_course, validate_unit,
)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def material_path(course_dir: Path, unit_id: str) -> Path:
    return course_dir / "materials" / (digest(unit_id) + ".json")


def validate_content(data, unit_id: str, kind: str) -> None:
    if kind not in {"vocabulary", "lesson"}:
        raise ValueError("未知製作階段")
    if not isinstance(data, dict):
        raise ValueError("最外層必須是 JSON 物件")
    key = "cards" if kind == "vocabulary" else "lines"
    _check_fields(data, ("unit_id", key), kind)
    if data["unit_id"] != unit_id:
        raise ValueError("Unit ID 與目前選定單元不符")
    items = data[key]
    if not isinstance(items, list) or not items:
        raise ValueError(f"{key} 必須是非空陣列")
    fields = ("text", "pos", "meaning_zh", "example", "example_zh") if kind == "vocabulary" else ("speaker", "text", "translation_zh")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{key} 每項必須是物件")
        _check_fields(item, fields, key)
        for field in fields:
            _require_text(item[field], field)


def current_source(course_dir: Path, unit_id: str) -> dict:
    course, units = load_course(course_dir)
    unit = next((u for u in units["units"] if u["id"] == unit_id), None)
    if unit is None:
        raise ValueError("單元已刪除，請重新開啟課綱")
    return {"course": course, "unit": unit}


def load_material(course_dir: Path, course: dict, unit: dict) -> dict:
    path = material_path(course_dir, unit["id"])
    if not path.exists():
        return {"source": {"course": deepcopy(course), "unit": deepcopy(unit)}, "vocabulary": None, "lesson": None}
    record = _read_json(path, "單元製作資料")
    if not isinstance(record, dict):
        raise ValueError("單元製作資料損壞")
    _check_fields(record, ("source", "vocabulary", "lesson"), "單元製作資料")
    if record["source"] != {"course": course, "unit": unit}:
        raise ValueError("課程或 Unit 規範已改變；舊製作資料仍保留，但不可誤配。請確認後重新製作。")
    for kind in ("vocabulary", "lesson"):
        if record[kind] is not None:
            validate_content(record[kind], unit["id"], kind)
    return record


def save_content(course_dir: Path, course: dict, unit: dict, kind: str, data: dict, *, reset=False) -> dict:
    validate_content(data, unit["id"], kind)
    source = {"course": course, "unit": unit}
    if current_source(course_dir, unit["id"]) != source:
        raise ValueError("課綱已變更，請重新開啟單元後再匯入")
    if reset:
        record = {"source": deepcopy(source), "vocabulary": None, "lesson": None}
    else:
        record = load_material(course_dir, course, unit)
    if kind == "lesson" and record["vocabulary"] is None:
        raise ValueError("請先確認並保存詞彙")
    if kind == "vocabulary" and record["vocabulary"] != data:
        record["lesson"] = None
    record[kind] = deepcopy(data)
    _write_json_atomic(material_path(course_dir, unit["id"]), record)
    return record


def build_unit_prompt(course: dict, unit: dict, kind: str, vocabulary=None, extra="", *, course_dir: Path | None = None) -> str:
    validate_course(course)
    validate_unit(unit)
    if kind == "vocabulary":
        overview = "未提供：未指定課程資料夾，無法確認課綱順序。"
        history = "未提供：無法確認先前單元的有效詞卡，紀錄不完整。"
        if course_dir is not None:
            course, units = load_course(course_dir)
            ordered = units["units"]
            index = next((i for i, item in enumerate(ordered) if item["id"] == unit["id"]), None)
            if index is None:
                raise ValueError("單元已刪除，請重新開啟課綱")
            unit = ordered[index]
            overview = json.dumps([
                {**{field: item[field] for field in ("id", "stage", "context", "scenario", "description")},
                 "current_unit": i == index}
                for i, item in enumerate(ordered)
            ], ensure_ascii=False, indent=2)
            previous, missing = [], []
            for item in ordered[:index]:
                try:
                    confirmed = load_material(course_dir, course, item)["vocabulary"]
                except (OSError, ValueError, UnicodeError):
                    confirmed = None
                if confirmed is None:
                    missing.append(item["id"])
                else:
                    previous.append({"unit_id": item["id"], "cards": [
                        {field: card[field] for field in ("text", "pos", "meaning_zh")}
                        for card in confirmed["cards"]
                    ]})
            if not index:
                history = "未提供：目前單元之前沒有單元。"
            else:
                history = f"已提供 {len(previous)}/{index} 個先前單元的有效詞卡；僅代表已產生內容，不代表已學會，也不保證完整去重。"
                if missing:
                    history += "\n紀錄不完整；未提供有效詞卡的單元：" + "、".join(missing)
                history += "\n" + (json.dumps(previous, ensure_ascii=False, indent=2) if previous else "未提供")
        example = {"unit_id": unit["id"], "cards": [{"text": "目標語言詞彙或片語", "pos": "詞類", "meaning_zh": "繁體中文義", "example": "目標語言例句", "example_zh": "例句繁體中文翻譯"}]}
        current = {"unit": unit, "effective_level": effective_level(course, unit)}
        return ("""你是一位語言教材設計者。請根據下方課程資料，為「目前單元」製作詞彙與片語卡。這份課程會依學習進度逐單元製作；你現在只需處理目前單元，不要一次產生整門課的教材。

【課程背景與銜接】
- 先閱讀課程目標與課綱總覽，理解整門課的用途、目前單元的位置，以及相鄰單元的分工。課綱總覽是規劃背景，不代表所有單元的教材都已產生，也不代表學習者已經學會。
- 如有提供先前單元的有效詞卡，利用它們掌握已產生的內容，避免無意義地重複；但為了完成目前單元的能力目標，必要的基礎用語、複習或同一詞彙在新語境中的用法仍可出現。
- 若沒有提供先前詞卡，或紀錄不完整，不要假裝知道過去教過或學會哪些詞彙，也不要因此捏造課程進度。
- 程度以目前單元的有效程度為準；未指定時不要自行當成 A1。若地區未指定，依課程目標選用適當、自然的表達；若目標涵蓋多個地區，優先選擇普遍可用的表達，必要時在中文義簡短註明差異。

【本次任務】
- 根據目前單元的情境、說明與要求，選出足以支撐其能力目標的常用詞彙及片語。數量依實際需要決定，不為湊數收錄冷僻或無關項目，也不要為了精簡而漏掉完成目標所必需的表達。
- 每張卡提供詞類、繁體中文義、一個自然且符合單元情境的目標語言例句，以及例句的繁體中文翻譯。
- 詞彙、片語及例句應符合有效程度與課程目標；遇到基本情境，也不必因階段編號較早就自動降低至初學者程度。
- text 和 example 只寫目標語言內容，不加中文或說明標籤；中文說明放在 meaning_zh 或 example_zh。
- 當次要求只適用本次，不修改長期設定。

【輸出要求】
只輸出一個符合以下結構的完整 JSON，不要 Markdown、前言或額外欄位。每個欄位都是非空字串；cards 是非空陣列。示例僅說明格式，不限制內容或數量。

""" + json.dumps(example, ensure_ascii=False, indent=2)
                + "\n\n【製作依據】\n課程資料：\n" + json.dumps(course, ensure_ascii=False, indent=2)
                + "\n\n課綱總覽（current_unit 為 true 表示目前單元）：\n" + overview
                + "\n\n目前單元完整資料與有效程度：\n" + json.dumps(current, ensure_ascii=False, indent=2)
                + "\n\n先前單元有效詞卡：\n" + history
                + "\n\n當次要求：\n" + (extra.strip() or "無"))
    elif kind == "lesson":
        validate_content(vocabulary, unit["id"], "vocabulary")
        example = {"unit_id": unit["id"], "lines": [{"speaker": "A", "text": "一行目標語言對話", "translation_zh": "繁體中文翻譯"}]}
        task = "使用已確認詞彙，製作完整單元的數段自然短對話，涵蓋能力目標；依朗讀順序逐行輸出，不把說話者或中文翻譯混入 text。"
    else:
        raise ValueError("未知製作階段")
    context = {"course": course, "unit": unit, "effective_level": effective_level(course, unit), "temporary_requirements": extra}
    if kind == "lesson":
        context["confirmed_vocabulary"] = vocabulary
    return (task + "\n只輸出符合下列精簡格式的完整 JSON，不要 Markdown。示例不是內容或數量限制。"
            "\n程度 null 表示未指定，不得擅自當成 A1。中文一律繁體；text/example 使用課程目標語言。"
            "\n當次要求不修改長期設定。\n輸出格式：\n" + json.dumps(example, ensure_ascii=False, indent=2)
            + "\n製作依據：\n" + json.dumps(context, ensure_ascii=False, indent=2))
