# Lingua — GUI MVP Implementation Steps

> Status: **GUI MVP implemented; single-unit production/learning extension added**, 2026-11-09. Follow [arch.md](arch.md). The current extension below supersedes the initial milestone's P3/P4/TTS exclusions.
>
> **Unattended execution:** work through steps 0–7 sequentially in one Codex run, testing and fixing between stages. Do not await further instructions after each step. **This is a single-developer repository: implement, commit and push directly on `main`; no feature branch or PR is required.** Keep changes small, verified, and reversible through normal Git history.

## Current source state

P3 context follow-up (2026-11-11): implemented the approved vocabulary Prompt with live course/curriculum data, current-Unit marking in array order, and compact summaries from preceding valid confirmed vocabulary. Missing/invalid/stale/retired-only history is explicitly incomplete. Refresh/copy detects deleted Units and read failures without discarding import drafts. Course/Unit/card contracts, P4 and source-snapshot save protection are unchanged. Verification results and limits are recorded in [the work record](chat/20261111-p3-prompt-context.md).

P2-specific correction: the user's reported window was `PromptDialog`, not the earlier `LearningDialog`. P2 now has simultaneous left Prompt/right JSON panes and normal MinMax window hints, plus cancel-safe draft replacement/closing. The full suite passed 80 tests, and 6 additional Microsoft JhengHei font layout cases passed. Native inspection was attempted but app-selection approval timed out; actual Windows title-bar clicks remain a manual acceptance item, not marked passed by offscreen tests.

Unit-production layout follow-up: three explicit stages, shared left-Prompt/right-result splitter, collapsible temporary requirements and on-demand detailed preview. Each stage retains its own draft; confirmed content resumes without regeneration. Audio controls only appear in speech/study. Automated checks exercise 100%/200% fonts at 700×500, 900×600, 1280×720 and 1440×900 after layout settles, including scroll-to-action reachability. Actual Qt screenshots with Microsoft JhengHei are retained outside the repo; native Windows DPI/human acceptance remains separate from offscreen checks.

Windows launch follow-up: `py run.py` works directly from the checkout; `.venv` and editable installation are optional. Dependency checks and consent-based pip installation/restart live in the existing `run.py`. Verification: 57 tests passed, including a source-copy GUI launch with editable `.pth` activation disabled and no project import available beforehand. Dependency installation/restart branches are simulated; a separate clean Windows PC has not been tested. Existing TTS worker/cache/Qt playback regression tests remain passing.

Single-unit extension: the workspace now offers vocabulary/lesson Prompt exchange, validated confirmed import, per-Unit persistence, vocabulary cards, bilingual reading and content-matched Edge TTS/Qt playback. Only requested current-Unit content is produced.

- [x] Read the existing contracts and Ultimate_English_Learner `src/gui.py`, `src/tts.py`, `src/player.py` (read-only); retain PySide6 and native Qt playback.
- [x] Unit-specific P3/P4 Prompts, confirmed vocabulary dependency, source/ID validation, UTF-8 import preview, cancellation and write-failure protection.
- [x] Atomic per-Unit records and safe hashed paths; retire changed/deleted identities, preserve other Units and legacy course files.
- [x] Card word/example playback, lesson controls/progress, actual WordBoundary-based current-line display and explicit no-timestamp limitation.
- [x] Regression checks for single-unit roundtrip/reopen, invalid input, cancellation, failed writes/retry, curriculum changes, cache identity, and Qt playback controls.
- [x] Actual online TTS follow-up (2026-11-09): upgraded the running environment from 7.2.8 to 7.3.1 and raised the dependency minimum. Fresh-cache fixed-text synthesis returned real MP3 (21,456 bytes) and 5 valid WordBoundary intervals; Qt decoded 3,576 ms and passed muted playback/control checks. All 44 regression tests passed. The earlier 7.2.8 HTTP 403 remains recorded in the previous work record.
- [ ] Human acceptance: audible output quality and visual timing on the user's Windows display. Muted Qt playback does not substitute for human listening.

The original steps below record the initial GUI milestone; they do not restrict this newly authorized extension.

