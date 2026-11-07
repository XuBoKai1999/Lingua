from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
)

from lingua.storage import load_course
from lingua.ui import CourseWorkspace, MainWindow, PromptDialog


@pytest.fixture(scope="session")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _create_from_current_form(window: MainWindow, *, blank: bool = False) -> None:
    window.findChild(QLineEdit, "course_name").setText("English - GUI 測試")
    window.findChild(QLineEdit, "course_language").setText("English")
    window.findChild(QPlainTextEdit, "course_goal").setPlainText("能在旅行時完成基本交流")
    window.findChild(QLineEdit, "course_default_level").setText("A2")
    if blank:
        window.findChild(QRadioButton, "blank_source").click()
    window.findChild(QPushButton, "save_course_button").click()


def test_home_and_default_template_creation(app, tmp_path):
    window = MainWindow(library_root=tmp_path)
    window.show()
    assert window.findChild(QPushButton, "browse_courses_button").text() == "進入教材"
    window.findChild(QPushButton, "create_course_button").click()
    assert window.current_page == "create"
    assert "44" in window.findChild(QLabel, "unit_count_preview").text()

    _create_from_current_form(window)
    assert window.current_page == "workspace"
    course_dir = next(tmp_path.iterdir())
    assert len(load_course(course_dir)[1]["units"]) == 44
    assert isinstance(window.centralWidget(), CourseWorkspace)
    assert len(window.centralWidget().units["units"]) == 44
    window.close()


def test_blank_course_and_browser_reopen(app, tmp_path):
    window = MainWindow(library_root=tmp_path)
    window.findChild(QPushButton, "create_course_button").click()
    _create_from_current_form(window, blank=True)
    course_dir = next(tmp_path.iterdir())
    assert load_course(course_dir)[1] == {"units": []}

    window.go_home()
    window.findChild(QPushButton, "browse_courses_button").click()
    courses = window.findChild(QListWidget, "course_list")
    assert courses.count() == 1
    courses.setCurrentRow(0)
    window.findChild(QPushButton, "open_course_button").click()
    assert window.current_page == "workspace"
    assert window.current_argument == course_dir
    window.close()


def test_corrupt_course_is_visible_without_crashing(app, tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "course.json").write_text("{bad", encoding="utf-8")
    (broken / "units.json").write_text('{"units": []}', encoding="utf-8")
    window = MainWindow(library_root=tmp_path)
    window.findChild(QPushButton, "browse_courses_button").click()
    courses = window.findChild(QListWidget, "course_list")
    assert courses.count() == 1
    courses.setCurrentRow(0)
    assert "無法讀取" in courses.currentItem().text()
    assert not window.findChild(QPushButton, "open_course_button").isEnabled()
    assert "有效 JSON" in window.findChild(QLabel, "browser_status").text()
    assert courses.currentItem().data(Qt.ItemDataRole.UserRole + 1)
    window.close()


def test_edit_u037_save_and_reopen(app, tmp_path):
    window = MainWindow(library_root=tmp_path)
    window.findChild(QPushButton, "create_course_button").click()
    _create_from_current_form(window)
    workspace = window.centralWidget()
    assert isinstance(workspace, CourseWorkspace)
    workspace.tree.setCurrentItem(workspace._tree_items[36])
    assert workspace.unit_id.text() == "U037"
    assert workspace.effective.text() == "A2"

    original_second = workspace.units["units"][37].copy()
    workspace.unit_description.setPlainText("已由 GUI 修改的旅行社交目標")
    workspace.unit_level.setText("B1")
    assert workspace.dirty
    workspace.save_button.click()
    course_dir = window.current_argument
    saved = load_course(course_dir)[1]
    assert saved["units"][36]["description"] == "已由 GUI 修改的旅行社交目標"
    assert saved["units"][36]["level"] == "B1"
    assert saved["units"][37] == original_second

    window.close()
    reopened = MainWindow(library_root=tmp_path)
    reopened.navigate("workspace", course_dir)
    reopened_workspace = reopened.centralWidget()
    reopened_workspace.tree.setCurrentItem(reopened_workspace._tree_items[36])
    assert reopened_workspace.unit_description.toPlainText() == "已由 GUI 修改的旅行社交目標"
    assert reopened_workspace.effective.text() == "B1"
    reopened.close()


