from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unicodedata
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_ROOT = REPO_ROOT / "library"
UNITS_TEMPLATE = REPO_ROOT / "templates" / "units" / "落地生根.json"
PLANNING_PROMPT = REPO_ROOT / "prompts" / "course_to_units.md"

COURSE_FIELDS = (
    "name", "language", "region", "goal", "default_level", "requirements",
)
UNIT_FIELDS = (
    "id", "stage", "context", "scenario", "description", "level", "requirements",
)


def _check_fields(value: dict[str, Any], expected: tuple[str, ...], label: str) -> None:
    missing = [field for field in expected if field not in value]
    extra = [field for field in value if field not in expected]
    if missing or extra:
        details = []
        if missing:
            details.append(f"缺少欄位：{', '.join(missing)}")
        if extra:
            details.append(f"不支援欄位：{', '.join(extra)}")
        raise ValueError(f"{label} 欄位不正確（{'；'.join(details)}）")


def _require_text(value: Any, field: str, *, allow_blank: bool = False) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field} 必須是文字")
    if not allow_blank and not value.strip():
        raise ValueError(f"{field} 不可空白")


def _optional_text(value: Any, field: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field} 必須是文字或 null")


def validate_course(course: Any) -> None:
    if not isinstance(course, dict):
        raise ValueError("course.json 最外層必須是物件")
    _check_fields(course, COURSE_FIELDS, "course.json")
    for field in ("name", "language", "goal"):
        _require_text(course[field], field)
    _optional_text(course["region"], "region")
    _optional_text(course["default_level"], "default_level")
    _require_text(course["requirements"], "requirements", allow_blank=True)


def validate_unit(unit: Any, *, label: str = "Unit") -> None:
    if not isinstance(unit, dict):
        raise ValueError(f"{label} 必須是物件")
    _check_fields(unit, UNIT_FIELDS, label)
    for field in ("id", "context", "scenario", "description"):
        _require_text(unit[field], f"{label}.{field}")
    stage = unit["stage"]
    if stage is not None and (type(stage) is not int or stage < 0):
        raise ValueError(f"{label}.stage 必須是非負整數或 null")
    _optional_text(unit["level"], f"{label}.level")
    _require_text(unit["requirements"], f"{label}.requirements", allow_blank=True)


def validate_units(data: Any) -> None:
    if not isinstance(data, dict) or set(data) != {"units"}:
        raise ValueError("units.json 最外層只能包含 units 陣列")
    units = data["units"]
    if not isinstance(units, list):
        raise ValueError("units 必須是陣列")
    seen: set[str] = set()
    for index, unit in enumerate(units, start=1):
        validate_unit(unit, label=f"Unit #{index}")
        if unit["id"] in seen:
            raise ValueError(f"Unit ID 重複：{unit['id']}")
        seen.add(unit["id"])


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} 不是有效 JSON：第 {error.lineno} 行，第 {error.colno} 欄") from error


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def parse_units_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"不是有效 JSON：第 {error.lineno} 行，第 {error.colno} 欄") from error
    validate_units(data)
    return data


def load_template_units(stages: Iterable[int]) -> dict[str, Any]:
    selected = set(stages)
    if not selected:
        raise ValueError("套用落地生根時至少要選擇一個階段")
    if any(type(stage) is not int or stage < 0 for stage in selected):
        raise ValueError("階段必須是非負整數")
    data = _read_json(UNITS_TEMPLATE, "落地生根課綱")
    validate_units(data)
    available = {unit["stage"] for unit in data["units"]}
    unknown = selected - available
    if unknown:
        raise ValueError(f"落地生根沒有階段：{', '.join(map(str, sorted(unknown)))}")
    return {"units": [deepcopy(unit) for unit in data["units"] if unit["stage"] in selected]}


def template_stage_counts() -> dict[int, int]:
    data = _read_json(UNITS_TEMPLATE, "落地生根課綱")
    validate_units(data)
    counts: dict[int, int] = {}
    for unit in data["units"]:
        stage = unit["stage"]
        if stage is not None:
            counts[stage] = counts.get(stage, 0) + 1
    return counts


def _safe_folder_name(name: str) -> str:
    clean = unicodedata.normalize("NFKC", name).strip()
    if "/" in clean or "\\" in clean or clean in {".", ".."}:
        raise ValueError("教材名稱不可包含路徑或路徑分隔符號")
    clean = re.sub(r'[<>:"|?*\x00-\x1f]', "_", clean).rstrip(". ")
    if not clean:
        raise ValueError("教材名稱無法作為資料夾名稱")
    if clean.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        clean += "_"
    return clean


