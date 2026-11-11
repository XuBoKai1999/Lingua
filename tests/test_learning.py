from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import types
import wave
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings, Qt, QUrl
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QScrollArea
from PySide6.QtTest import QTest

from lingua import materials, speech, storage
from lingua.learning import LearningDialog


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_speech_settings(tmp_path, monkeypatch):
    import lingua.learning as learning
    settings = QSettings(str(tmp_path / "speech.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(learning, "QSettings", lambda *a: settings)


@pytest.fixture
def prepared(tmp_path):
    course = {"name": "English", "language": "English", "region": "UK", "goal": "Travel and meet people", "default_level": "A2", "requirements": "Use natural speech"}
    directory = storage.create_course(course, template_stages=(0, 1), library_root=tmp_path)
    units = storage.load_course(directory)[1]
    unit = units["units"][36]
    vocab = {"unit_id": unit["id"], "cards": [{"text": "seat taken", "pos": "phrase", "meaning_zh": "座位有人坐", "example": "Is this seat taken?", "example_zh": "這個座位有人坐嗎？"}]}
    lesson = {"unit_id": unit["id"], "lines": [{"speaker": "A", "text": "Hello! Is this seat taken?", "translation_zh": "你好！這個座位有人坐嗎？"}, {"speaker": "B", "text": "No, please sit down.", "translation_zh": "沒有，請坐。"}]}
    return directory, course, units, unit, vocab, lesson


def test_single_unit_prompts_roundtrip_and_other_units_unchanged(prepared):
    directory, course, units, unit, vocab, lesson = prepared
    original = (directory / "units.json").read_bytes()
    prompt = materials.build_unit_prompt(course, unit, "vocabulary", extra="Short dialogues")
    assert all(value in prompt for value in ("UK", "Travel and meet people", "A2", unit["context"], unit["description"], "Short dialogues"))
    assert materials.load_material(directory, course, unit)["vocabulary"] is None
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    prompt = materials.build_unit_prompt(course, unit, "lesson", vocab)
    assert "confirmed_vocabulary" in prompt and "seat taken" in prompt
    materials.save_content(directory, course, unit, "lesson", lesson)
    record = materials.load_material(directory, course, unit)
    assert record["lesson"] == lesson and record["vocabulary"] == vocab
    assert (directory / "units.json").read_bytes() == original
    assert storage.load_course(directory)[0] == course
    assert len(list((directory / "materials").glob("*.json"))) == 1
    assert materials.load_material(directory, course, units["units"][0])["lesson"] is None
    assert '"effective_level": null' in materials.build_unit_prompt({**course, "default_level": None}, unit, "vocabulary")
    assert '"effective_level": "B1"' in materials.build_unit_prompt(course, {**unit, "level": "B1"}, "vocabulary")
    with pytest.raises(ValueError):
        materials.build_unit_prompt(course, unit, "lesson")


@pytest.fixture
def prompt_course(tmp_path):
    course = {"name": "Deutsch", "language": "Deutsch", "region": None, "goal": "在不同德語地區旅行與交流", "default_level": "B2", "requirements": "保留自然用語"}
    directory = storage.create_course(course, library_root=tmp_path)
    units = {"units": [
        {"id": unit_id, "stage": stage, "context": f"情境 {i}", "scenario": f"主題 {i}", "description": f"能力 {i}", "level": None, "requirements": f"單元要求 {i}"}
        for i, (unit_id, stage) in enumerate((("U090", 4), ("U003", 0), ("unit-final", None), ("U001", 1)))
    ]}
    storage.save_units(directory, units)
    return directory, course, units, units["units"][2]


def test_p3_order_current_marker_summary_and_json_contract(prompt_course):
    directory, course, units, unit = prompt_course
    originals = [(directory / name).read_bytes() for name in ("course.json", "units.json")]
    for i, item in enumerate(units["units"]):
        vocabulary = {"unit_id": item["id"], "cards": [{"text": f"Wort {i}", "pos": "名詞", "meaning_zh": f"中文義 {i}", "example": f"Nur Beispiel {i}", "example_zh": f"不該列入摘要的翻譯 {i}"}]}
        materials.save_content(directory, course, item, "vocabulary", vocabulary)
    prompt = materials.build_unit_prompt(course, unit, "vocabulary", extra="本次附加要求", course_dir=directory)
    overview = json.loads(prompt.split("課綱總覽（current_unit 為 true 表示目前單元）：\n")[1].split("\n\n目前單元完整資料與有效程度：")[0])
    assert [item["id"] for item in overview] == [item["id"] for item in units["units"]]
    assert [item["current_unit"] for item in overview] == [False, False, True, False]
    assert all(set(item) == {"id", "stage", "context", "scenario", "description", "current_unit"} for item in overview)
    current = json.loads(prompt.split("目前單元完整資料與有效程度：\n")[1].split("\n\n先前單元有效詞卡：")[0])
    assert current == {"unit": unit, "effective_level": "B2"}
    history = prompt.split("先前單元有效詞卡：\n")[1].split("\n\n當次要求：")[0]
    summaries = json.loads(history[history.index("["):])
    assert [item["unit_id"] for item in summaries] == ["U090", "U003"]
    assert all(set(card) == {"text", "pos", "meaning_zh"} for item in summaries for card in item["cards"])
    assert "Wort 0" in history and "Wort 1" in history
    assert all(text not in history for text in ("Wort 2", "Wort 3", "Nur Beispiel", "不該列入摘要的翻譯"))
    assert "已提供 2/2" in history and "不代表已學會" in history and "不保證完整去重" in history
    output, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("{"):])
    materials.validate_content(output, unit["id"], "vocabulary")
    assert set(output) == {"unit_id", "cards"}
    assert set(output["cards"][0]) == {"text", "pos", "meaning_zh", "example", "example_zh"}
    assert '"region": null' in prompt and "本次附加要求" in prompt
    assert "［" not in prompt and "{{" not in prompt and "落地生根" not in prompt
    assert originals == [(directory / name).read_bytes() for name in ("course.json", "units.json")]


