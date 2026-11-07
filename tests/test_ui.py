from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QRadioButton

from lingua.storage import load_course
from lingua.ui import MainWindow


@pytest.fixture(scope="session")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _create_from_current_form(window: MainWindow, *, blank: bool = False) -> None:
    window.findChild(QLineEdit, "course_name").setText("English - GUI 測試")
    window.findChild(QLineEdit, "course_language").setText("English")
    window.findChild(QPlainTextEdit, "course_goal").setPlainText("能在旅行時完成基本交流")
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
    assert window.findChild(QListWidget, "workspace_units").count() == 44
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