Lingua `main` contains the working PySide6 GUI MVP for course creation, browsing and editing, validated P2 Prompt/import workflows, and a demo-only lesson preview, alongside the design history, course/units JSON templates, the complete `落地生根` v0.2 curriculum (`128 Units`) and P2 course-to-units Prompt.

Follow-up verification covers creation-draft leave confirmation, keeping course edits open after failed writes, and rejecting non-UTF-8 imports without replacing existing text or course data.

Borrow concepts from UEL (`tkinter` home navigation and copy/paste Prompt) and structural layout principles from calibration (`PySide6` / layouts / scrollable editor / zoom). Do not copy unrelated application logic.

## Step 0 — Repo audit & safe workspace

- [x] Read `arch.md`, `steps.md`, current `decisions/003` and `004`, `templates/course.template.json`, `templates/units.template.json`, `templates/units/落地生根.json`, `prompts/course_to_units.md`.
- [x] Inspect reference GUI source from UEL (`src/gui.py`, `src/views/new_article.py`) and calibration (`src/calibration/ui/main_window.py`, `case_editor.py`). Only borrow concepts and verified implementation patterns.
- [x] Check `git status` and current branch; work on `main` after safely fetching/updating from `origin/main`. Do not discard uncommitted user changes or existing branch work; if already on a different branch, transition safely without resetting, overwriting, or losing work. Never force-push or commit user course data.
- [x] Confirm existing JSON field definitions and stage count **16/28/44/40**. Do not modify approved templates, previous decisions, or archival files just to suit GUI assumptions.

**Gate:** both references understood and data contract identified.

## Step 1 — Bootstrapping & deterministic storage

- [x] Add minimal Python 3.11+ PySide6 packaging/launch (`pyproject.toml`, `run.py` and smallest sensible `src/lingua` package); dependencies only what is necessary, e.g. PySide6 and pytest for test extra. Document exact PowerShell commands.
- [x] Build local `library/` persistence; gitignore it alongside Qt cache, temporary files and virtual environments. Resolve all source templates relative to repo root, independent of current working directory. Permit temporary library-root injection for tests.
- [x] Add strict but small course/unit JSON validators matching the existing **six/seven-field contracts**. Validate wrong types, blank required names/goals, duplicate IDs, illegal stage values and invalid imports.
- [x] Implement create/list/load/save course, copy selected template stages without modifying template, create blank units, edit existing Units, add new IDs, delete Units, and atomic save. Avoid silently overwriting existing course directories.
- [x] Write persistence tests: 0–1 creates 44 Units; 0–3 creates 128; null/explicit level; reopening; blank course; invalid import leaves original intact; no template mutation; no path traversal.

**Gate:** storage tests pass before GUI wiring.

## Step 2 — Real GUI shell and course creation

- [x] Start `QMainWindow` with **進入教材** and **創建新教材** as obvious home actions, plus back/home navigation.
- [x] Build responsive creation form for all six `course.json` fields. Select `落地生根` or `空白教材`; show stage 0–3 checkboxes only for template; default stage 0 and 1; preview selected Unit count.
- [x] On Save, validate inputs, persist course+units, and open new course workspace. Cancel leaves no created data. Error messages should be readable in Traditional Chinese.
- [x] Build course browser listing saved courses; open or return without losing state. Treat missing or corrupt course JSON as a visible error, not a crash.
- [x] Verify creation on Windows-sized and reduced windows; use Qt layouts and scroll areas, no pixel-coordinate positioning.

**Gate:** create, close, reopen a 44-Unit English course through GUI.

## Step 3 — Course workspace & editing

- [x] Header shows name, language, region and goal with Edit Course.
- [x] Resizable `QSplitter`: left Unit tree grouped by stage → context → scenario; right Unit detail form. Large text fields wrap/scroll instead of clipping.
- [x] Show Unit ID, stage, context, scenario, description, level, requirements and inherited **effective level**. Saving one Unit preserves others and source ID.
- [x] Add/remove Unit with ID validation and explicit delete confirmation. Move Up/Down if it can be implemented clearly without duplicating ordering state. Maintain array order as authority.
- [x] Save/Revert and navigation-away warning for unsaved edits. No silent loss when selecting another Unit or switching screens.
- [x] Fonts zoom via keyboard (and optionally Ctrl+wheel), persisted using `QSettings`. Qt layouts should continue to work at zoom levels around 80–200% or use scrollbars to preserve reachability.