def test_unsaved_navigation_cancel_keeps_editor_and_disk(app, tmp_path, monkeypatch):
    window = MainWindow(library_root=tmp_path)
    window.findChild(QPushButton, "create_course_button").click()
    _create_from_current_form(window)
    workspace = window.centralWidget()
    workspace.tree.setCurrentItem(workspace._tree_items[36])
    original = workspace.unit_description.toPlainText()
    workspace.unit_description.setPlainText("尚未儲存")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )
    workspace.tree.setCurrentItem(workspace._tree_items[37])
    assert workspace.current_index == 36
    assert workspace.unit_description.toPlainText() == "尚未儲存"
    assert load_course(window.current_argument)[1]["units"][36]["description"] == original
    workspace.revert_button.click()
    window.close()


def test_add_move_delete_unit_and_edit_course(app, tmp_path, monkeypatch):
    import lingua.ui as ui

    window = MainWindow(library_root=tmp_path)
    window.findChild(QPushButton, "create_course_button").click()
    _create_from_current_form(window)
    workspace = window.centralWidget()
    new_unit = {
        "id": "U045",
        "stage": 1,
        "context": "測試情境",
        "scenario": "新增與排序",
        "description": "能驗證新增、排序及刪除",
        "level": None,
        "requirements": "",
    }
    monkeypatch.setattr(ui, "_edit_unit_dialog", lambda *args, **kwargs: new_unit)
    workspace.findChild(QPushButton, "add_unit_button").click()
    assert len(load_course(window.current_argument)[1]["units"]) == 45
    workspace.findChild(QPushButton, "move_unit_up_button").click()
    assert load_course(window.current_argument)[1]["units"][43]["id"] == "U045"

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    workspace.findChild(QPushButton, "delete_unit_button").click()
    assert len(load_course(window.current_argument)[1]["units"]) == 44
    assert all(unit["id"] != "U045" for unit in workspace.units["units"])

    changed_course = {**workspace.course, "goal": "已修改的教材目標", "default_level": None}
    def edit_course(_parent, _course, course_dir):
        ui.save_course(course_dir, changed_course)
        return changed_course

    monkeypatch.setattr(ui, "_edit_course_dialog", edit_course)
    workspace.findChild(QPushButton, "edit_course_button").click()
    saved_course = load_course(window.current_argument)[0]
    assert saved_course["goal"] == "已修改的教材目標"
    assert workspace.effective.text() == "未指定"
    window.close()


@pytest.mark.parametrize("leave", ["go_back", "go_home", "close"])
def test_create_draft_leave_cancel_and_discard(app, tmp_path, monkeypatch, leave):
    window = MainWindow(library_root=tmp_path)
    window.show()
    window.navigate("create")
    form = window.centralWidget()
    form.findChild(QLineEdit, "course_name").setText("未完成草稿")
    form.findChild(QPlainTextEdit, "course_goal").setPlainText("保留目標")
    form.findChild(QCheckBox, "stage_2").setChecked(True)
    history = list(window.history)
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    getattr(window, leave)()
    assert window.isVisible()
    assert window.centralWidget() is form
    assert window.history == history
    assert form.findChild(QLineEdit, "course_name").text() == "未完成草稿"
    assert form.findChild(QPlainTextEdit, "course_goal").toPlainText() == "保留目標"
    assert form.findChild(QCheckBox, "stage_2").isChecked()
    assert not list(tmp_path.iterdir())

    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    getattr(window, leave)()
    if leave == "close":
        assert not window.isVisible()
    else:
        assert window.current_page == "home"
        window.close()


def test_create_source_draft_and_successful_save(app, tmp_path, monkeypatch):
    window = MainWindow(library_root=tmp_path)
    window.navigate("create")
    questions = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a: questions.append(a) or QMessageBox.StandardButton.Cancel,
    )
    window.findChild(QRadioButton, "blank_source").click()
    window.go_back()
    assert len(questions) == 1
    assert window.current_page == "create"
    questions.clear()
    _create_from_current_form(window, blank=True)
    assert window.current_page == "workspace"
    assert not questions
    window.close()