def create_course(
    course: dict[str, Any], *, template_stages: Iterable[int] | None = None,
    library_root: Path | None = None,
) -> Path:
    validate_course(course)
    units = {"units": []} if template_stages is None else load_template_units(template_stages)
    validate_units(units)
    root = (library_root or DEFAULT_LIBRARY_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / _safe_folder_name(course["name"])
    if target.exists():
        raise FileExistsError(f"教材資料夾已存在：{target.name}")
    temporary = Path(tempfile.mkdtemp(prefix=".creating-", dir=root))
    try:
        _write_json_atomic(temporary / "course.json", deepcopy(course))
        _write_json_atomic(temporary / "units.json", units)
        temporary.rename(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


def list_course_dirs(library_root: Path | None = None) -> list[Path]:
    root = library_root or DEFAULT_LIBRARY_ROOT
    if not root.exists():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.name.casefold(),
    )


def load_course(course_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    course = _read_json(course_dir / "course.json", "course.json")
    units = _read_json(course_dir / "units.json", "units.json")
    validate_course(course)
    validate_units(units)
    return course, units


def save_course(course_dir: Path, course: dict[str, Any]) -> None:
    if not course_dir.is_dir():
        raise FileNotFoundError(f"教材資料夾不存在：{course_dir}")
    validate_course(course)
    _write_json_atomic(course_dir / "course.json", deepcopy(course))


def save_units(course_dir: Path, units: dict[str, Any]) -> None:
    if not course_dir.is_dir():
        raise FileNotFoundError(f"教材資料夾不存在：{course_dir}")
    validate_units(units)
    # Retire changed/removed identities before committing the new curriculum.
    # Keep files recoverable; a failed save restores their original names.
    from lingua.materials import material_path
    previous = _read_json(course_dir / "units.json", "units.json")
    validate_units(previous)
    current = {unit["id"]: unit for unit in units["units"]}
    retired = []
    try:
        for unit in previous["units"]:
            path = material_path(course_dir, unit["id"])
            if current.get(unit["id"]) != unit and path.exists():
                archive = path.with_suffix(f".retired-{uuid.uuid4().hex}.json")
                path.rename(archive)
                retired.append((path, archive))
        _write_json_atomic(course_dir / "units.json", deepcopy(units))
    except Exception:
        for path, archive in reversed(retired):
            archive.rename(path)
        raise


def import_units(course_dir: Path, text: str) -> dict[str, Any]:
    units = parse_units_json(text)
    save_units(course_dir, units)
    return units


def next_unit_id(units: Iterable[dict[str, Any]]) -> str:
    used = {unit["id"] for unit in units}
    highest = max(
        (int(match.group(1)) for item in used if (match := re.fullmatch(r"U(\d+)", item))),
        default=0,
    )
    candidate = highest + 1
    while f"U{candidate:03d}" in used:
        candidate += 1
    return f"U{candidate:03d}"


def effective_level(course: dict[str, Any], unit: dict[str, Any]) -> str | None:
    return unit["level"] if unit["level"] is not None else course["default_level"]


def build_planning_prompt(
    course: dict[str, Any], units: dict[str, Any], *,
    reference_units: dict[str, Any] | None = None, extra_requirements: str = "",
) -> str:
    validate_course(course)
    validate_units(units)
    if reference_units is not None:
        validate_units(reference_units)
    markdown = PLANNING_PROMPT.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^```text[ \t]*\n(.*?)^```[ \t]*$", markdown)
    if match is None:
        raise ValueError("找不到 course_to_units.md 的 text Prompt 區塊")
    replacements = {
        "{{course_json}}": json.dumps(course, ensure_ascii=False, indent=2),
        "{{existing_units_json}}": json.dumps(units, ensure_ascii=False, indent=2),
        "{{reference_units_json}}": (
            "null" if reference_units is None else json.dumps(reference_units, ensure_ascii=False, indent=2)
        ),
        "{{extra_requirements}}": extra_requirements.strip() or "無",
    }
    prompt = match.group(1).rstrip()
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    if re.search(r"{{[^{}]+}}", prompt):
        raise ValueError("Prompt 仍有尚未填入的佔位符")
    return prompt