**Gate:** edit one Unit, reopen, verify exact saved changes; resize/zoom without overlapping or missing controls.

## Step 4 — P2 external-AI workflow

- [x] Add GUI route to show/copy the P2 prompt from existing `prompts/course_to_units.md`. Extract the prompt fenced text, not the explanatory Markdown.
- [x] Substitute current `course_json`, current `existing_units_json`, `reference_units_json` (null by default unless deliberately chosen), and `extra_requirements` (optional). Clipboard must contain a fully expanded Prompt without `{{...}}` holes.
- [x] Allow paste or load JSON for proposed Units; validate and preview count, warn about replacement, import only after explicit confirmation. Invalid or cancelled import changes nothing. Expose errors clearly.
- [x] Do not integrate an LLM API, chat service or autonomous planning engine.

**Gate:** copy a usable prompt and safely import a hand-crafted test `units.json` through GUI.

## Step 5 — Visually inspectable lesson preview, no fake capabilities

- [x] Provide a tab/panel for the future dialogue-led learning experience: multiple short exchanges layout, speaker attribution, space for vocab, and a visibly separate future GPT interaction area.
- [x] To facilitate user feedback before P3/P4, supply a **clearly labeled demo-only short conversation** (e.g., meeting someone on a trip), not included in saved course JSON. The demo may live as a small constant in UI code.
- [x] Playback/recording/generation controls not implemented **must be disabled or omitted**, with honest explanatory labels. Do not create fake TTS, fake recordings, fake GPT outputs or buttons that appear to work.
- [x] Ensure lesson-preview UI remains readable on smaller screens and at zoom.

**Gate:** GUI can be demonstrated for layout critique without any AI credentials, Internet, TTS or material files.

## Step 6 — Automated checks and manual checklist

- [x] Run `python -m pytest -q` including storage tests and Qt tests using `QT_QPA_PLATFORM=offscreen` where no display is available. Tests must create `QApplication` safely and not rely on audio/API/network.
- [x] Test navigational smoke path: home → create stages 0+1 → 44 Units → inspect/edit U037 (first social Unit) → save → reopen → course_to_units Prompt copy → import test valid Units → cancel invalid replacement.
- [x] Verify stage-select counts, schema conformance, Unicode Chinese fields, valid JSON, unique IDs, data persistence, zoom and responsive layout as far as environment permits.
- [x] Run a non-GUI import/syntax check. If Qt GUI cannot launch in headless environment, do an offscreen smoke check and **report limitations accurately**.
- [x] If screenshot capture is available in offscreen mode, capture a real GUI screenshot of home, course creation, course editor and lesson preview into a temporary ignored location; do not fabricate UI captures. Screenshots are optional, not blockers.
- [x] Conduct self-review for overengineering, data overwrite hazards, unwanted modifications, unimplemented clickable controls, hard-coded dimensions, broken imports and unnecessary dependencies.

**Gate:** all available tests pass or unavoidable environment limitations are documented, with no silent failures.

## Step 7 — Handoff, docs, commits and direct main push

- [x] Update `README.md` with exact Windows PowerShell installation/run/test commands, features available **now** and explicit future/nonfunctional UI items.
- [x] Update this `steps.md` checkboxes/status to match what was **actually** completed. Do not mark a blocked item complete.
- [x] Make small, logical commits **directly on `main`** after relevant verification; push to `origin/main` using a normal, non-force push. Do not create a feature branch or PR for this task, do not reset/rewrite history, and do not overwrite uncommitted changes. If the remote changed, fetch and reconcile safely before pushing; report unresolved conflicts instead of forcing.
- [x] Give concise handoff with: latest `main` commit link and push status, implemented screens, run commands, test results, known limitations, and places where user GUI feedback is needed.

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