def test_create_failed_save_keeps_draft_protection(app, tmp_path, monkeypatch):
    import lingua.ui as ui

    window = MainWindow(library_root=tmp_path)
    window.navigate("create")
    errors = []

    def fail_create(*args, **kwargs):
        raise OSError("simulated create failure")

    monkeypatch.setattr(ui, "create_course", fail_create)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: errors.append(a[2]))
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel)
    _create_from_current_form(window)
    assert errors == ["simulated create failure"]
    window.go_home()
    assert window.current_page == "create"
    assert window.findChild(QLineEdit, "course_name").text() == "English - GUI 測試"
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard)
    window.close()


@pytest.mark.parametrize("retry", [True, False])
def test_course_edit_failed_write_keeps_dialog_for_retry_or_cancel(app, tmp_path, monkeypatch, retry):
    import lingua.ui as ui

    window = MainWindow(library_root=tmp_path)
    window.navigate("create")
    _create_from_current_form(window)
    workspace = window.centralWidget()
    original = workspace.course.copy()
    original_bytes = (workspace.course_dir / "course.json").read_bytes()
    original_save = ui.save_course
    errors = []

    def fail_save(*args):
        raise OSError("simulated write failure")

    monkeypatch.setattr(ui, "save_course", fail_save)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: errors.append(a[2]))

    def exercise_dialog(dialog):
        dialog.show()
        goal = dialog.findChildren(QPlainTextEdit)[0]
        goal.setPlainText("修改後的目標")
        buttons = dialog.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.Save).click()
        assert dialog.isVisible()
        assert goal.toPlainText() == "修改後的目標"
        assert workspace.course == original
        assert (workspace.course_dir / "course.json").read_bytes() == original_bytes
        assert errors == ["simulated write failure"]
        monkeypatch.setattr(ui, "save_course", original_save)
        button = QDialogButtonBox.StandardButton.Save if retry else QDialogButtonBox.StandardButton.Cancel
        buttons.button(button).click()
        assert not dialog.isVisible()
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", exercise_dialog)
    workspace._edit_course()
    expected = {**original, "goal": "修改後的目標"} if retry else original
    assert workspace.course == expected
    assert load_course(workspace.course_dir)[0] == expected
    window.close()


def test_non_utf8_import_preserves_text_validation_and_course(app, tmp_path, monkeypatch):
    window = MainWindow(library_root=tmp_path)
    window.navigate("create")
    _create_from_current_form(window)
    workspace = window.centralWidget()
    original = (workspace.course_dir / "units.json").read_bytes()
    dialog = PromptDialog(workspace.course_dir, workspace.course, workspace.units, window)
    dialog.import_text.setPlainText('{"units": []}')
    dialog._validate_import()
    candidate = dialog.validated_units
    invalid = tmp_path / "not-utf8.json"
    invalid.write_bytes(b'\xff\xfe{"units": []}')
    errors = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(invalid), ""))
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: errors.append(a[2]))
    dialog._load_import_file()
    assert len(errors) == 1 and "UTF-8" in errors[0]
    assert dialog.import_text.toPlainText() == '{"units": []}'
    assert dialog.validated_units is candidate
    assert dialog.import_button.isEnabled()
    assert (workspace.course_dir / "units.json").read_bytes() == original
    dialog.reject()
    window.close()


