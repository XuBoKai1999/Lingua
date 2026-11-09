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


def build_unit_prompt(course: dict, unit: dict, kind: str, vocabulary=None, extra="") -> str:
    validate_course(course)
    validate_unit(unit)
    if kind == "vocabulary":
        example = {"unit_id": unit["id"], "cards": [{"text": "word or phrase", "pos": "詞類", "meaning_zh": "繁體中文義", "example": "目標語言例句", "example_zh": "例句中文翻譯"}]}
        task = "為此單元製作足夠完成能力目標的詞彙及片語卡，每張包含詞類、中文義與目標語言／中文例句。"
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
