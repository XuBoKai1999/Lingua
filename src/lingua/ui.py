from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
    QVBoxLayout,
    QWidget,
)

from lingua.storage import (
    DEFAULT_LIBRARY_ROOT,
    create_course,
    list_course_dirs,
    load_course,
    template_stage_counts,
)


class MainWindow(QMainWindow):
    def __init__(self, *, library_root: Path | None = None) -> None:
        super().__init__()
        if QApplication.instance() is None:
            raise RuntimeError("建立主視窗前必須先建立 QApplication")
        self.library_root = library_root or DEFAULT_LIBRARY_ROOT
        self.current_page = ""
        self.current_argument: Path | None = None
        self.history: list[tuple[str, Path | None]] = []

        self.setWindowTitle("Lingua")
        available = self.screen().availableGeometry()
        self.resize(min(1400, int(available.width() * 0.9)), min(900, int(available.height() * 0.9)))
        self._build_toolbar()
        self._display("home")

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("導覽")
        toolbar.setMovable(False)
        self.back_action = QAction("返回", self)
        self.back_action.triggered.connect(self.go_back)
        toolbar.addAction(self.back_action)
        self.home_action = QAction("首頁", self)
        self.home_action.triggered.connect(self.go_home)
        toolbar.addAction(self.home_action)

    def navigate(self, page: str, argument: Path | None = None) -> None:
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
        if not self.history:
            return
        page, argument = self.history.pop()
        self._display(page, argument)

    def go_home(self) -> None:
        if self.current_page != "home":
            self.navigate("home")

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
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        if course_dir is None:
            layout.addWidget(QLabel("未指定教材。"))
            return page
        try:
            course, units = load_course(course_dir)
        except (OSError, ValueError) as exception:
            message = QLabel(f"無法開啟教材：{exception}")
            message.setWordWrap(True)
            layout.addWidget(message)
            return page
        title = QLabel(course["name"])
        title.setObjectName("workspace_title")
        layout.addWidget(title)
        region = f"／{course['region']}" if course["region"] else ""
        summary = QLabel(
            f"{course['language']}{region}\n{course['goal']}\n\n課綱目前有 {len(units['units'])} 個 Units。"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        units_list = QListWidget()
        units_list.setObjectName("workspace_units")
        for unit in units["units"]:
            units_list.addItem(f"{unit['id']} — {unit['context']} — {unit['scenario']}")
        layout.addWidget(units_list)
        return page