@pytest.mark.parametrize("invalid", ["missing", "json", "utf8", "cards", "course", "unit", "lesson", "wrong_id", "retired"])
def test_p3_partial_history_excludes_invalid_and_retired(prompt_course, invalid):
    directory, course, units, unit = prompt_course
    first, second = units["units"][:2]
    vocabulary = {"unit_id": first["id"], "cards": [{"text": "gültig", "pos": "形容詞", "meaning_zh": "有效", "example": "Das ist gültig.", "example_zh": "這是有效的。"}]}
    materials.save_content(directory, course, first, "vocabulary", vocabulary)
    rejected = {**vocabulary, "unit_id": second["id"], "cards": [{**vocabulary["cards"][0], "text": "DO_NOT_INCLUDE"}]}
    record = {"source": {"course": deepcopy(course), "unit": deepcopy(second)}, "vocabulary": rejected, "lesson": None}
    path = materials.material_path(directory, second["id"])
    if invalid == "cards":
        record["vocabulary"]["cards"][0]["meaning_zh"] = " "
    elif invalid == "course":
        record["source"]["course"]["goal"] = "舊課程"
    elif invalid == "unit":
        record["source"]["unit"]["description"] = "舊規範"
    elif invalid == "lesson":
        record["lesson"] = {"unit_id": second["id"], "lines": []}
    elif invalid == "wrong_id":
        record["vocabulary"]["unit_id"] = first["id"]
    if invalid != "missing":
        if invalid == "retired":
            path = path.with_suffix(".retired-test.json")
        storage._write_json_atomic(path, record)
        if invalid in {"json", "utf8"}:
            path.write_bytes(b"{" if invalid == "json" else b"\xff")
    prompt = materials.build_unit_prompt(course, unit, "vocabulary", course_dir=directory)
    history = prompt.split("先前單元有效詞卡：\n")[1].split("\n\n當次要求：")[0]
    assert "已提供 1/2" in history and "紀錄不完整" in history and "未提供有效詞卡的單元：U003" in history
    assert "gültig" in history and "DO_NOT_INCLUDE" not in history


