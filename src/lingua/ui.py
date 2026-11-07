from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSettings, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QCloseEvent, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lingua.storage import (
    DEFAULT_LIBRARY_ROOT,
    create_course,
    list_course_dirs,
    load_course,
    next_unit_id,
    save_course,
    save_units,
    template_stage_counts,
    validate_course,
    validate_unit,
    validate_units,
)


def _stage_value(text: str) -> int | None:
    value = text.strip()
    if not value:
        return None
    try:
        stage = int(value)
    except ValueError as error:
        raise ValueError("stage 必須是非負整數或留白") from error
    if stage < 0:
        raise ValueError("stage 必須是非負整數或留白")
    return stage


def _edit_course_dialog(parent: QWidget, course: dict) -> dict | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("編輯教材")
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    name = QLineEdit(course["name"])
    language = QLineEdit(course["language"])
    region = QLineEdit(course["region"] or "")
    goal = QPlainTextEdit(course["goal"])
    default_level = QLineEdit(course["default_level"] or "")
    requirements = QPlainTextEdit(course["requirements"])
    form.addRow("教材名稱 *", name)
    form.addRow("目標語言 *", language)
    form.addRow("國家／地區", region)
    form.addRow("學習目標 *", goal)
    form.addRow("預設程度", default_level)
    form.addRow("長期要求", requirements)
    layout.addLayout(form)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(buttons)
    result: list[dict] = []

    def accept() -> None:
        candidate = {
            "name": name.text().strip(),
            "language": language.text().strip(),
            "region": region.text().strip() or None,
            "goal": goal.toPlainText().strip(),
            "default_level": default_level.text().strip() or None,
            "requirements": requirements.toPlainText().strip(),
        }
        try:
            validate_course(candidate)
        except ValueError as exception:
            QMessageBox.critical(dialog, "教材資料不正確", str(exception))
            return
        result.append(candidate)
        dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    return result[0] if dialog.exec() == QDialog.DialogCode.Accepted else None


def _edit_unit_dialog(parent: QWidget, unit: dict, existing_ids: set[str]) -> dict | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("新增 Unit")
    layout = QVBoxLayout(dialog)
    form = QFormLayout()
    unit_id = QLineEdit(unit["id"])
    stage = QLineEdit("" if unit["stage"] is None else str(unit["stage"]))
    context = QLineEdit(unit["context"])
    scenario = QLineEdit(unit["scenario"])
    description = QPlainTextEdit(unit["description"])
    level = QLineEdit(unit["level"] or "")
    requirements = QPlainTextEdit(unit["requirements"])
    form.addRow("Unit ID *", unit_id)
    form.addRow("階段", stage)
    form.addRow("大情境 *", context)
    form.addRow("子情境 *", scenario)
    form.addRow("能力目標 *", description)
    form.addRow("Unit 程度", level)
    form.addRow("Unit 要求", requirements)
    layout.addLayout(form)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(buttons)
    result: list[dict] = []

    def accept() -> None:
        try:
            candidate = {
                "id": unit_id.text().strip(),
                "stage": _stage_value(stage.text()),
                "context": context.text().strip(),
                "scenario": scenario.text().strip(),
                "description": description.toPlainText().strip(),
                "level": level.text().strip() or None,
                "requirements": requirements.toPlainText().strip(),
            }
            validate_unit(candidate)
            if candidate["id"] in existing_ids:
                raise ValueError(f"Unit ID 已存在：{candidate['id']}")
        except ValueError as exception:
            QMessageBox.critical(dialog, "Unit 資料不正確", str(exception))
            return
        result.append(candidate)
        dialog.accept()

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    return result[0] if dialog.exec() == QDialog.DialogCode.Accepted else None


