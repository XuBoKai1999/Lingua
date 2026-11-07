# Lingua — GUI MVP Implementation Steps

> Status: **ready to implement**, 2026-11-07. Follow [arch.md](arch.md). This document defines the **entire** first GUI milestone; do not stop after building an empty shell.
>
> **Unattended execution:** work through steps 0–7 sequentially in one Codex run, testing and fixing between stages. Do not await further instructions after each step. **This is a single-developer repository: implement, commit and push directly on `main`; no feature branch or PR is required.** Keep changes small, verified, and reversible through normal Git history.

## Current source state

Lingua `main` currently contains design history, course/units JSON templates, the complete `落地生根` v0.2 curriculum (`128 Units`) plus Markdown review, and one P2 course-to-units Prompt. **There is no executable GUI yet.**

Borrow concepts from UEL (`tkinter` home navigation and copy/paste Prompt) and structural layout principles from calibration (`PySide6` / layouts / scrollable editor / zoom). Do not copy unrelated application logic.

## Step 0 — Repo audit & safe workspace

- [ ] Read `arch.md`, `steps.md`, current `decisions/003` and `004`, `templates/course.template.json`, `templates/units.template.json`, `templates/units/落地生根.json`, `prompts/course_to_units.md`.
- [ ] Inspect reference GUI source from UEL (`src/gui.py`, `src/views/new_article.py`) and calibration (`src/calibration/ui/main_window.py`, `case_editor.py`). Only borrow concepts and verified implementation patterns.
- [ ] Check `git status` and current branch; work on `main` after safely fetching/updating from `origin/main`. Do not discard uncommitted user changes or existing branch work; if already on a different branch, transition safely without resetting, overwriting, or losing work. Never force-push or commit user course data.
- [ ] Confirm existing JSON field definitions and stage count **16/28/44/40**. Do not modify approved templates, previous decisions, or archival files just to suit GUI assumptions.

**Gate:** both references understood and data contract identified.

## Step 1 — Bootstrapping & deterministic storage

- [ ] Add minimal Python 3.11+ PySide6 packaging/launch (`pyproject.toml`, `run.py` and smallest sensible `src/lingua` package); dependencies only what is necessary, e.g. PySide6 and pytest for test extra. Document exact PowerShell commands.
- [ ] Build local `library/` persistence; gitignore it alongside Qt cache, temporary files and virtual environments. Resolve all source templates relative to repo root, independent of current working directory. Permit temporary library-root injection for tests.
- [ ] Add strict but small course/unit JSON validators matching the existing **six/seven-field contracts**. Validate wrong types, blank required names/goals, duplicate IDs, illegal stage values and invalid imports.
- [ ] Implement create/list/load/save course, copy selected template stages without modifying template, create blank units, edit existing Units, add new IDs, delete Units, and atomic save. Avoid silently overwriting existing course directories.
- [ ] Write persistence tests: 0–1 creates 44 Units; 0–3 creates 128; null/explicit level; reopening; blank course; invalid import leaves original intact; no template mutation; no path traversal.

**Gate:** storage tests pass before GUI wiring.

## Step 2 — Real GUI shell and course creation

- [ ] Start `QMainWindow` with **進入教材** and **創建新教材** as obvious home actions, plus back/home navigation.
- [ ] Build responsive creation form for all six `course.json` fields. Select `落地生根` or `空白教材`; show stage 0–3 checkboxes only for template; default stage 0 and 1; preview selected Unit count.
- [ ] On Save, validate inputs, persist course+units, and open new course workspace. Cancel leaves no created data. Error messages should be readable in Traditional Chinese.
- [ ] Build course browser listing saved courses; open or return without losing state. Treat missing or corrupt course JSON as a visible error, not a crash.
- [ ] Verify creation on Windows-sized and reduced windows; use Qt layouts and scroll areas, no pixel-coordinate positioning.

**Gate:** create, close, reopen a 44-Unit English course through GUI.

## Step 3 — Course workspace & editing

- [ ] Header shows name, language, region and goal with Edit Course.
- [ ] Resizable `QSplitter`: left Unit tree grouped by stage → context → scenario; right Unit detail form. Large text fields wrap/scroll instead of clipping.
- [ ] Show Unit ID, stage, context, scenario, description, level, requirements and inherited **effective level**. Saving one Unit preserves others and source ID.
- [ ] Add/remove Unit with ID validation and explicit delete confirmation. Move Up/Down if it can be implemented clearly without duplicating ordering state. Maintain array order as authority.
- [ ] Save/Revert and navigation-away warning for unsaved edits. No silent loss when selecting another Unit or switching screens.
- [ ] Fonts zoom via keyboard (and optionally Ctrl+wheel), persisted using `QSettings`. Qt layouts should continue to work at zoom levels around 80–200% or use scrollbars to preserve reachability.

**Gate:** edit one Unit, reopen, verify exact saved changes; resize/zoom without overlapping or missing controls.

## Step 4 — P2 external-AI workflow