def test_p3_no_history_and_no_directory_are_explicit(prompt_course):
    directory, course, units, unit = prompt_course
    prompt = materials.build_unit_prompt(course, unit, "vocabulary", course_dir=directory)
    assert "已提供 0/2" in prompt and "紀錄不完整" in prompt
    assert prompt.endswith("當次要求：\n無")
    prompt = materials.build_unit_prompt(course, units["units"][0], "vocabulary", course_dir=directory)
    assert "未提供：目前單元之前沒有單元。" in prompt
    prompt = materials.build_unit_prompt(course, unit, "vocabulary")
    assert "未提供：未指定課程資料夾" in prompt
    assert "未提供：無法確認先前單元的有效詞卡，紀錄不完整。" in prompt


@pytest.mark.parametrize(("default", "override", "expected"), [(None, None, None), ("B2", None, "B2"), ("B2", "C1", "C1")])
def test_p3_live_effective_level_and_region(prompt_course, default, override, expected):
    directory, course, units, unit = prompt_course
    storage.save_course(directory, {**course, "default_level": default, "region": "德國、奧地利與瑞士"})
    units["units"][2] = {**unit, "level": override}
    storage.save_units(directory, units)
    prompt = materials.build_unit_prompt(course, unit, "vocabulary", course_dir=directory)
    assert '"effective_level": ' + json.dumps(expected) in prompt
    assert "德國、奧地利與瑞士" in prompt
    assert "未指定時不要自行當成 A1" in prompt


def test_p3_open_dialog_rereads_course_order_unit_and_deletion(app, prompt_course):
    directory, course, units, unit = prompt_course
    dialog = LearningDialog(directory, course, unit)
    changed_course = {**course, "goal": "最新課程目標", "default_level": "C2"}
    storage.save_course(directory, changed_course)
    ordered = {"units": [units["units"][3], {**unit, "description": "最新能力目標"}, *units["units"][:2]]}
    storage.save_units(directory, ordered)
    previous = ordered["units"][0]
    vocabulary = {"unit_id": previous["id"], "cards": [{"text": "neu", "pos": "形容詞", "meaning_zh": "新的", "example": "Das ist neu.", "example_zh": "這是新的。"}]}
    materials.save_content(directory, changed_course, previous, "vocabulary", vocabulary)
    assert dialog.refresh_prompt()
    dialog.copy_prompt()
    prompt = QApplication.clipboard().text()
    assert prompt == dialog.prompt.toPlainText()
    assert "最新課程目標" in prompt and "最新能力目標" in prompt and '"effective_level": "C2"' in prompt
    assert prompt.index('"id": "U001"') < prompt.index('"id": "unit-final"') < prompt.index('"id": "U090"')
    history = prompt.split("先前單元有效詞卡：\n")[1].split("\n\n當次要求：")[0]
    assert "已提供 1/1" in history and "neu" in history and "U090" not in history
    assert dialog.course == course and dialog.unit == unit
    with pytest.raises(ValueError, match="課綱已變更"):
        materials.save_content(directory, course, unit, "vocabulary", {**vocabulary, "unit_id": unit["id"]})
    storage.save_units(directory, {"units": [previous]})
    QApplication.clipboard().setText("keep clipboard")
    dialog.copy_prompt()
    assert not dialog.prompt.toPlainText() and "單元已刪除" in dialog.status.text()
    assert QApplication.clipboard().text() == "keep clipboard"
    dialog.reject()


@pytest.mark.parametrize("failure", ["json", "utf8", "missing_course", "missing_units"])
def test_p3_live_read_failure_clears_prompt_and_keeps_draft(app, prompt_course, failure):
    directory, course, _, unit = prompt_course
    dialog = LearningDialog(directory, course, unit)
    draft = '{"unfinished": true}'
    dialog.import_text.setPlainText(draft)
    if failure.startswith("missing"):
        (directory / ("course.json" if failure == "missing_course" else "units.json")).unlink()
    else:
        (directory / "units.json").write_bytes(b"{" if failure == "json" else b"\xff")
    assert not dialog.refresh_prompt()
    assert dialog.prompt.toPlainText() == "" and dialog.status.text()
    assert dialog.status.text().startswith("無法產生 Prompt：")
    assert dialog.import_text.toPlainText() == draft and dialog.import_dirty
    dialog.import_text.clear()
    dialog.reject()