class CourseWorkspace(QWidget):
    def __init__(self, course_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.course_dir = course_dir
        self.course, self.units = load_course(course_dir)
        self.current_index: int | None = None
        self.dirty = False
        self._loading = False
        self._tree_items: dict[int, QTreeWidgetItem] = {}
        self._build()
        self._populate_tree(0 if self.units["units"] else None)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        header = QHBoxLayout()
        header_text = QVBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("workspace_title")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        header_text.addWidget(self.title)
        header_text.addWidget(self.summary)
        header.addLayout(header_text, 1)
        edit_course = QPushButton("編輯教材")
        edit_course.setObjectName("edit_course_button")
        edit_course.clicked.connect(self._edit_course)
        header.addWidget(edit_course)
        outer.addLayout(header)
        self._refresh_header()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("course_splitter")
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.unit_count = QLabel()
        left_layout.addWidget(self.unit_count)
        self.tree = QTreeWidget()
        self.tree.setObjectName("unit_tree")
        self.tree.setHeaderLabel("階段 → 大情境 → 子情境")
        self.tree.currentItemChanged.connect(self._selection_changed)
        left_layout.addWidget(self.tree, 1)
        tree_actions = QHBoxLayout()
        add = QPushButton("新增")
        add.setObjectName("add_unit_button")
        delete = QPushButton("刪除")
        delete.setObjectName("delete_unit_button")
        up = QPushButton("上移")
        up.setObjectName("move_unit_up_button")
        down = QPushButton("下移")
        down.setObjectName("move_unit_down_button")
        add.clicked.connect(self._add_unit)
        delete.clicked.connect(self._delete_unit)
        up.clicked.connect(lambda: self._move_unit(-1))
        down.clicked.connect(lambda: self._move_unit(1))
        for button in (add, delete, up, down):
            tree_actions.addWidget(button)
        left_layout.addLayout(tree_actions)
        splitter.addWidget(left)

        tabs = QTabWidget()
        tabs.setObjectName("workspace_tabs")
        tabs.addTab(self._build_unit_editor(), "Unit 編輯")
        splitter.addWidget(tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def _build_unit_editor(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        self.edit_status = QLabel("請選擇 Unit。")
        self.edit_status.setObjectName("unit_edit_status")
        self.edit_status.setWordWrap(True)
        layout.addWidget(self.edit_status)
        form = QFormLayout()
        self.unit_id = QLineEdit()
        self.unit_id.setReadOnly(True)
        self.unit_id.setObjectName("unit_id")
        self.unit_stage = QLineEdit()
        self.unit_stage.setObjectName("unit_stage")
        self.unit_context = QLineEdit()
        self.unit_context.setObjectName("unit_context")
        self.unit_scenario = QLineEdit()
        self.unit_scenario.setObjectName("unit_scenario")
        self.unit_description = QPlainTextEdit()
        self.unit_description.setObjectName("unit_description")
        self.unit_level = QLineEdit()
        self.unit_level.setObjectName("unit_level")
        self.unit_requirements = QPlainTextEdit()
        self.unit_requirements.setObjectName("unit_requirements")
        self.effective = QLabel("未指定")
        self.effective.setObjectName("effective_level")
        form.addRow("Unit ID", self.unit_id)
        form.addRow("階段", self.unit_stage)
        form.addRow("大情境", self.unit_context)
        form.addRow("子情境", self.unit_scenario)
        form.addRow("能力目標", self.unit_description)
        form.addRow("Unit 程度", self.unit_level)
        form.addRow("有效程度", self.effective)
        form.addRow("Unit 要求", self.unit_requirements)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.revert_button = QPushButton("還原")
        self.revert_button.setObjectName("revert_unit_button")
        self.save_button = QPushButton("儲存 Unit")
        self.save_button.setObjectName("save_unit_button")
        self.revert_button.clicked.connect(self._revert_current)
        self.save_button.clicked.connect(self._save_current)
        actions.addStretch()
        actions.addWidget(self.revert_button)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        for widget in (self.unit_stage, self.unit_context, self.unit_scenario, self.unit_level):
            widget.textChanged.connect(self._form_changed)
        for widget in (self.unit_description, self.unit_requirements):
            widget.textChanged.connect(self._form_changed)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _refresh_header(self) -> None:
        self.title.setText(self.course["name"])
        region = f"／{self.course['region']}" if self.course["region"] else ""
        self.summary.setText(f"{self.course['language']}{region} — {self.course['goal']}")

    def _populate_tree(self, select_index: int | None = None) -> None:
        blocker = QSignalBlocker(self.tree)
        self.tree.clear()
        self._tree_items.clear()
        stage_items: dict[int | None, QTreeWidgetItem] = {}
        context_items: dict[tuple[int | None, str], QTreeWidgetItem] = {}
        for index, unit in enumerate(self.units["units"]):
            stage = unit["stage"]
            if stage not in stage_items:
                label = "未分階段" if stage is None else f"階段 {stage}"
                stage_items[stage] = QTreeWidgetItem(self.tree, [label])
            context_key = (stage, unit["context"])
            if context_key not in context_items:
                context_items[context_key] = QTreeWidgetItem(stage_items[stage], [unit["context"]])
            leaf = QTreeWidgetItem(context_items[context_key], [f"{unit['id']} — {unit['scenario']}"])
            leaf.setData(0, Qt.ItemDataRole.UserRole, index)
            self._tree_items[index] = leaf
        self.tree.expandAll()
        self.unit_count.setText(f"{len(self.units['units'])} Units")
        if select_index is not None and select_index in self._tree_items:
            self.tree.setCurrentItem(self._tree_items[select_index])
            del blocker
            self._load_unit(select_index)
        else:
            del blocker
            self.current_index = None
            self._loading = True
            self.unit_id.clear()
            self.unit_stage.clear()
            self.unit_context.clear()
            self.unit_scenario.clear()
            self.unit_description.clear()
            self.unit_level.clear()
            self.unit_requirements.clear()
            self._loading = False
            self.dirty = False
            self._set_form_enabled(False)
            self.edit_status.setText("尚無 Unit。可使用左側「新增」建立第一個 Unit。")
            self.effective.setText("未指定")

    def _selection_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        index = None if current is None else current.data(0, Qt.ItemDataRole.UserRole)
        if index is None:
            if previous is not None:
                blocker = QSignalBlocker(self.tree)
                self.tree.setCurrentItem(previous)
                del blocker
            return
        if index == self.current_index:
            return
        if self.dirty:
            if not self._resolve_unsaved():
                blocker = QSignalBlocker(self.tree)
                if self.current_index in self._tree_items:
                    self.tree.setCurrentItem(self._tree_items[self.current_index])
                del blocker
                return
            self._populate_tree(index)
            return
        self._load_unit(index)

    def _set_form_enabled(self, enabled: bool) -> None:
        for widget in (
            self.unit_id, self.unit_stage, self.unit_context, self.unit_scenario,
            self.unit_description, self.unit_level, self.unit_requirements,
            self.revert_button, self.save_button,
        ):
            widget.setEnabled(enabled)

    def _load_unit(self, index: int) -> None:
        unit = self.units["units"][index]
        self._loading = True
        self.current_index = index
        self.unit_id.setText(unit["id"])
        self.unit_stage.setText("" if unit["stage"] is None else str(unit["stage"]))
        self.unit_context.setText(unit["context"])
        self.unit_scenario.setText(unit["scenario"])
        self.unit_description.setPlainText(unit["description"])
        self.unit_level.setText(unit["level"] or "")
        self.unit_requirements.setPlainText(unit["requirements"])
        self._loading = False
        self.dirty = False
        self._set_form_enabled(True)
        self._update_status()

    def _candidate_from_form(self) -> dict:
        return {
            "id": self.unit_id.text(),
            "stage": _stage_value(self.unit_stage.text()),
            "context": self.unit_context.text().strip(),
            "scenario": self.unit_scenario.text().strip(),
            "description": self.unit_description.toPlainText().strip(),
            "level": self.unit_level.text().strip() or None,
            "requirements": self.unit_requirements.toPlainText().strip(),
        }

    def _form_changed(self) -> None:
        if self._loading or self.current_index is None:
            return
        try:
            self.dirty = self._candidate_from_form() != self.units["units"][self.current_index]
        except ValueError:
            self.dirty = True
        self._update_status()

    def _update_status(self) -> None:
        self.edit_status.setText("尚未儲存的變更" if self.dirty else "已儲存")
        level = self.unit_level.text().strip() or self.course["default_level"]
        self.effective.setText(level or "未指定")
        self.save_button.setEnabled(self.current_index is not None and self.dirty)
        self.revert_button.setEnabled(self.current_index is not None and self.dirty)

    def _save_current(self, *, rebuild: bool = True) -> bool:
        if self.current_index is None:
            return True
        try:
            candidate = self._candidate_from_form()
            updated = deepcopy(self.units)
            updated["units"][self.current_index] = candidate
            validate_units(updated)
            save_units(self.course_dir, updated)
        except (OSError, ValueError) as exception:
            QMessageBox.critical(self, "無法儲存 Unit", str(exception))
            return False
        self.units = updated
        self.dirty = False
        if rebuild:
            self._populate_tree(self.current_index)
        else:
            self._update_status()
        return True

    def _revert_current(self) -> None:
        if self.current_index is not None:
            self._load_unit(self.current_index)

    def _resolve_unsaved(self) -> bool:
        if not self.dirty:
            return True
        answer = QMessageBox.question(
            self,
            "尚未儲存",
            "目前 Unit 有尚未儲存的變更。要先儲存嗎？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self._save_current(rebuild=False)
        self._revert_current()
        return True

    def maybe_leave(self) -> bool:
        return self._resolve_unsaved()

    def _edit_course(self) -> None:
        if not self._resolve_unsaved():
            return
        if self.current_index is not None:
            self._populate_tree(self.current_index)
        candidate = _edit_course_dialog(self, deepcopy(self.course))
        if candidate is None:
            return
        try:
            save_course(self.course_dir, candidate)
        except (OSError, ValueError) as exception:
            QMessageBox.critical(self, "無法儲存教材", str(exception))
            return
        self.course = candidate
        self._refresh_header()
        self._update_status()

    def _add_unit(self) -> None:
        if not self._resolve_unsaved():
            return
        current = self.units["units"][self.current_index] if self.current_index is not None else None
        candidate = _edit_unit_dialog(
            self,
            {
                "id": next_unit_id(self.units["units"]),
                "stage": None if current is None else current["stage"],
                "context": "" if current is None else current["context"],
                "scenario": "",
                "description": "",
                "level": None,
                "requirements": "",
            },
            {unit["id"] for unit in self.units["units"]},
        )
        if candidate is None:
            return
        updated = deepcopy(self.units)
        updated["units"].append(candidate)
        try:
            save_units(self.course_dir, updated)
        except (OSError, ValueError) as exception:
            QMessageBox.critical(self, "無法新增 Unit", str(exception))
            return
        self.units = updated
        self._populate_tree(len(updated["units"]) - 1)

    def _delete_unit(self) -> None:
        if self.current_index is None or not self._resolve_unsaved():
            return
        unit = self.units["units"][self.current_index]
        if QMessageBox.question(
            self,
            "刪除 Unit",
            f"確定刪除 {unit['id']} — {unit['scenario']}？此動作會立即儲存。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        updated = deepcopy(self.units)
        del updated["units"][self.current_index]
        try:
            save_units(self.course_dir, updated)
        except (OSError, ValueError) as exception:
            QMessageBox.critical(self, "無法刪除 Unit", str(exception))
            return
        next_index = min(self.current_index, len(updated["units"]) - 1)
        self.units = updated
        self._populate_tree(next_index if next_index >= 0 else None)

    def _move_unit(self, offset: int) -> None:
        if self.current_index is None or not self._resolve_unsaved():
            return
        target = self.current_index + offset
        if target < 0 or target >= len(self.units["units"]):
            return
        updated = deepcopy(self.units)
        updated["units"][self.current_index], updated["units"][target] = (
            updated["units"][target], updated["units"][self.current_index]
        )
        try:
            save_units(self.course_dir, updated)
        except OSError as exception:
            QMessageBox.critical(self, "無法調整 Unit 順序", str(exception))
            return
        self.units = updated
        self._populate_tree(target)


class MainWindow(QMainWindow):
    ZOOM_MIN = 0.8
    ZOOM_MAX = 2.0
    ZOOM_STEP = 0.1
    BASE_FONT_PROPERTY = "linguaBaseFont"

    def __init__(
        self, *, library_root: Path | None = None, settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("建立主視窗前必須先建立 QApplication")
        self.library_root = library_root or DEFAULT_LIBRARY_ROOT
        self.settings = settings if settings is not None else QSettings("Lingua", "Lingua")
        self.current_page = ""
        self.current_argument: Path | None = None
        self.history: list[tuple[str, Path | None]] = []
        base_font = app.property(self.BASE_FONT_PROPERTY)
        if base_font is None:
            base_font = QFont(app.font())
            app.setProperty(self.BASE_FONT_PROPERTY, base_font)
        self.base_font = QFont(base_font)
        self.base_font_size = self.base_font.pointSizeF()
        self.zoom_factor = self._clamp_zoom(float(self.settings.value("ui/zoom", 1.0)))

        self.setWindowTitle("Lingua")
        self._build_toolbar()
        self._display("home")
        geometry = self.settings.value("ui/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            available = self.screen().availableGeometry()
            self.resize(min(1400, int(available.width() * 0.9)), min(900, int(available.height() * 0.9)))
        self.set_zoom(self.zoom_factor, save=False)
        app.installEventFilter(self)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("導覽")
        toolbar.setMovable(False)
        self.back_action = QAction("返回", self)
        self.back_action.triggered.connect(self.go_back)
        toolbar.addAction(self.back_action)
        self.home_action = QAction("首頁", self)
        self.home_action.triggered.connect(self.go_home)
        toolbar.addAction(self.home_action)
        toolbar.addSeparator()
        self.zoom_out_action = QAction("縮小", self)
        self.zoom_out_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.ZoomOut))
        self.zoom_out_action.triggered.connect(lambda: self.set_zoom(self.zoom_factor - self.ZOOM_STEP))
        toolbar.addAction(self.zoom_out_action)
        reset = QAction("重設縮放", self)
        reset.setShortcut("Ctrl+0")
        reset.triggered.connect(lambda: self.set_zoom(1.0))
        toolbar.addAction(reset)
        self.zoom_in_action = QAction("放大", self)
        self.zoom_in_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.ZoomIn))
        self.zoom_in_action.triggered.connect(lambda: self.set_zoom(self.zoom_factor + self.ZOOM_STEP))
        toolbar.addAction(self.zoom_in_action)
        self.zoom_label = QLabel()
        self.zoom_label.setObjectName("zoom_label")
        toolbar.addWidget(self.zoom_label)

    def navigate(self, page: str, argument: Path | None = None) -> None:
        if not self._can_leave():
            return
        if self.current_page:
            self.history.append((self.current_page, self.current_argument))
        self._display(page, argument)

    def _display(self, page: str, argument: Path | None = None) -> None:
        builders = {
            "home": self._build_home,
            "browser": self._build_browser,
            "create": self._build_create_course,
            "workspace": lambda: self._build_workspace(argument),
        }
        if page not in builders:
            raise ValueError(f"未知頁面：{page}")
        old = self.takeCentralWidget()
        if old is not None:
            old.deleteLater()
        self.current_page = page
        self.current_argument = argument
        self.setCentralWidget(builders[page]())
        self.back_action.setEnabled(bool(self.history))
        self.home_action.setEnabled(page != "home")

    def go_back(self) -> None:
        if not self.history or not self._can_leave():
            return
        page, argument = self.history.pop()
        self._display(page, argument)

    def go_home(self) -> None:
        if self.current_page != "home":
            self.navigate("home")

    def _can_leave(self) -> bool:
        page = self.centralWidget()
        return not isinstance(page, CourseWorkspace) or page.maybe_leave()

    @staticmethod
    def _clamp_zoom(value: float) -> float:
        return round(min(MainWindow.ZOOM_MAX, max(MainWindow.ZOOM_MIN, value)), 1)

    def set_zoom(self, value: float, *, save: bool = True) -> None:
        self.zoom_factor = self._clamp_zoom(value)
        font = QFont(self.base_font)
        font.setPointSizeF(self.base_font_size * self.zoom_factor)
        QApplication.instance().setFont(font)
        self.zoom_label.setText(f"{self.zoom_factor:.0%}")
        self.zoom_out_action.setEnabled(self.zoom_factor > self.ZOOM_MIN)
        self.zoom_in_action.setEnabled(self.zoom_factor < self.ZOOM_MAX)
        if save:
            self.settings.setValue("ui/zoom", self.zoom_factor)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.set_zoom(self.zoom_factor + (self.ZOOM_STEP if delta > 0 else -self.ZOOM_STEP))
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._can_leave():
            event.ignore()
            return
        self.settings.setValue("ui/geometry", self.saveGeometry())
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        event.accept()

    def _build_home(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(18)
        layout.addStretch()
        title = QLabel("Lingua")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("home_title")
        layout.addWidget(title)
        subtitle = QLabel("建立、瀏覽與編輯你的外語教材")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        enter = QPushButton("進入教材")
        enter.setObjectName("browse_courses_button")
        enter.clicked.connect(lambda: self.navigate("browser"))
        layout.addWidget(enter)
        create = QPushButton("創建新教材")
        create.setObjectName("create_course_button")
        create.clicked.connect(lambda: self.navigate("create"))
        layout.addWidget(create)
        layout.addStretch()
        return page

    def _build_browser(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("教材瀏覽"))
        courses = QListWidget()
        courses.setObjectName("course_list")
        layout.addWidget(courses)
        status = QLabel("選擇教材後開啟。")
        status.setWordWrap(True)
        status.setObjectName("browser_status")
        layout.addWidget(status)
        actions = QHBoxLayout()
        refresh = QPushButton("重新整理")
        open_button = QPushButton("開啟教材")
        open_button.setObjectName("open_course_button")
        open_button.setEnabled(False)
        actions.addStretch()
        actions.addWidget(refresh)
        actions.addWidget(open_button)
        layout.addLayout(actions)

        def populate() -> None:
            courses.clear()
            for course_dir in list_course_dirs(self.library_root):
                try:
                    course, units = load_course(course_dir)
                    label = f"{course['name']} — {course['language']} — {len(units['units'])} Units"
                    error = None
                except (OSError, ValueError) as exception:
                    label = f"{course_dir.name} — 無法讀取"
                    error = str(exception)
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, str(course_dir))
                item.setData(Qt.ItemDataRole.UserRole + 1, error)
                courses.addItem(item)
            if courses.count() == 0:
                status.setText("尚未建立教材。請返回首頁並選擇「創建新教材」。")
            open_button.setEnabled(False)

        def selection_changed() -> None:
            item = courses.currentItem()
            error = None if item is None else item.data(Qt.ItemDataRole.UserRole + 1)
            open_button.setEnabled(item is not None and error is None)
            if error:
                status.setText(f"此教材無法開啟：{error}")
            elif item is not None:
                status.setText("按「開啟教材」或雙擊教材繼續。")

        def open_selected() -> None:
            item = courses.currentItem()
            if item is None or item.data(Qt.ItemDataRole.UserRole + 1):
                return
            course_dir = Path(item.data(Qt.ItemDataRole.UserRole))
            try:
                load_course(course_dir)
            except (OSError, ValueError) as exception:
                QMessageBox.critical(self, "無法開啟教材", str(exception))
                populate()
                return
            self.navigate("workspace", course_dir)

        courses.itemSelectionChanged.connect(selection_changed)
        courses.itemDoubleClicked.connect(lambda _item: open_selected())
        refresh.clicked.connect(populate)
        open_button.clicked.connect(open_selected)
        populate()
        return page

    def _build_create_course(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.addWidget(QLabel("創建新教材"))

        form = QFormLayout()
        name = QLineEdit()
        name.setObjectName("course_name")
        language = QLineEdit()
        language.setObjectName("course_language")
        region = QLineEdit()
        region.setObjectName("course_region")
        goal = QPlainTextEdit()
        goal.setObjectName("course_goal")
        goal.setPlaceholderText("這份教材要幫助你完成什麼？")
        default_level = QLineEdit()
        default_level.setObjectName("course_default_level")
        default_level.setPlaceholderText("可留白，例如 A2")
        requirements = QPlainTextEdit()
        requirements.setObjectName("course_requirements")
        requirements.setPlaceholderText("可留白，例如偏重實際溝通、不安排獨立文法課")
        form.addRow("教材名稱 *", name)
        form.addRow("目標語言 *", language)
        form.addRow("國家／地區", region)
        form.addRow("學習目標 *", goal)
        form.addRow("預設程度", default_level)
        form.addRow("長期要求", requirements)
        layout.addLayout(form)

        source_group = QGroupBox("課綱來源")
        source_layout = QVBoxLayout(source_group)
        template_source = QRadioButton("落地生根")
        template_source.setObjectName("template_source")
        blank_source = QRadioButton("空白教材")
        blank_source.setObjectName("blank_source")
        template_source.setChecked(True)
        source_layout.addWidget(template_source)
        source_layout.addWidget(blank_source)

        stage_frame = QFrame()
        stage_layout = QVBoxLayout(stage_frame)
        stage_layout.setContentsMargins(20, 4, 0, 4)
        counts = template_stage_counts()
        stage_checks: dict[int, QCheckBox] = {}
        for stage, count in sorted(counts.items()):
            checkbox = QCheckBox(f"階段 {stage}（{count} Units）")
            checkbox.setObjectName(f"stage_{stage}")
            checkbox.setChecked(stage in {0, 1})
            stage_checks[stage] = checkbox
            stage_layout.addWidget(checkbox)
        source_layout.addWidget(stage_frame)
        layout.addWidget(source_group)

        preview = QLabel()
        preview.setObjectName("unit_count_preview")
        preview.setWordWrap(True)
        layout.addWidget(preview)

        actions = QHBoxLayout()
        cancel = QPushButton("取消")
        save = QPushButton("建立教材")
        save.setObjectName("save_course_button")
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

        def update_preview() -> None:
            is_template = template_source.isChecked()
            stage_frame.setVisible(is_template)
            count = sum(counts[stage] for stage, checkbox in stage_checks.items() if checkbox.isChecked()) if is_template else 0
            preview.setText(f"將建立 {count} 個 Units。" if is_template else "將建立空白課綱（0 Units）。")

        def save_course_from_form() -> None:
            course = {
                "name": name.text().strip(),
                "language": language.text().strip(),
                "region": region.text().strip() or None,
                "goal": goal.toPlainText().strip(),
                "default_level": default_level.text().strip() or None,
                "requirements": requirements.toPlainText().strip(),
            }
            stages = tuple(stage for stage, checkbox in stage_checks.items() if checkbox.isChecked())
            try:
                course_dir = create_course(
                    course,
                    template_stages=stages if template_source.isChecked() else None,
                    library_root=self.library_root,
                )
            except (OSError, ValueError) as exception:
                QMessageBox.critical(self, "無法建立教材", str(exception))
                return
            self.navigate("workspace", course_dir)

        template_source.toggled.connect(update_preview)
        for checkbox in stage_checks.values():
            checkbox.toggled.connect(update_preview)
        cancel.clicked.connect(self.go_back)
        save.clicked.connect(save_course_from_form)
        update_preview()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _build_workspace(self, course_dir: Path | None) -> QWidget:
        if course_dir is None:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.addWidget(QLabel("未指定教材。"))
            return page
        try:
            return CourseWorkspace(course_dir, self)
        except (OSError, ValueError) as exception:
            page = QWidget()
            layout = QVBoxLayout(page)
            message = QLabel(f"無法開啟教材：{exception}")
            message.setWordWrap(True)
            layout.addWidget(message)
            return page
