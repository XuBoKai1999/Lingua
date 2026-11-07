from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from lingua import storage


COURSE = {
    "name": "English - 測試教材",
    "language": "English",
    "region": None,
    "goal": "能完成旅行時的基本交流。",
    "default_level": "A2",
    "requirements": "以實際溝通為主。",
}


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_template_stage_selection_and_source_unchanged(tmp_path):
    before = _sha256(storage.UNITS_TEMPLATE)
    course_dir = storage.create_course(COURSE, template_stages=(0, 1), library_root=tmp_path)
    course, units = storage.load_course(course_dir)

    assert course == COURSE
    assert len(units["units"]) == 44
    assert units["units"][0]["id"] == "U001"
    assert units["units"][-1]["id"] == "U044"
    assert _sha256(storage.UNITS_TEMPLATE) == before


def test_all_stages_reopen_edit_and_level_inheritance(tmp_path):
    course_dir = storage.create_course(COURSE, template_stages=range(4), library_root=tmp_path)
    course, units = storage.load_course(course_dir)
    assert len(units["units"]) == 128
    assert storage.effective_level(course, units["units"][0]) == "A2"

    changed = deepcopy(units)
    changed["units"][0]["description"] = "已修改的能力目標"
    changed["units"][0]["level"] = "B1"
    storage.save_units(course_dir, changed)
    reopened_course, reopened_units = storage.load_course(course_dir)

    assert reopened_units["units"][0]["description"] == "已修改的能力目標"
    assert reopened_units["units"][1:] == units["units"][1:]
    assert storage.effective_level(reopened_course, reopened_units["units"][0]) == "B1"


def test_blank_course_collision_and_path_traversal(tmp_path):
    course_dir = storage.create_course(COURSE, library_root=tmp_path)
    assert storage.load_course(course_dir)[1] == {"units": []}
    with pytest.raises(FileExistsError):
        storage.create_course(COURSE, library_root=tmp_path)
    with pytest.raises(ValueError, match="路徑"):
        storage.create_course({**COURSE, "name": "../escape"}, library_root=tmp_path)


@pytest.mark.parametrize(
    "data, message",
    [
        ({**COURSE, "goal": "  "}, "goal"),
        ({**COURSE, "extra": "x"}, "不支援欄位"),
        ({"units": [{"id": "U001"}]}, "缺少欄位"),
        (
            {"units": [
                {"id": "U001", "stage": -1, "context": "a", "scenario": "b", "description": "c", "level": None, "requirements": ""},
            ]},
            "stage",
        ),
    ],
)
def test_validation_rejects_invalid_contracts(data, message):
    with pytest.raises(ValueError, match=message):
        (storage.validate_units if "units" in data else storage.validate_course)(data)


def test_duplicate_ids_and_invalid_import_leave_original_unchanged(tmp_path):
    course_dir = storage.create_course(COURSE, template_stages=(0,), library_root=tmp_path)
    original = (course_dir / "units.json").read_bytes()
    unit = storage.load_course(course_dir)[1]["units"][0]
    duplicate = json.dumps({"units": [unit, unit]}, ensure_ascii=False)

    with pytest.raises(ValueError, match="重複"):
        storage.import_units(course_dir, duplicate)
    with pytest.raises(ValueError, match="有效 JSON"):
        storage.import_units(course_dir, "{not json")
    assert (course_dir / "units.json").read_bytes() == original


def test_valid_import_unicode_and_next_id(tmp_path):
    course_dir = storage.create_course(COURSE, library_root=tmp_path)
    candidate = {
        "units": [
            {"id": "U009", "stage": None, "context": "咖啡店", "scenario": "點飲料", "description": "能點飲料", "level": None, "requirements": "少糖"},
        ]
    }
    storage.import_units(course_dir, json.dumps(candidate, ensure_ascii=False))
    reopened = storage.load_course(course_dir)[1]
    assert reopened == candidate
    assert "咖啡店" in (course_dir / "units.json").read_text(encoding="utf-8")
    assert storage.next_unit_id(reopened["units"]) == "U010"


def test_planning_prompt_extracts_only_text_fence_and_expands_placeholders():
    prompt = storage.build_planning_prompt(COURSE, {"units": []}, extra_requirements="偏重旅行")
    assert prompt.startswith("你是 Lingua 的外語課程設計顧問")
    assert "偏重旅行" in prompt
    assert "English - 測試教材" in prompt
    assert "{{" not in prompt
    assert "# Course → Units" not in prompt
    assert "【供參考的課綱：若沒有則為 null】\nnull" in prompt