def test_p3_switch_course_uses_its_own_history(app, prompt_course, tmp_path):
    directory, course, units, unit = prompt_course
    other_course = {**course, "name": "Français", "language": "Français", "region": "France"}
    other_dir = storage.create_course(other_course, library_root=tmp_path)
    storage.save_units(other_dir, units)
    for root, settings, text in ((directory, course, "FIRST_COURSE_ONLY"), (other_dir, other_course, "SECOND_COURSE_ONLY")):
        first = units["units"][0]
        materials.save_content(root, settings, first, "vocabulary", {"unit_id": first["id"], "cards": [{"text": text, "pos": "名詞", "meaning_zh": "測試詞", "example": "Exemple.", "example_zh": "例句。"}]})
    first_dialog = LearningDialog(directory, course, unit)
    first_dialog.copy_prompt()
    assert "FIRST_COURSE_ONLY" in QApplication.clipboard().text()
    first_dialog.reject()
    second_dialog = LearningDialog(other_dir, other_course, unit)
    second_dialog.copy_prompt()
    prompt = QApplication.clipboard().text()
    assert "SECOND_COURSE_ONLY" in prompt and "FIRST_COURSE_ONLY" not in prompt
    assert "Français" in prompt and '"region": "France"' in prompt
    second_dialog.reject()


@pytest.mark.parametrize("mutation", ["wrong_id", "empty", "type", "extra"])
def test_invalid_content_preserves_old(prepared, mutation):
    directory, course, _, unit, vocab, _ = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    original = materials.material_path(directory, unit["id"]).read_bytes()
    data = deepcopy(vocab)
    if mutation == "wrong_id":
        data["unit_id"] = "U001"
    elif mutation == "empty":
        data["cards"] = []
    elif mutation == "type":
        data["cards"][0]["text"] = 3
    else:
        data["cards"][0]["extra"] = "unexpected"
    with pytest.raises(ValueError):
        materials.save_content(directory, course, unit, "vocabulary", data)
    assert materials.material_path(directory, unit["id"]).read_bytes() == original


def test_failed_material_save_and_retry_invalidates_lesson(prepared, monkeypatch):
    directory, course, _, unit, vocab, lesson = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    materials.save_content(directory, course, unit, "lesson", lesson)
    original = materials.material_path(directory, unit["id"]).read_bytes()
    changed = deepcopy(vocab)
    changed["cards"][0]["text"] = "new phrase"
    replace = storage.os.replace
    monkeypatch.setattr(storage.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        materials.save_content(directory, course, unit, "vocabulary", changed)
    assert materials.material_path(directory, unit["id"]).read_bytes() == original
    monkeypatch.setattr(storage.os, "replace", replace)
    assert materials.save_content(directory, course, unit, "vocabulary", changed)["lesson"] is None


def test_safe_paths_delete_replace_reuse_and_rollback(prepared, monkeypatch):
    directory, course, units, unit, vocab, _ = prepared
    assert materials.material_path(directory, "../../outside").parent == directory / "materials"
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    other = units["units"][0]
    other_vocab = {**vocab, "unit_id": other["id"]}
    materials.save_content(directory, course, other, "vocabulary", other_vocab)
    other_bytes = materials.material_path(directory, other["id"]).read_bytes()
    without = {"units": [u for u in units["units"] if u["id"] != unit["id"]]}
    replace = storage.os.replace
    monkeypatch.setattr(storage.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("failed curriculum write")))
    with pytest.raises(OSError):
        storage.save_units(directory, without)
    assert materials.load_material(directory, course, unit)["vocabulary"] == vocab
    monkeypatch.setattr(storage.os, "replace", replace)
    storage.save_units(directory, without)
    with pytest.raises(ValueError, match="刪除"):
        materials.save_content(directory, course, unit, "vocabulary", vocab)
    storage.save_units(directory, units)
    assert materials.load_material(directory, course, unit)["vocabulary"] is None
    assert materials.material_path(directory, other["id"]).read_bytes() == other_bytes
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    changed = deepcopy(units)
    changed["units"][36]["description"] = "New task"
    storage.save_units(directory, changed)
    assert materials.load_material(directory, course, changed["units"][36])["vocabulary"] is None
    assert list((directory / "materials").glob("*.retired-*.json"))


