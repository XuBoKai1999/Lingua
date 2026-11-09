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
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QMessageBox
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
    dialog.kind.setCurrentText("lesson")
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
