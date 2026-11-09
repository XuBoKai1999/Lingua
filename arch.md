# Lingua — GUI MVP Architecture

> Status: **GUI MVP plus single-unit production/learning**, 2026-11-09. The current extension below supersedes the original MVP exclusions of P3/P4/TTS. The remaining sections describe the initial GUI milestone.
>
> Historical design: [decisions/001–004](decisions/) (especially [003](decisions/003_教材與Units_JSON初版設計決議.md), [004](decisions/004_落地生根v0.2與對話式教材構想.md)).
>
> Source data: [course.template.json](templates/course.template.json), [units.template.json](templates/units.template.json), [落地生根.json](templates/units/落地生根.json), [course_to_units.md](prompts/course_to_units.md).
>
> Principle: **如無必要，勿增實體**. Prefer the smallest real working vertical slice over frameworks, premature APIs or inactive buttons.

## Current extension — make only the Unit being studied

Select one existing Unit and open `製作／學習目前 Unit`. P3 vocabulary and P4 lesson creation use expanded Prompt copy → external AI → paste/load JSON → validate/read preview → explicit save confirmation. No embedded LLM API or whole-course generation. Both Prompts include all course/Unit specifications and effective level; P4 requires confirmed vocabulary. Temporary requirements only appear in the Prompt.

`materials.py` defines two compact JSON exchanges: vocabulary `{unit_id, cards: [{text, pos, meaning_zh, example, example_zh}]}` and lesson `{unit_id, lines: [{speaker, text, translation_zh}]}`. `text`/`example` use the course target language, Chinese fields use Traditional Chinese. Arrays must be nonempty and every field is validated. Multiple conversations are represented by ordered speaker lines, without a separate dialogue model.

The original six/seven-field `course.json`/`units.json` are unchanged. A course acquires `materials/<sha256(Unit ID)>.json` only when that Unit is produced. This atomic record contains the source course and Unit snapshots, vocabulary and lesson. Changed vocabulary clears the lesson on confirmed save. Source mismatches disable old material until explicit replacement; no data is silently attributed to another Unit. When saving a curriculum, records for removed/changed Units are renamed to recoverable `.retired-<uuid>.json` files before updating `units.json`; failed writes restore the original names. Reordering and unrelated Units leave records untouched. A crash during that sequence may leave a recoverable retired record, never misattach it to a reused ID. No automatic archive restoration or deletion is provided.

`learning.py` uses a single PySide6 dialog with external-AI exchange, left-list/right-card vocabulary, and bilingual lesson lines. `speech.py` runs edge-tts in a cancellable QProcess; only requested word/example/selected-Unit lesson lines are synthesized. Generation sends target-language text to Microsoft's online Edge TTS service. Generated audio works offline. Voice name/rate are editable and kept in QSettings; choose a voice matching the target language (initial default is English). No second GUI or playback dependency is introduced; QMediaPlayer/QAudioOutput supply play, pause, stop, replay, seek and current-clip progress.

Audio is content-addressed by text, voice and rate under the course's `audio/`, with an audio checksum and actual WordBoundary milliseconds in its metadata. Incomplete/corrupt/mismatched cache entries are never played. Each lesson line is a separate clip; current-line highlighting and scrolling use that clip's actual WordBoundary intervals and the player's media position. Progress/seek apply to the current clip; clip changes may have short gaps. Without reliable boundaries, playback remains available but highlighting is explicitly disabled. Switching tabs/cards, settings, saved content or closing the dialog stops playback/generation. Failures keep confirmed text and import drafts for retry.

Validation uses a single 落地生根 Unit (U037) and the existing legacy-course tests. A real Edge TTS call was attempted on 2026-11-09; after sandbox network escalation the service returned WebSocket HTTP 403, so actual service audio and audible synchronization remain unverified. Real Qt decoding/control tests use explicitly synthetic WAV audio, not mocked TTS presented as success.

## 1. Product boundary (initial MVP)

Lingua is a local desktop tool for authoring, browsing, and eventually studying vocabulary-driven foreign-language courses. A Course contains Units. Four conceptual stages:

1. P1 — Course specification (human/GUI, `course.json`).
2. P2 — Units curriculum (predefined template, manual edit, or optional GPT discussion followed by JSON import, `units.json`).
3. P3 — Vocabulary generation (AI; **not part of this MVP**).
4. P4 — Dialogue/lesson materials and later TTS/interactive GPT practice (**not part of this MVP**).