def test_gui_import_cancel_failure_retry_reopen_and_switch(app, prepared, monkeypatch):
    directory, course, units, unit, vocab, lesson = prepared
    dialog = LearningDialog(directory, course, unit)
    dialog.copy_prompt()
    assert unit["scenario"] in QApplication.clipboard().text()
    dialog.import_text.setPlainText(json.dumps(vocab))
    dialog.validate_import()
    assert dialog.save.isEnabled()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    dialog.save_import()
    assert not materials.material_path(directory, unit["id"]).exists()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    write = materials._write_json_atomic
    monkeypatch.setattr(materials, "_write_json_atomic", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    dialog.save_import()
    assert dialog.import_dirty and "重試" in dialog.status.text()
    monkeypatch.setattr(materials, "_write_json_atomic", write)
    dialog.save_import()
    assert not dialog.import_dirty and dialog.cards.count() == 1
    dialog.kind.setCurrentIndex(1)
    dialog.copy_prompt()
    assert "seat taken" in QApplication.clipboard().text()
    dialog.import_text.setPlainText(json.dumps(lesson))
    dialog.validate_import()
    dialog.save_import()
    assert dialog.lines.count() == 2
    dialog.reject()
    reopened = LearningDialog(directory, course, unit)
    assert reopened.lines.count() == 2 and reopened.cards.count() == 1
    reopened.reject()
    other = LearningDialog(directory, course, units["units"][0])
    assert other.lines.count() == 0
    other.reject()


def test_audio_cache_failure_retry_and_settings_identity(tmp_path, monkeypatch):
    class Communicate:
        def __init__(self, *a, **kw):
            assert kw["boundary"] == "WordBoundary"

        async def stream(self):
            yield {"type": "audio", "data": b"test-audio-not-real"}
            yield {"type": "WordBoundary", "offset": 1000000, "duration": 2000000}

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Communicate))
    root = tmp_path / "audio"
    args = (root, "Hello", "en-US-AriaNeural", "+0%")
    audio, timings = asyncio.run(speech.synthesize(*args))
    assert timings == [{"start": 100.0, "end": 300.0}]
    assert speech.cached_audio(*args)
    assert speech.cached_audio(root, "Changed", args[2], args[3]) is None
    assert speech.cached_audio(root, args[1], args[2], "-20%") is None
    audio.write_bytes(b"corrupt")
    assert speech.cached_audio(*args) is None
    asyncio.run(speech.synthesize(*args))
    assert speech.cached_audio(*args)


def test_playback_controls_timestamp_mapping_and_invalidation(app, prepared, monkeypatch):
    directory, course, _, unit, vocab, lesson = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    materials.save_content(directory, course, unit, "lesson", lesson)
    dialog = LearningDialog(directory, course, unit)
    calls = []
    monkeypatch.setattr(dialog, "_cached", lambda text: (directory / "stub.mp3", [{"start": 100, "end": 400}]))
    monkeypatch.setattr(dialog.player, "play", lambda: calls.append("play"))
    monkeypatch.setattr(dialog.player, "setSource", lambda url: calls.append(url))
    monkeypatch.setattr(dialog.player, "pause", lambda: calls.append("pause"))
    dialog.play_lesson()
    assert dialog.track == 0
    dialog._position(200)
    assert dialog.lines.currentRow() == 0
    dialog._position(500)
    assert dialog.lines.currentRow() == -1
    dialog._media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    dialog._position(200)
    assert dialog.track == 1 and dialog.lines.currentRow() == 1
    dialog.replay()
    assert dialog.track == 0
    dialog.resume()
    assert calls.count("play") == 4
    dialog.voice.setText("en-GB-SoniaNeural")
    assert not dialog.queue and dialog.track == -1
    assert calls[-1] == QUrl()
    dialog.play_card("text")
    assert dialog.queue[0][1] is None
    dialog.stop()
    dialog.play_lesson()
    dialog._generated(1, None)
    assert not dialog.queue and "TTS 失敗" in dialog.status.text()
    dialog.play_lesson()
    storage.save_course(directory, {**course, "goal": "Changed"})
    dialog.resume()
    assert not dialog.queue
    dialog.reject()


def test_tts_partial_failure_keeps_text_and_allows_retry(tmp_path, monkeypatch):
    class Failing:
        def __init__(self, *a, **kw):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"partial"}
            raise OSError("network lost")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Failing))
    args = (tmp_path, "Hello", "en-US-AriaNeural", "+0%")
    with pytest.raises(OSError):
        asyncio.run(speech.synthesize(*args))
    assert speech.cached_audio(*args) is None
    assert not list(tmp_path.iterdir())