- [ ] Add GUI route to show/copy the P2 prompt from existing `prompts/course_to_units.md`. Extract the prompt fenced text, not the explanatory Markdown.
- [ ] Substitute current `course_json`, current `existing_units_json`, `reference_units_json` (null by default unless deliberately chosen), and `extra_requirements` (optional). Clipboard must contain a fully expanded Prompt without `{{...}}` holes.
- [ ] Allow paste or load JSON for proposed Units; validate and preview count, warn about replacement, import only after explicit confirmation. Invalid or cancelled import changes nothing. Expose errors clearly.
- [ ] Do not integrate an LLM API, chat service or autonomous planning engine.

**Gate:** copy a usable prompt and safely import a hand-crafted test `units.json` through GUI.

## Step 5 — Visually inspectable lesson preview, no fake capabilities

- [ ] Provide a tab/panel for the future dialogue-led learning experience: multiple short exchanges layout, speaker attribution, space for vocab, and a visibly separate future GPT interaction area.
- [ ] To facilitate user feedback before P3/P4, supply a **clearly labeled demo-only short conversation** (e.g., meeting someone on a trip), not included in saved course JSON. The demo may live as a small constant in UI code.
- [ ] Playback/recording/generation controls not implemented **must be disabled or omitted**, with honest explanatory labels. Do not create fake TTS, fake recordings, fake GPT outputs or buttons that appear to work.
- [ ] Ensure lesson-preview UI remains readable on smaller screens and at zoom.

**Gate:** GUI can be demonstrated for layout critique without any AI credentials, Internet, TTS or material files.

## Step 6 — Automated checks and manual checklist

- [ ] Run `python -m pytest -q` including storage tests and Qt tests using `QT_QPA_PLATFORM=offscreen` where no display is available. Tests must create `QApplication` safely and not rely on audio/API/network.
- [ ] Test navigational smoke path: home → create stages 0+1 → 44 Units → inspect/edit U037 (first social Unit) → save → reopen → course_to_units Prompt copy → import test valid Units → cancel invalid replacement.
- [ ] Verify stage-select counts, schema conformance, Unicode Chinese fields, valid JSON, unique IDs, data persistence, zoom and responsive layout as far as environment permits.
- [ ] Run a non-GUI import/syntax check. If Qt GUI cannot launch in headless environment, do an offscreen smoke check and **report limitations accurately**.
- [ ] If screenshot capture is available in offscreen mode, capture a real GUI screenshot of home, course creation, course editor and lesson preview into a temporary ignored location; do not fabricate UI captures. Screenshots are optional, not blockers.
- [ ] Conduct self-review for overengineering, data overwrite hazards, unwanted modifications, unimplemented clickable controls, hard-coded dimensions, broken imports and unnecessary dependencies.

**Gate:** all available tests pass or unavoidable environment limitations are documented, with no silent failures.

## Step 7 — Handoff, docs, commits and direct main push

- [ ] Update `README.md` with exact Windows PowerShell installation/run/test commands, features available **now** and explicit future/nonfunctional UI items.
- [ ] Update this `steps.md` checkboxes/status to match what was **actually** completed. Do not mark a blocked item complete.
- [ ] Make small, logical commits **directly on `main`** after relevant verification; push to `origin/main` using a normal, non-force push. Do not create a feature branch or PR for this task, do not reset/rewrite history, and do not overwrite uncommitted changes. If the remote changed, fetch and reconcile safely before pushing; report unresolved conflicts instead of forcing.
- [ ] Give concise handoff with: latest `main` commit link and push status, implemented screens, run commands, test results, known limitations, and places where user GUI feedback is needed.

## Minimum acceptance checklist

| Check | Expected |
| --- | --- |
| Installation/startup | Windows desktop launches with `python run.py` after documented install |
| Home | Both `進入教材` and `創建新教材` work |
| Create from template | Stage 0+1 → **44** Units; stage 0–3 → **128** Units |
| Blank course | Valid `course.json` + `{"units": []}` |
| Browse | stage/context/scenario tree works and respects order |
| Edit | course and Unit edits persist; effective level inherits; source template unchanged |
| Protect | invalid JSON, duplicate IDs, unintended overwrite and unsaved changes handled safely |
| P2 | copy expanded Prompt + validated, confirmed JSON import |
| Lesson preview | visually useful demo, explicitly **not** actual audio/GPT |
| Layout | resize, scroll, zoom without lost controls |
| Tests | storage and Qt offscreen tests pass or provide precise blockers |

## Explicit out of scope

No P3/P4 AI material generation, LLM keys, real GPT interaction, TTS or speech evaluation, writing assessment, multi-user accounts, login, cloud, database, threaded jobs, full feature parity with UEL, or calibration-specific logic.

**Avoid adding entities unless necessary**: no repository-wide architecture framework, plugin discovery, schema-version migration suite, rich task engine, extra JSON metadata, or one-Python-module-per-widget structure. Do not prioritize speculative future features over a working GUI.