A predefined course-curriculum template is copied into a new independent course. **Do not make the course depend at runtime on a template that may later change.** Avoid persisting a `template` key in `course.json`: the agreed contract has exactly these six fields:

`name`, `language`, `region`, `goal`, `default_level`, `requirements`.

A Unit has the seven agreed fields:

`id`, `stage`, `context`, `scenario`, `description`, `level`, `requirements`.

Preserve JSON UTF-8, original fields, IDs and array order. `context` = broad situation; `scenario` = specific situation; `description` = what the learner can do. Effective difficulty = `unit.level` if non-null, else `course.default_level`. A null effective difficulty means unspecified, **not** automatically CEFR A1.

## 2. What to borrow from existing code

Research references (read-only; do **not** modify either repository):

- [Ultimate_English_Learner](https://github.com/XuBoKai1999/Ultimate_English_Learner): `src/gui.py` uses Tkinter/ttk navigation and a user-controlled font zoom; `src/views/new_article.py` uses adjacent prompt/result editors and copy/import actions. Reuse these **workflow concepts**, not necessarily its UI toolkit or article-oriented data model.
- [calibration](https://github.com/XuBoKai1999/calibration): `src/calibration/ui/main_window.py` and `case_editor.py` use **PySide6**, `QVBoxLayout`/`QFormLayout`, `QScrollArea` and `QSettings`-persisted font zoom. Prefer this design approach to UEL's Tkinter for stable resizing, native widgets and Windows display scaling. Do not copy domain-specific calibration code.

**Decision:** Python 3.11+ and **PySide6** (desktop-first, Windows-first); local filesystem for JSON, no backend server, web frontend or database. Use Python's standard library wherever adequate. Tests may use `pytest` with Qt offscreen.

## 3. GUI: minimally complete, visually reviewable

### 3.1 Home

Two obvious actions, consistent with the earlier Lingua concept:

`進入教材` → browse existing local courses.  
`創建新教材` → course creation form.

Provide a clear Back/Home navigation path. Chinese interface by default. Do not create a third language-management hierarchy.

### 3.2 Create course

Form fields map directly to `course.json`:

- name, language, region (optional), goal, default_level (optional), requirements (multiline).
- Choose curriculum source: `落地生根` / `空白教材`.
- If choosing `落地生根`, allow selecting stages **0–3**, default **0 and 1 selected**. Copy only the selected stage entries from the existing JSON, preserving their original Unit IDs and sequence. Do not ask GPT to regenerate this template.
- If blank, create a valid `{"units": []}`.
- Show a read-only preview of how many Units will be created. No silent creation if required text fields are missing or no stage is selected for a nonempty template.
- Save a course directory containing only `course.json` and `units.json` initially. Do not pre-generate 128 vocabulary/material files.

### 3.3 Course browser and course workspace

Course browser lists saved courses; selecting one opens a usable workspace. The workspace should make it easy to give UI feedback **before P3/P4 exist**:

- Header: course name, language, region, goal; **Edit course** action.
- Left pane: units browser with levels **stage → context → scenario** (flat JSON is still the source of truth; do not introduce nested models). IDs and number of Units visible. Support stage navigation/filtering as convenient.
- Right pane: selected Unit inspector/editor with context, scenario, description, stage, level, requirements; **effective inherited level** displayed read-only. Save and Revert; clear indication of unsaved changes. Allow **add Unit** and **delete Unit with confirmation**, and preferably move up/down in array order where simple; keep stable IDs and avoid accidental duplication.
- The right side also provides a **lesson look-and-feel preview** for feedback. Show a clearly marked **demo-only** short exchange in two speakers, as a visual placeholder for future dialogue/TTS and a stub region for vocabulary and GPT interaction. Any Play, Record, Generate, Start GPT, AI actions not implemented must be **disabled or absent**, explicitly described as forthcoming; no fake success or simulated audio.
- No actual P3 vocabulary, P4 lesson generation, TTS, microphone, API or review engine in this MVP. A visual demo may be in code and **must not be written to a user's course files**.

### 3.4 Optional AI-assisted P2 planning (existing prompt, no AI API)

Provide a readable Prompt preview/copy UI similar in workflow to UEL, but Qt-based:

- Read the existing `prompts/course_to_units.md`, extract its **text fenced prompt**, and replace `{{course_json}}`, `{{existing_units_json}}`, `{{reference_units_json}}` and `{{extra_requirements}}`. Do not copy raw Markdown explanation as the prompt.
- Pre-fill current course and units; default optional reference to `null`, optional extra requirements via a text box. The Copy action must place **expanded** prompt text on clipboard, no leftover placeholders.
- Allow pasting/loading candidate `units.json` produced by GPT. Validate the JSON shape/types, unique IDs and collisions before save; show count/confirmation before replacing the curriculum. If cancelled or invalid, keep all existing data unchanged. Never quietly discard user changes.
- This is **prompt-assisted external conversation**, not an embedded chat window, API integration, or autonomous course generation.

## 4. Visual/layout reliability requirements

Use `QMainWindow` and Qt layouts exclusively: `QVBoxLayout`/`QHBoxLayout`/`QFormLayout`, `QSplitter` for left/right panes and `QScrollArea` for long forms. Avoid manual geometry calculations, absolute positioning and fixed widths that become invalid at another DPI or font size.

- Default window size should follow available screen geometry; do not exceed it. Ensure usable behavior at approx. 900×600 and on larger Windows desktops; use scrollbars when needed.
- Allow splitter resizing; set size policies, stretch and sensible minimum sizes. No overlapping/hidden controls when resizing.
- Font zoom (Ctrl+Plus, Ctrl+Minus, Ctrl+0; Ctrl+mouse wheel if straightforward), stored using `QSettings`; zoom text via app/base font while layouts recalculate. Standard mouse wheel still scrolls. Persist window size/geometry if simple.
- Prefer readable native controls and restrained styling. Do not build a custom widget/theme framework; no unbounded stylesheet overrides.
- All user-visible errors (corrupt JSON, failed write, invalid import) should be expressed clearly in Traditional Chinese.

## 5. Persistence and boundaries

- Templates/documents under `templates/`, `prompts/`, `decisions/` are **read-only shipped resources** for the app. The GUI never edits them.
- Store user-created courses under an **ignored** local `library/` directory (e.g. `library/<safe-course-folder>/course.json` and `units.json`); resolve the root deterministically relative to the checkout, not to arbitrary CWD, with optional injection/overrides for tests. Do not commit private courses.
- Sanitize course folder names; reject path traversal; handle name collisions without overwriting existing courses.
- Validate on load and before save, and write JSON in UTF-8 (`ensure_ascii=False`, readable indentation), using temp-file + atomic replace for updates. A failed save/import cannot destroy the prior valid file.
- Keep template JSON untouched when editing instances. Do not regenerate or silently normalize unrelated Units.
- Unsaved changes: Save, Revert/Cancel, and confirmation when leaving/replacing content. Editing a single Unit must not mutate others.
- No learning progress, generation state or AI output in P1/P2 JSON. Add no `database`, network stack, multi-user identity, telemetry, cloud backup or opaque service layer.

## 6. Suggested small code layout (not a rigid mandate)

~~~text
run.py
pyproject.toml
src/lingua/__init__.py
src/lingua/app.py         # QApplication and bootstrapping
src/lingua/ui.py          # Qt pages/dialogs/widgets; split only if this becomes unwieldy
src/lingua/storage.py     # JSON validation, load/save, template copying, prompt assembly helpers as needed
tests/test_storage.py
tests/test_ui.py
README.md
.gitignore
~~~

This is a **ceiling, not a quota**: reuse files rather than creating one module per view, one file per Unit, a second model/schema format, or extensive fixture directories. Only add a file when it serves an immediate requirement. No mass duplication of code from the reference repos.

## 7. Acceptance contract

A first-time user can launch the program, create an English course with `落地生根` stages 0–1 (**44 Units**), open it, browse stage/context/scenario, inspect/edit a Unit, close/reopen the app and see changes persisted, access the clearly labeled dialogue mock, and copy the expanded planning Prompt. They can also create a blank course and import validated Units after confirmation. Window resizing, zoom, corrupt JSON handling, and unsaved-change protection should work without overlaps or silent data loss.

Prove using automated storage tests, Qt offscreen tests, and a manual review checklist. Implement the whole GUI MVP before claiming it is finished, but **do not expand into real P3/P4**. Follow [steps.md](steps.md) for order, review points and handoff.