def test_draft_cancel_non_utf8_and_missing_timing(app, prepared, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    directory, course, _, unit, vocab, lesson = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    materials.save_content(directory, course, unit, "lesson", lesson)
    dialog = LearningDialog(directory, course, unit)
    dialog.show()
    dialog.import_text.setPlainText(json.dumps(vocab))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    dialog.reject()
    assert dialog.isVisible() and dialog.import_dirty
    invalid = tmp_path / "invalid.json"
    invalid.write_bytes(b"\xff")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(invalid), ""))
    previous = dialog.import_text.toPlainText()
    dialog.load_json()
    assert dialog.import_text.toPlainText() == previous
    assert "UTF-8" in dialog.status.text()
    monkeypatch.setattr(dialog, "_cached", lambda text: (directory / "stub.mp3", []))
    monkeypatch.setattr(dialog.player, "play", lambda: None)
    monkeypatch.setattr(dialog.player, "setSource", lambda *a: None)
    dialog.play_lesson()
    dialog._position(200)
    assert dialog.lines.currentRow() == -1
    assert "未提供可靠時間戳" in dialog.status.text()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    dialog.reject()


def test_qt_decoder_play_pause_seek_stop_with_synthetic_wav(app, prepared, tmp_path, monkeypatch):
    """Real Qt decoder/playback smoke; synthetic silence is explicitly NOT a TTS test."""
    directory, course, _, unit, vocab, lesson = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    materials.save_content(directory, course, unit, "lesson", lesson)
    audio = tmp_path / "synthetic-silence.wav"
    with wave.open(str(audio), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(b"\x00\x00" * 16000 * 3)
    dialog = LearningDialog(directory, course, unit)
    dialog.output.setMuted(True)
    monkeypatch.setattr(dialog, "_cached", lambda text: (audio, [{"start": 0, "end": 3000}]))
    dialog.play_lesson()
    for _ in range(30):
        QTest.qWait(100)
        if dialog.player.position() > 0:
            break
    assert dialog.player.error() == QMediaPlayer.Error.NoError
    assert dialog.player.duration() >= 2900
    assert dialog.player.position() > 0
    dialog.player.pause()
    assert dialog.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    dialog.player.setPosition(1000)
    assert dialog.player.position() == 1000
    dialog.resume()
    assert dialog.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    dialog.replay()
    assert dialog.track == 0
    dialog.stop()
    assert dialog.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
    assert dialog.player.source().isEmpty()
    dialog.reject()


def test_workspace_opens_only_selected_unit_and_empty_course_disables_action(app, prepared, monkeypatch):
    from lingua.ui import CourseWorkspace

    directory, course, units, unit, _, _ = prepared
    opened = []
    monkeypatch.setattr(LearningDialog, "exec", lambda dialog: opened.append(dialog.unit["id"]))
    workspace = CourseWorkspace(directory)
    workspace.tree.setCurrentItem(workspace._tree_items[36])
    workspace.learning_button.click()
    workspace.tree.setCurrentItem(workspace._tree_items[0])
    workspace.learning_button.click()
    assert opened == [unit["id"], units["units"][0]["id"]]
    storage.save_units(directory, {"units": []})
    empty = CourseWorkspace(directory)
    assert not empty.learning_button.isEnabled()


def test_qprocess_worker_handoff_with_existing_synthetic_cache(app, prepared, monkeypatch):
    """Exercise real QProcess stdin/finish/cache handoff without online TTS."""
    directory, course, _, unit, vocab, _ = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    dialog = LearningDialog(directory, course, unit)
    text = vocab["cards"][0]["text"]
    root = directory / "audio"
    root.mkdir()
    voice, rate = dialog.voice.text(), dialog.rate.text()
    key = speech.audio_key(text, voice, rate)
    audio = root / f"{key}.mp3"
    with wave.open(str(audio), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(b"\x00\x00" * 16000)
    storage._write_json_atomic(root / f"{key}.json", {"request": [text, voice, rate], "sha256": hashlib.sha256(audio.read_bytes()).hexdigest(), "boundaries": []})
    lookup = dialog._cached
    calls = []

    def first_miss(value):
        calls.append(value)
        return None if len(calls) == 1 else lookup(value)

    monkeypatch.setattr(dialog, "_cached", first_miss)
    dialog.output.setMuted(True)
    dialog.play_card("text")
    for _ in range(50):
        QTest.qWait(100)
        if dialog.track >= 0:
            break
    assert dialog.track == 0, dialog.status.text()
    assert Path(dialog.player.source().toLocalFile()) == audio
    assert materials.load_material(directory, course, unit)["vocabulary"] == vocab
    dialog.reject()


def test_stage_navigation_keeps_independent_drafts_and_close_cancel(app, prepared, monkeypatch):
    directory, course, _, unit, vocab, _ = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    original = materials.material_path(directory, unit["id"]).read_bytes()
    dialog = LearningDialog(directory, course, unit)
    dialog.show()
    assert dialog.kind.currentData() == "lesson"
    lesson_draft = '{"incomplete":'
    dialog.import_text.setPlainText(lesson_draft)
    dialog.extra.setPlainText("教材要求")
    dialog.kind.setCurrentIndex(0)
    assert json.loads(dialog.import_text.toPlainText()) == vocab
    dialog.import_text.setPlainText("詞彙草稿")
    dialog.extra.setPlainText("詞彙要求")
    dialog.kind.setCurrentIndex(1)
    assert dialog.import_text.toPlainText() == lesson_draft
    assert dialog.extra.toPlainText() == "教材要求"
    assert not dialog.save.isEnabled()
    dialog.kind.setCurrentIndex(2)
    assert dialog.audio_panel.isVisible()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    dialog.reject()
    assert dialog.isVisible()
    dialog.kind.setCurrentIndex(0)
    assert dialog.import_text.toPlainText() == "詞彙草稿"
    assert dialog.extra.toPlainText() == "詞彙要求"
    assert not dialog.audio_panel.isVisible()
    assert materials.material_path(directory, unit["id"]).read_bytes() == original
    assert storage.load_course(directory)[0] == course
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    dialog.reject()


def test_saved_stages_resume_and_next_requires_successful_save(app, prepared, monkeypatch):
    directory, course, _, unit, vocab, lesson = prepared
    dialog = LearningDialog(directory, course, unit)
    assert dialog.kind.currentIndex() == 0 and not dialog.next.isEnabled()
    assert not dialog.kind.model().item(1).isEnabled()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    dialog.import_text.setPlainText(json.dumps(vocab))
    dialog.validate_import()
    dialog.save_import()
    assert dialog.next.isEnabled()
    dialog.next.click()
    assert dialog.kind.currentData() == "lesson" and not dialog.next.isEnabled()
    dialog.import_text.setPlainText(json.dumps(lesson))
    dialog.validate_import()
    dialog.save_import()
    dialog.next.click()
    assert dialog.kind.currentData() == "study"
    dialog.reject()
    reopened = LearningDialog(directory, course, unit)
    assert reopened.kind.currentData() == "study"
    reopened.kind.setCurrentIndex(1)
    assert json.loads(reopened.import_text.toPlainText()) == lesson
    assert reopened.next.isEnabled()
    reopened.kind.setCurrentIndex(0)
    assert json.loads(reopened.import_text.toPlainText()) == vocab
    reopened.reject()


def test_changed_vocabulary_invalidates_validated_lesson_draft_not_its_text(app, prepared, monkeypatch):
    directory, course, _, unit, vocab, lesson = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    dialog = LearningDialog(directory, course, unit)
    draft = json.dumps(lesson)
    dialog.import_text.setPlainText(draft)
    dialog.validate_import()
    assert dialog.save.isEnabled()
    dialog.kind.setCurrentIndex(0)
    changed = deepcopy(vocab)
    changed["cards"][0]["text"] = "updated phrase"
    dialog.import_text.setPlainText(json.dumps(changed))
    dialog.validate_import()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    dialog.save_import()
    dialog.next.click()
    assert dialog.import_text.toPlainText() == draft
    assert not dialog.save.isEnabled() and dialog.candidate is None
    assert "updated phrase" in dialog.prompt.toPlainText()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    dialog.reject()


def test_extra_only_close_protection_and_failed_save_survive_stage_switch(app, prepared, monkeypatch):
    directory, course, _, unit, vocab, lesson = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    original = materials.material_path(directory, unit["id"]).read_bytes()
    dialog = LearningDialog(directory, course, unit)
    dialog.show()
    dialog.extra.setPlainText("當次補充要求")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    dialog.close()
    assert dialog.isVisible() and dialog.extra.toPlainText() == "當次補充要求"
    raw = json.dumps(lesson)
    dialog.import_text.setPlainText(raw)
    dialog.validate_import()
    write = materials._write_json_atomic
    monkeypatch.setattr(materials, "_write_json_atomic", lambda *a: (_ for _ in ()).throw(OSError("full disk")))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    dialog.save_import()
    assert "保存失敗" in dialog.status.text()
    dialog.kind.setCurrentIndex(0)
    dialog.kind.setCurrentIndex(1)
    assert dialog.import_text.toPlainText() == raw
    assert dialog.extra.toPlainText() == "當次補充要求"
    assert dialog.candidate == lesson and dialog.save.isEnabled()
    assert materials.material_path(directory, unit["id"]).read_bytes() == original
    monkeypatch.setattr(materials, "_write_json_atomic", write)
    dialog.save_import()
    assert dialog.next.isEnabled() and not dialog.import_dirty and not dialog.extra_dirty
    dialog.reject()


def test_detailed_preview_is_on_demand_and_keeps_candidate(app, prepared, monkeypatch):
    from PySide6.QtWidgets import QDialog, QPlainTextEdit

    directory, course, _, unit, vocab, _ = prepared
    dialog = LearningDialog(directory, course, unit)
    dialog.import_text.setPlainText(json.dumps(vocab))
    dialog.validate_import()
    def inspect(preview_dialog):
        editor = preview_dialog.findChild(QPlainTextEdit)
        assert editor.isReadOnly()
        assert json.loads(editor.toPlainText()) == vocab
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", inspect)
    dialog.details.click()
    assert dialog.candidate == vocab and dialog.save.isEnabled()
    assert not materials.material_path(directory, unit["id"]).exists()
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    dialog.reject()


@pytest.mark.parametrize("size", [(700, 500), (900, 600), (1280, 720), (1440, 900)])
@pytest.mark.parametrize("zoom", [1, 2])
def test_staged_layout_controls_reachable_after_settling(app, prepared, size, zoom):
    directory, course, _, unit, vocab, _ = prepared
    materials.save_content(directory, course, unit, "vocabulary", vocab)
    original_font = QFont(app.font())
    font = QFont(original_font)
    font.setPointSizeF((original_font.pointSizeF() if original_font.pointSizeF() > 0 else 10) * zoom)
    app.setFont(font)
    dialog = LearningDialog(directory, course, unit)
    def reachable(button):
        areas = []
        parent = button.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                areas.append(parent)
            parent = parent.parentWidget()
        for _ in range(2):
            for area in reversed(areas):
                area.ensureWidgetVisible(button, 0, 0)
            app.processEvents()
        assert button.width() >= button.minimumSizeHint().width()
        assert button.height() >= button.minimumSizeHint().height()
        for area in areas:
            rect = QRect(button.mapTo(area.viewport(), QPoint()), button.size())
            assert area.viewport().rect().contains(rect), button.text()

    try:
        dialog.resize(*size)
        dialog.show()
        for _ in range(5):
            QTest.qWait(20)
        assert dialog.size().width() == size[0] and dialog.size().height() == size[1]
        for stage in (0, 1):
            dialog.kind.setCurrentIndex(stage)
            for _ in range(5):
                QTest.qWait(20)
            assert not dialog.audio_panel.isVisible()
            assert dialog.exchange.orientation() == Qt.Orientation.Horizontal
            assert dialog.prompt.height() >= QFontMetrics(app.font()).height() * 3
            assert dialog.import_text.height() >= QFontMetrics(app.font()).height() * 3
            for button in dialog.exchange.findChildren(QPushButton):
                reachable(button)
        dialog.kind.setCurrentIndex(2)
        for _ in range(5):
            QTest.qWait(20)
        assert dialog.audio_panel.isVisible()
        for button in dialog.study.findChildren(QPushButton):
            if button.isVisible():
                reachable(button)
    finally:
        dialog.reject()
        app.setFont(original_font)
