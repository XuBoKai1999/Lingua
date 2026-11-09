"""One selected Unit: external AI exchange, cards, reading and real audio."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QSettings, QSignalBlocker, Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSplitter, QTabWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from lingua.materials import (
    build_unit_prompt, current_source, load_material, save_content, validate_content,
)
from lingua.speech import audio_key, cached_audio


class LearningDialog(QDialog):
    def __init__(self, course_dir: Path, course: dict, unit: dict, parent=None):
        super().__init__(parent)
        self.course_dir, self.course, self.unit = course_dir, deepcopy(course), deepcopy(unit)
        self.record = {"source": {"course": self.course, "unit": self.unit}, "vocabulary": None, "lesson": None}
        self.stale = False
        self.load_error = ""
        self.candidate = None
        self.import_dirty = False
        self.extra_dirty = False
        self.drafts = {}
        self._active_kind = None
        self.queue = []
        self.track = -1
        self.boundaries = []
        self.settings = QSettings("Lingua", "Lingua")
        self.setWindowTitle(f"製作與學習 {unit['id']} — {unit['scenario']}")
        screen = self.screen().availableGeometry()
        self.resize(min(1100, int(screen.width() * .9)), min(850, int(screen.height() * .9)))
        outer = QVBoxLayout(self)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.kind = QComboBox()
        self.kind.addItem("1 詞彙製作", "vocabulary")
        self.kind.addItem("2 教材製作", "lesson")
        self.kind.addItem("3 語音／學習", "study")
        layout.addWidget(self.kind)
        layout.addWidget(self.status)
        layout.addWidget(self._build_exchange(), 1)
        study = self.study = QWidget()
        study_layout = QVBoxLayout(study)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_cards(), "詞彙學習")
        self.tabs.addTab(self._build_reader(), "教材收聽")
        study_layout.addWidget(self.tabs, 1)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        self.output.setVolume(.8)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(lambda duration: self.progress.setMaximum(max(0, duration)))
        self.player.mediaStatusChanged.connect(self._media_status)
        self.player.errorOccurred.connect(lambda *_: self.status.setText("播放失敗：" + self.player.errorString()))
        self.process = QProcess(self)
        self.process.finished.connect(self._generated)
        self.process.errorOccurred.connect(lambda *_: self.status.setText("TTS 程序失敗，可重試：" + self.process.errorString()))
        self.cards.currentRowChanged.connect(self.stop)
        self.tabs.currentChanged.connect(self.stop)
        self.audio_panel = self._build_audio()
        study_layout.addWidget(self.audio_panel)
        layout.addWidget(study, 1)
        study.hide()
        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.body.setWidget(content)
        outer.addWidget(self.body, 1)
        close = QPushButton("關閉")
        close.clicked.connect(self.reject)
        outer.addWidget(close)
        try:
            self.record = load_material(course_dir, course, unit)
            self.status.setText("只製作目前 Unit；先保存詞彙，再製作教材。")
        except (OSError, ValueError) as error:
            self.stale = True
            self.load_error = str(error)
            self.status.setText(str(error))
        self._refresh_study()
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()
        if self.record["lesson"]:
            self.kind.setCurrentIndex(2)
        elif self.record["vocabulary"]:
            self.kind.setCurrentIndex(1)

    def _build_exchange(self):
        self.exchange = QSplitter(Qt.Orientation.Horizontal)
        left, right = QWidget(), QWidget()
        left_layout, right_layout = QVBoxLayout(left), QVBoxLayout(right)
        title = QLabel("Prompt → 複製到外部 AI")
        title.setWordWrap(True)
        left_layout.addWidget(title)
        extra_toggle = QPushButton("當次要求（選填）")
        extra_toggle.setCheckable(True)
        left_layout.addWidget(extra_toggle)
        self.extra = QPlainTextEdit()
        self.extra.setPlaceholderText("只加入本次 Prompt，不修改長期規範")
        self.extra.hide()
        extra_toggle.toggled.connect(self.extra.setVisible)
        self.extra.textChanged.connect(self._extra_changed)
        left_layout.addWidget(self.extra)
        self.prompt = QPlainTextEdit()
        self.prompt.setReadOnly(True)
        left_layout.addWidget(self.prompt, 1)
        actions = QHBoxLayout()
        for text, callback in (("更新 Prompt", self.refresh_prompt), ("複製 Prompt", self.copy_prompt)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        left_layout.insertLayout(2, actions)
        title = QLabel("AI 結果 → 貼回完整 JSON")
        title.setWordWrap(True)
        right_layout.addWidget(title)
        self.import_text = QPlainTextEdit()
        self.import_text.textChanged.connect(self._import_changed)
        right_layout.addWidget(self.import_text, 1)
        load = QPushButton("載入 JSON")
        load.clicked.connect(self.load_json)
        right_layout.addWidget(load)
        actions = QHBoxLayout()
        validate = QPushButton("驗證結果")
        validate.clicked.connect(self.validate_import)
        actions.addWidget(validate)
        self.details = QPushButton("詳細預覽")
        self.details.setEnabled(False)
        self.details.clicked.connect(self._show_preview)
        actions.addWidget(self.details)
        right_layout.addLayout(actions)
        self.save = QPushButton("確認保存")
        self.save.setEnabled(False)
        self.save.clicked.connect(self.save_import)
        right_layout.addWidget(self.save)
        self.next = QPushButton()
        self.next.clicked.connect(lambda: self.kind.setCurrentIndex(self.kind.currentIndex() + 1))
        right_layout.addWidget(self.next)
        right_layout.removeWidget(self.import_text)
        right_layout.addWidget(self.import_text, 1)
        for pane in (left, right):
            for button in pane.findChildren(QPushButton):
                button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(pane)
            self.exchange.addWidget(scroll)
        self.exchange.setStretchFactor(0, 1)
        self.exchange.setStretchFactor(1, 1)
        self.exchange.setSizes([1, 1])
        self.exchange.setChildrenCollapsible(False)
        return self.exchange

    def _remember_draft(self):
        if self._active_kind is None:
            return
        self.drafts[self._active_kind] = {
            "text": self.import_text.toPlainText(), "extra": self.extra.toPlainText(),
            "candidate": self.candidate, "dirty": self.import_dirty, "extra_dirty": self.extra_dirty,
        }

    def _kind_changed(self):
        self._remember_draft()
        self.stop()
        study = self.kind.currentData() == "study"
        self.exchange.setVisible(not study)
        self.study.setVisible(study)
        if study:
            self.status.setText("選詞彙卡或教材收聽；可返回前兩步查看／修改已保存內容，草稿仍保留。")
            return
        self._active_kind = self.kind.currentData()
        draft = self.drafts.get(self._active_kind)
        if draft is None:
            saved = self.record[self._active_kind]
            draft = {"text": json.dumps(saved, ensure_ascii=False, indent=2) if saved else "", "extra": "", "candidate": saved, "dirty": False, "extra_dirty": False}
        blockers = [QSignalBlocker(self.import_text), QSignalBlocker(self.extra)]
        self.import_text.setPlainText(draft["text"])
        self.extra.setPlainText(draft["extra"])
        del blockers
        self.candidate, self.import_dirty, self.extra_dirty = draft["candidate"], draft["dirty"], draft["extra_dirty"]
        self.save.setEnabled(self.candidate is not None and self.import_dirty)
        self.details.setEnabled(self.candidate is not None)
        self._update_stages()
        self.status.setText("已有保存內容，可查看或接續下一步；修改後請重新驗證。" if self.record[self._active_kind] else "左側複製 Prompt → 右側貼回結果 → 驗證 → 確認保存 → 下一步。")
        if self.stale:
            self.status.setText(self.load_error)
        self.refresh_prompt()

    def _update_stages(self):
        has_vocab = self.record["vocabulary"] is not None
        self.kind.model().item(1).setEnabled(has_vocab)
        self.kind.model().item(2).setEnabled(has_vocab)
        self.next.setText("下一步：教材" if self._active_kind == "vocabulary" else "下一步：學習")
        self.next.setEnabled(self.record[self._active_kind] is not None)

    def _extra_changed(self):
        self.extra_dirty = True

    def _show_preview(self):
        if self.candidate is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("完整 JSON 預覽（尚未保存的變更仍需確認）")
        layout = QVBoxLayout(dialog)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(json.dumps(self.candidate, ensure_ascii=False, indent=2))
        layout.addWidget(preview)
        close = QPushButton("返回")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.resize(self.size())
        dialog.exec()

    def _import_changed(self):
        self.candidate = None
        self.save.setEnabled(False)
        self.details.setEnabled(False)
        saved = self.record[self._active_kind]
        baseline = json.dumps(saved, ensure_ascii=False, indent=2) if saved else ""
        self.import_dirty = self.import_text.toPlainText() != baseline

    def refresh_prompt(self):
        try:
            prompt = build_unit_prompt(self.course, self.unit, self._active_kind, self.record["vocabulary"], self.extra.toPlainText())
        except ValueError as error:
            self.prompt.clear()
            self.status.setText(str(error))
            return False
        self.prompt.setPlainText(prompt)
        return True

    def copy_prompt(self):
        if self.refresh_prompt():
            QApplication.clipboard().setText(self.prompt.toPlainText())
            self.status.setText("已複製，請交給外部 AI；貼回後驗證並確認。")

    def load_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "載入單元 JSON", str(self.course_dir), "JSON (*.json)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            self.status.setText("無法讀取 UTF-8 JSON：" + str(error))
            return
        if self.import_dirty and QMessageBox.question(self, "取代草稿", "放棄目前貼上的 JSON 草稿？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.import_text.setPlainText(text)

    def validate_import(self):
        try:
            data = json.loads(self.import_text.toPlainText())
            validate_content(data, self.unit["id"], self._active_kind)
            self.candidate = data
            self.details.setEnabled(True)
            self.save.setEnabled(True)
            self.status.setText(f"驗證成功，{len(data.get('cards', data.get('lines', [])))} 項，尚未保存。")
        except (ValueError, TypeError) as error:
            self.candidate = None
            self.save.setEnabled(False)
            self.details.setEnabled(False)
            self.status.setText("JSON 無效：" + str(error))

    def save_import(self):
        if self.candidate is None:
            return
        warning = "確定保存並取代本單元詞彙？詞彙改變會使教材失效，須重新製作。" if self._active_kind == "vocabulary" else "確定保存並取代本單元教材？"
        if self.stale:
            warning += " 舊規範的製作資料將由新資料取代。"
        if QMessageBox.question(self, "保存單元", warning, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            record = save_content(self.course_dir, self.course, self.unit, self._active_kind, self.candidate, reset=self.stale)
        except (OSError, ValueError) as error:
            self.status.setText("保存失敗，草稿保留可重試：" + str(error))
            return
        self.stop()
        if self._active_kind == "vocabulary" and self.record["vocabulary"] != record["vocabulary"]:
            draft = self.drafts.get("lesson")
            if draft and (draft["dirty"] or draft["extra_dirty"]):
                draft.update(candidate=None, dirty=True)
            else:
                self.drafts.pop("lesson", None)
        self.record, self.stale = record, False
        self.import_dirty = False
        self.extra_dirty = False
        self.save.setEnabled(False)
        self._update_stages()
        self._refresh_study()
        self.status.setText("已保存此階段。可按「下一步」，或留在此處查看／修改。")

    def _build_cards(self):
        splitter = QSplitter()
        self.cards = QListWidget()
        splitter.addWidget(self.cards)
        right = QWidget()
        layout = QVBoxLayout(right)
        self.card = QTextBrowser()
        layout.addWidget(self.card)
        for text, field in (("播放詞／片語", "text"), ("播放例句", "example")):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, f=field: self.play_card(f))
            layout.addWidget(button)
        splitter.addWidget(right)
        self.cards.currentRowChanged.connect(self._show_card)
        splitter.setStretchFactor(1, 2)
        return splitter

    def _build_reader(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.lines = QListWidget()
        self.lines.setWordWrap(True)
        layout.addWidget(self.lines, 1)
        self.read = QPushButton("產生／播放本單元教材")
        self.read.clicked.connect(self.play_lesson)
        layout.addWidget(self.read)
        return page

    def _refresh_study(self):
        self.cards.clear()
        self.card.clear()
        for card in (self.record["vocabulary"] or {}).get("cards", []):
            self.cards.addItem(card["text"])
        if self.cards.count():
            self.cards.setCurrentRow(0)
        self.lines.clear()
        for line in (self.record["lesson"] or {}).get("lines", []):
            self.lines.addItem(f"{line['speaker']}: {line['text']}\n{line['translation_zh']}")
        self.read.setEnabled(bool(self.record["lesson"]))

    def _show_card(self, index):
        if index >= 0 and self.record["vocabulary"]:
            card = self.record["vocabulary"]["cards"][index]
            self.card.setPlainText(f"{card['text']} [{card['pos']}]\n\n{card['meaning_zh']}\n\n{card['example']}\n{card['example_zh']}")

    def _build_audio(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        notice = QLabel("語音生成需連網至 Microsoft Edge TTS，傳送朗讀文字；已產生音檔可離線重播。語音須與目標語言相符。")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        form = QFormLayout()
        self.voice = QLineEdit(str(self.settings.value("speech/voice", "en-US-AriaNeural")))
        self.rate = QLineEdit(str(self.settings.value("speech/rate", "+0%")))
        self.voice.textChanged.connect(self.stop)
        self.rate.textChanged.connect(self.stop)
        form.addRow("Edge 語音名稱", self.voice)
        form.addRow("語速", self.rate)
        layout.addLayout(form)
        controls = QHBoxLayout()
        for text, callback in (("播放／繼續", self.resume), ("暫停", self.player.pause), ("停止／取消生成", self.stop), ("重播", self.replay)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 0)
        self.progress.sliderMoved.connect(self.player.setPosition)
        layout.addWidget(self.progress)
        self.time = QLabel("進度為目前音檔／目前行；逐行播放可能有短暫間隔。")
        layout.addWidget(self.time)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def play_card(self, field):
        index = self.cards.currentRow()
        if index >= 0 and self.record["vocabulary"]:
            self.start_audio([(self.record["vocabulary"]["cards"][index][field], None)])

    def play_lesson(self):
        if self.record["lesson"]:
            self.start_audio([(line["text"], i) for i, line in enumerate(self.record["lesson"]["lines"])])

    def _check_source(self):
        if current_source(self.course_dir, self.unit["id"]) != self.record["source"] or load_material(self.course_dir, self.course, self.unit) != self.record:
            raise ValueError("單元製作資料已改變，請關閉並重新開啟；不播放舊音檔。")

    def start_audio(self, queue):
        self.stop()
        try:
            self._check_source()
            for text, _ in queue:
                audio_key(text, self.voice.text().strip(), self.rate.text().strip())
        except (ValueError, OSError) as error:
            self.status.setText(str(error))
            return
        self.queue = queue
        self.settings.setValue("speech/voice", self.voice.text().strip())
        self.settings.setValue("speech/rate", self.rate.text().strip())
        if all(self._cached(text) for text, _ in queue):
            self._play_track(0)
            return
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
        env.insert("PYTHONIOENCODING", "utf-8")
        self.process.setProcessEnvironment(env)
        self.process.start(sys.executable, ["-m", "lingua.speech"])
        self.process.write(json.dumps({"root": str(self.course_dir / "audio"), "texts": [text for text, _ in queue], "voice": self.voice.text().strip(), "rate": self.rate.text().strip()}, ensure_ascii=False).encode("utf-8"))
        self.process.closeWriteChannel()
        self.status.setText("正在生成目前選擇的音訊；文字已保存，失敗可重試。")

    def _cached(self, text):
        return cached_audio(self.course_dir / "audio", text, self.voice.text().strip(), self.rate.text().strip())

    def _generated(self, code, _status):
        if not self.queue:
            return
        if code != 0:
            self.status.setText("TTS 失敗，請確認網路／語音後重試：" + bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")[-1000:])
            self.queue = []
            return
        self._play_track(0)

    def _play_track(self, index):
        try:
            self._check_source()
            audio = self._cached(self.queue[index][0])
            if audio is None:
                raise ValueError("音檔不符目前文字／設定，請重新產生")
        except (OSError, ValueError) as error:
            self.stop()
            self.status.setText(str(error))
            return
        self.track = index
        path, self.boundaries = audio
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.status.setText("使用真實 WordBoundary 時間戳標示目前行。" if self.boundaries else "服務未提供可靠時間戳：可收聽，但不標示目前行。")
        self.player.play()

    def _position(self, position):
        if not self.progress.isSliderDown():
            self.progress.setValue(position)
        self.time.setText(f"音檔 {self.track + 1}/{len(self.queue)}：{position / 1000:.1f} / {self.player.duration() / 1000:.1f} 秒（進度條控制目前音檔）")
        line = self.queue[self.track][1] if 0 <= self.track < len(self.queue) else None
        speaking = any(boundary["start"] <= position <= boundary["end"] for boundary in self.boundaries)
        if line is not None and speaking:
            self.lines.setCurrentRow(line)
            self.lines.scrollToItem(self.lines.item(line))
        else:
            self.lines.setCurrentRow(-1)

    def _media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.track + 1 < len(self.queue):
            self._play_track(self.track + 1)

    def resume(self):
        if self.track >= 0:
            try:
                self._check_source()
            except (OSError, ValueError) as error:
                self.stop()
                self.status.setText(str(error))
                return
            self.player.play()

    def replay(self):
        if self.queue and self.process.state() == QProcess.ProcessState.NotRunning:
            self._play_track(0)

    def stop(self):
        self.queue = []
        self.track = -1
        self.boundaries = []
        self.player.stop()
        self.player.setSource(QUrl())
        self.lines.setCurrentRow(-1)
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)

    def reject(self):
        self._remember_draft()
        if any(draft["dirty"] or draft["extra_dirty"] for draft in self.drafts.values()) and QMessageBox.question(self, "未保存草稿", "放棄各階段尚未保存的 JSON／當次要求並關閉？", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Discard:
            return
        self.stop()
        super().reject()