def test_zoom_is_clamped_and_persisted(app, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(library_root=tmp_path / "library", settings=settings)
    window.set_zoom(5.0)
    assert window.zoom_factor == 2.0
    window.set_zoom(1.5)
    window.close()

    reopened = MainWindow(library_root=tmp_path / "library", settings=settings)
    assert reopened.zoom_factor == 1.5
    assert reopened.findChild(QLabel, "zoom_label").text() == "150%"
    reopened.set_zoom(1.0)
    reopened.close()


def test_prompt_copy_is_fully_expanded(app, tmp_path):
    window = MainWindow(library_root=tmp_path)
    window.findChild(QPushButton, "create_course_button").click()
    _create_from_current_form(window, blank=True)
    workspace = window.centralWidget()
    dialog = PromptDialog(window.current_argument, workspace.course, workspace.units, window)
    dialog.findChild(QPlainTextEdit, "prompt_extra_requirements").setPlainText("偏重旅行社交")
    dialog.findChild(QPushButton, "copy_prompt_button").click()
    copied = QApplication.clipboard().text()
    assert copied.startswith("你是 Lingua 的外語課程設計顧問")
    assert "偏重旅行社交" in copied
    assert "{{" not in copied
    assert "# Course → Units" not in copied
    assert "【供參考的課綱：若沒有則為 null】\nnull" in copied
    dialog.reject()
    window.close()


def test_units_import_requires_validation_and_confirmation(app, tmp_path, monkeypatch):
    window = MainWindow(library_root=tmp_path)
    window.findChild(QPushButton, "create_course_button").click()
    _create_from_current_form(window)
    workspace = window.centralWidget()
    course_dir = window.current_argument
    original = (course_dir / "units.json").read_bytes()
    dialog = PromptDialog(course_dir, workspace.course, workspace.units, window)
    candidate = {
        "units": [
            {
                "id": "U900",
                "stage": None,
                "context": "測試匯入",
                "scenario": "確認流程",
                "description": "能驗證匯入",
                "level": None,
                "requirements": "",
            }
        ]
    }
    dialog.findChild(QPlainTextEdit, "units_import_text").setPlainText(
        json.dumps(candidate, ensure_ascii=False)
    )
    dialog.findChild(QPushButton, "validate_import_button").click()
    assert "1 Units" in dialog.findChild(QLabel, "import_status").text()
    assert dialog.findChild(QPushButton, "import_units_button").isEnabled()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    dialog.findChild(QPushButton, "import_units_button").click()
    assert (course_dir / "units.json").read_bytes() == original

    duplicate = {"units": [candidate["units"][0], candidate["units"][0]]}
    dialog.findChild(QPlainTextEdit, "units_import_text").setPlainText(
        json.dumps(duplicate, ensure_ascii=False)
    )
    dialog.findChild(QPushButton, "validate_import_button").click()
    assert "ID 重複" in dialog.findChild(QLabel, "import_status").text()
    assert not dialog.findChild(QPushButton, "import_units_button").isEnabled()
    assert (course_dir / "units.json").read_bytes() == original

    dialog.findChild(QPlainTextEdit, "units_import_text").setPlainText(
        json.dumps(candidate, ensure_ascii=False)
    )
    dialog.findChild(QPushButton, "validate_import_button").click()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    dialog.findChild(QPushButton, "import_units_button").click()
    assert dialog.imported_units == candidate
    assert load_course(course_dir)[1] == candidate
    window.close()


def test_lesson_preview_is_demo_only_and_scrollable(app, tmp_path):
    window = MainWindow(library_root=tmp_path)
    window.findChild(QPushButton, "create_course_button").click()
    _create_from_current_form(window)
    course_dir = window.current_argument
    course_before = (course_dir / "course.json").read_bytes()
    units_before = (course_dir / "units.json").read_bytes()
    window.resize(900, 600)
    window.set_zoom(2.0)
    window.show()
    app.processEvents()

    tabs = window.findChild(QTabWidget, "workspace_tabs")
    assert tabs.count() == 2
    tabs.setCurrentIndex(1)
    preview = window.findChild(QScrollArea, "lesson_preview_scroll")
    assert preview.widgetResizable()
    assert "僅供 GUI 版面預覽" in preview.findChild(QLabel, "lesson_demo_notice").text()
    assert "尚未開放" in preview.findChild(QLabel, "lesson_unavailable_notice").text()
    assert preview.findChild(QPushButton) is None
    app.processEvents()
    assert preview.viewport().width() > 0
    assert preview.viewport().height() > 0
    assert (course_dir / "course.json").read_bytes() == course_before
    assert (course_dir / "units.json").read_bytes() == units_before
    window.set_zoom(1.0)
    window.close()
