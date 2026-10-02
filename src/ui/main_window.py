import os
import sys
import ctypes
from pathlib import Path
from typing import Optional, List
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QProgressBar,
    QTreeWidget, QTreeWidgetItem, QCheckBox, QGroupBox,
    QRadioButton, QButtonGroup, QMessageBox, QSplitter,
    QHeaderView, QMenu, QDialog, QDialogButtonBox, QTextEdit,
    QScrollArea, QFrame, QSizePolicy, QListWidget, QListWidgetItem,
    QFileSystemModel, QTreeView, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSettings, QDir
from PySide6.QtGui import QIcon, QFont, QColor, QBrush, QAction

from src.core.duplicate_finder import DuplicateFinder, ScanResult, DuplicateGroup
from src.core.everything_search import FileInfo
from src.core.ntfs_linker import LinkType


class ScanWorker(QThread):
    progress_updated = Signal(int, int, str)
    scan_finished = Signal(object)
    scan_error = Signal(str)

    def __init__(self, finder: DuplicateFinder, directories: List[str], min_size: int):
        super().__init__()
        self.finder = finder
        self.directories = directories
        self.min_size = min_size

    def run(self):
        try:
            self.finder.set_progress_callback(self.progress_updated.emit)
            result = self.finder.scan_directories(self.directories, self.min_size)
            self.scan_finished.emit(result)
        except Exception as e:
            self.scan_error.emit(str(e))


class ActionWorker(QThread):
    progress_updated = Signal(int, int, str)
    action_finished = Signal(list)
    action_error = Signal(str)

    def __init__(self, finder: DuplicateFinder, groups: List[DuplicateGroup], action: str, link_type: LinkType):
        super().__init__()
        self.finder = finder
        self.groups = groups
        self.action = action
        self.link_type = link_type

    def run(self):
        try:
            all_results = []
            total_groups = len(self.groups)
            
            for i, group in enumerate(self.groups):
                self.progress_updated.emit(i + 1, total_groups, f"处理组 {i+1}/{total_groups}...")
                results = self.finder.apply_action(group, self.action, self.link_type)
                all_results.extend(results)
            
            self.action_finished.emit(all_results)
        except Exception as e:
            self.action_error.emit(str(e))


class DuplicateItemWidget(QWidget):
    def __init__(self, file_info: FileInfo, is_keep: bool = False, parent=None):
        super().__init__(parent)
        self.file_info = file_info
        self.is_keep = is_keep
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        
        self.radio = QRadioButton()
        self.radio.setChecked(self.is_keep)
        self.radio.setToolTip("设为保留文件 (其他文件将被替换为指向此文件的符号链接)")
        layout.addWidget(self.radio)
        
        self.checkbox = QCheckBox()
        self.checkbox.setEnabled(True)
        if self.is_keep:
            self.checkbox.setChecked(False)
            self.checkbox.setToolTip("保留文件，默认不删除。如需删除，请手动勾选")
        else:
            self.checkbox.setChecked(True)
            self.checkbox.setToolTip("勾选后将删除此文件并替换为指向保留文件的符号链接")
        layout.addWidget(self.checkbox)
        
        self.name_label = QLabel(self.file_info.name)
        self.name_label.setToolTip(self.file_info.path)
        self.name_label.setMinimumWidth(200)
        self.update_keep_style()
        layout.addWidget(self.name_label)
        
        path_label = QLabel(self.file_info.path)
        path_label.setStyleSheet("color: #666; font-size: 11px;")
        path_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(path_label)
        
        size_label = QLabel(self.format_size(self.file_info.size))
        size_label.setMinimumWidth(80)
        size_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(size_label)
        
        time_label = QLabel(self.format_time(self.file_info.modified_time))
        time_label.setMinimumWidth(140)
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(time_label)

    def update_keep_style(self):
        if self.is_keep:
            self.name_label.setStyleSheet("font-weight: bold; color: #2e7d32;")
            self.name_label.setText(f"★ {self.file_info.name}")
        else:
            self.name_label.setStyleSheet("")
            self.name_label.setText(self.file_info.name)

    def format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def format_time(self, timestamp: float) -> str:
        from datetime import datetime
        try:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except:
            return "未知"

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def set_checked(self, checked: bool):
        self.checkbox.setChecked(checked)


class GroupWidget(QWidget):
    def __init__(self, group: DuplicateGroup, group_index: int, parent=None):
        super().__init__(parent)
        self.group = group
        self.group_index = group_index
        self.item_widgets = []
        self.keep_button_group = QButtonGroup(self)
        self.keep_button_group.setExclusive(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 4, 4, 4)
        
        self.group_checkbox = QCheckBox(f"组 {self.group_index + 1}: {len(self.group.files)} 个文件, 大小: {self.format_size(self.group.size)}, 浪费空间: {self.format_size(self.group.size * len(self.group.confirmed_duplicates))}")
        self.group_checkbox.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.group_checkbox.setChecked(True)
        self.group_checkbox.toggled.connect(self.on_group_toggled)
        header_layout.addWidget(self.group_checkbox)
        
        header_layout.addStretch()
        
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setMaximumWidth(60)
        self.select_all_btn.clicked.connect(self.select_all)
        header_layout.addWidget(self.select_all_btn)
        
        self.select_none_btn = QPushButton("取消")
        self.select_none_btn.setMaximumWidth(60)
        self.select_none_btn.clicked.connect(self.select_none)
        header_layout.addWidget(self.select_none_btn)
        
        self.invert_btn = QPushButton("反选")
        self.invert_btn.setMaximumWidth(60)
        self.invert_btn.clicked.connect(self.invert_selection)
        header_layout.addWidget(self.invert_btn)
        
        layout.addWidget(header)
        
        self.items_container = QWidget()
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(20, 0, 0, 0)
        self.items_layout.setSpacing(1)
        layout.addWidget(self.items_container)
        
        self.populate_items()
        self.update_header()

    def format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def populate_items(self):
        keep_path = self.group.keep_file.path if self.group.keep_file else None
        
        for file_info in self.group.files:
            is_keep = (file_info.path == keep_path)
            widget = DuplicateItemWidget(file_info, is_keep)
            self.keep_button_group.addButton(widget.radio)
            widget.radio.toggled.connect(lambda checked, w=widget: self.on_keep_changed(w) if checked else None)
            widget.checkbox.toggled.connect(lambda checked, w=widget: self.update_header())
            self.item_widgets.append(widget)
            self.items_layout.addWidget(widget)

    def on_keep_changed(self, keep_widget):
        for widget in self.item_widgets:
            is_selected_keep = widget is keep_widget
            widget.is_keep = is_selected_keep
            if is_selected_keep:
                widget.checkbox.setChecked(False)
                widget.checkbox.setEnabled(True)
                widget.checkbox.setToolTip("保留文件，默认不删除。如需删除，请手动勾选")
            else:
                widget.checkbox.setChecked(True)
                widget.checkbox.setEnabled(True)
                widget.checkbox.setToolTip("勾选后将删除此文件并替换为指向保留文件的符号链接")
            widget.update_keep_style()
        self.group.keep_file = keep_widget.file_info
        self.group.confirmed_duplicates = [w.file_info for w in self.item_widgets if not w.is_keep]
        self.update_header()

    def update_header(self):
        keep_widget = next((w for w in self.item_widgets if w.is_keep), None)
        self.group.keep_file = keep_widget.file_info if keep_widget else None
        selected_count = sum(1 for w in self.item_widgets if w.is_checked() and not w.is_keep)
        self.group_checkbox.setText(
            f"组 {self.group_index + 1}: {len(self.group.files)} 个文件, 大小: {self.format_size(self.group.size)}, "
            f"已选 {selected_count} 个, 可节省: {self.format_size(self.group.size * selected_count)}"
        )
        self.group_checkbox.setEnabled(keep_widget is not None)

    def on_group_toggled(self, checked: bool):
        for widget in self.item_widgets:
            if not widget.is_keep:
                widget.set_checked(checked)

    def select_all(self):
        for widget in self.item_widgets:
            if not widget.is_keep:
                widget.set_checked(True)
        self.group_checkbox.setChecked(True)

    def select_none(self):
        for widget in self.item_widgets:
            widget.set_checked(False)
        self.group_checkbox.setChecked(False)

    def invert_selection(self):
        for widget in self.item_widgets:
            if not widget.is_keep:
                widget.set_checked(not widget.checkbox.isChecked())
        
        any_checked = any(w.checkbox.isChecked() for w in self.item_widgets if not w.is_keep)
        self.group_checkbox.setChecked(any_checked)

    def get_selected_files(self) -> List[FileInfo]:
        selected = []
        for widget in self.item_widgets:
            if widget.is_checked() and not widget.is_keep:
                selected.append(widget.file_info)
        return selected

    def has_selection(self) -> bool:
        return any(w.is_checked() for w in self.item_widgets if not w.is_keep)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(400)
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        link_group = QGroupBox("链接类型")
        link_layout = QVBoxLayout(link_group)
        
        self.link_type_group = QButtonGroup(self)
        self.hardlink_radio = QRadioButton("硬链接 - 同一文件系统，节省空间，原位置可访问")
        self.symlink_radio = QRadioButton("符号链接 - 跨文件系统，类似快捷方式")
        self.junction_radio = QRadioButton("目录联接 - 仅目录，类似符号链接")
        
        self.hardlink_radio.setChecked(True)
        
        self.link_type_group.addButton(self.hardlink_radio, 0)
        self.link_type_group.addButton(self.symlink_radio, 1)
        self.link_type_group.addButton(self.junction_radio, 2)
        
        link_layout.addWidget(self.hardlink_radio)
        link_layout.addWidget(self.symlink_radio)
        link_layout.addWidget(self.junction_radio)
        
        layout.addWidget(link_group)
        
        scan_group = QGroupBox("扫描设置")
        scan_layout = QVBoxLayout(scan_group)
        
        min_size_layout = QHBoxLayout()
        min_size_layout.addWidget(QLabel("最小文件大小:"))
        self.min_size_edit = QLineEdit("1")
        self.min_size_edit.setMaximumWidth(100)
        min_size_layout.addWidget(self.min_size_edit)
        min_size_layout.addWidget(QLabel("字节 (0 表示不限制)"))
        min_size_layout.addStretch()
        scan_layout.addLayout(min_size_layout)
        
        layout.addWidget(scan_group)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self) -> dict:
        link_type = LinkType.SYMBOLIC_LINK
        if self.hardlink_radio.isChecked():
            link_type = LinkType.HARD_LINK
        elif self.junction_radio.isChecked():
            link_type = LinkType.JUNCTION
        
        return {
            "es_path": "es.exe",
            "link_type": link_type,
            "min_size": int(self.min_size_edit.text()) if self.min_size_edit.text().isdigit() else 1
        }

    def load_settings(self):
        settings = QSettings("DuplicateCleaner", "Settings")
        
        link_type_val = settings.value("link_type", 1, type=int)
        if link_type_val == 0:
            self.hardlink_radio.setChecked(True)
        elif link_type_val == 2:
            self.junction_radio.setChecked(True)
        else:
            self.symlink_radio.setChecked(True)
        
        self.min_size_edit.setText(str(settings.value("min_size", 1, type=int)))

    def save_settings(self):
        settings = QSettings("DuplicateCleaner", "Settings")
        s = self.get_settings()
        settings.setValue("es_path", s["es_path"])
        settings.setValue("link_type", self.link_type_group.checkedId())
        settings.setValue("min_size", s["min_size"])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("重复文件清理工具 - 基于 Everything + NTFS 硬链接")
        self.resize(1200, 800)
        
        self.finder = DuplicateFinder()
        self.scan_result: Optional[ScanResult] = None
        self.group_widgets: List[GroupWidget] = []
        self.scan_worker: Optional[ScanWorker] = None
        self.action_worker: Optional[ActionWorker] = None
        
        self.settings = QSettings("DuplicateCleaner", "Settings")
        self.setup_ui()
        self.load_window_state()
        self.apply_styles()
        self.update_es_status()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        toolbar = self.create_toolbar()
        main_layout.addWidget(toolbar)
        
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter, 1)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.groups_container = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_container)
        self.groups_layout.setContentsMargins(0, 0, 0, 0)
        self.groups_layout.setSpacing(8)
        self.groups_layout.addStretch()
        
        self.scroll_area.setWidget(self.groups_container)
        splitter.addWidget(self.scroll_area)
        
        log_group = QGroupBox("操作日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_group)
        
        splitter.setSizes([600, 150])
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666; padding: 4px;")
        main_layout.addWidget(self.status_label)
        
        self.create_menu_bar()

    def create_toolbar(self) -> QWidget:
        toolbar = QWidget()
        layout = QVBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        # 目录列表区域
        dir_group = QGroupBox("扫描目录 (支持多目录、跨分区)")
        dir_layout = QVBoxLayout(dir_group)
        dir_layout.setContentsMargins(6, 6, 6, 6)
        dir_layout.setSpacing(4)
        
        # 目录列表
        self.dir_list = QListWidget()
        self.dir_list.setMaximumHeight(100)
        self.dir_list.setAlternatingRowColors(True)
        self.dir_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dir_list.customContextMenuRequested.connect(self.show_dir_context_menu)
        dir_layout.addWidget(self.dir_list)
        
        # 目录操作按钮
        dir_btn_layout = QHBoxLayout()
        add_dir_btn = QPushButton("添加目录...")
        add_dir_btn.clicked.connect(self.add_directory)
        dir_btn_layout.addWidget(add_dir_btn)
        
        remove_dir_btn = QPushButton("移除选中")
        remove_dir_btn.clicked.connect(self.remove_selected_directories)
        dir_btn_layout.addWidget(remove_dir_btn)
        
        clear_dirs_btn = QPushButton("清空列表")
        clear_dirs_btn.clicked.connect(self.clear_directories)
        dir_btn_layout.addWidget(clear_dirs_btn)
        
        dir_btn_layout.addStretch()
        
        # 预设常用目录按钮
        preset_label = QLabel("快速添加:")
        preset_label.setStyleSheet("color: #666;")
        dir_btn_layout.addWidget(preset_label)
        
        for preset_name, preset_path in [
            ("桌面", os.path.join(os.path.expanduser("~"), "Desktop")),
            ("文档", os.path.join(os.path.expanduser("~"), "Documents")),
            ("下载", os.path.join(os.path.expanduser("~"), "Downloads")),
        ]:
            if os.path.exists(preset_path):
                btn = QPushButton(preset_name)
                btn.setMaximumWidth(60)
                btn.clicked.connect(lambda checked, p=preset_path: self.add_preset_directory(p))
                dir_btn_layout.addWidget(btn)
        
        dir_layout.addLayout(dir_btn_layout)
        layout.addWidget(dir_group)
        
        # 操作按钮行
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        
        # Everything 状态指示器
        self.es_status_label = QLabel()
        self.es_status_label.setMinimumWidth(180)
        self.es_status_label.setStyleSheet("padding: 4px 8px; border-radius: 3px; font-weight: bold;")
        self.update_es_status()
        action_layout.addWidget(self.es_status_label)
        
        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.setMinimumWidth(100)
        self.scan_btn.clicked.connect(self.start_scan)
        action_layout.addWidget(self.scan_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.clicked.connect(self.cancel_operation)
        self.cancel_btn.setVisible(False)
        action_layout.addWidget(self.cancel_btn)
        
        self.settings_btn = QPushButton("设置")
        self.settings_btn.setMinimumWidth(80)
        self.settings_btn.clicked.connect(self.show_settings)
        action_layout.addWidget(self.settings_btn)
        
        action_layout.addStretch()
        
        self.select_all_btn = QPushButton("全选所有")
        self.select_all_btn.clicked.connect(self.select_all_groups)
        self.select_all_btn.setEnabled(False)
        action_layout.addWidget(self.select_all_btn)
        
        self.select_none_btn = QPushButton("取消所有")
        self.select_none_btn.clicked.connect(self.select_none_groups)
        self.select_none_btn.setEnabled(False)
        action_layout.addWidget(self.select_none_btn)
        
        self.delete_btn = QPushButton("删除选中 (创建软链接)")
        self.delete_btn.setMinimumWidth(180)
        self.delete_btn.setStyleSheet("background-color: #c62828; color: white; font-weight: bold;")
        self.delete_btn.clicked.connect(self.delete_selected)
        self.delete_btn.setEnabled(False)
        action_layout.addWidget(self.delete_btn)
        
        layout.addLayout(action_layout)
        
        return toolbar

    def create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件")
        
        scan_action = QAction("扫描目录...", self)
        scan_action.setShortcut("Ctrl+O")
        scan_action.triggered.connect(self.browse_directory)
        file_menu.addAction(scan_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        tools_menu = menubar.addMenu("工具")
        
        settings_action = QAction("设置...", self)
        settings_action.triggered.connect(self.show_settings)
        tools_menu.addAction(settings_action)
        
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #fafafa;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QPushButton {
                background-color: #e0e0e0;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px 12px;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            QPushButton:pressed {
                background-color: #c0c0c0;
            }
            QPushButton:disabled {
                background-color: #f0f0f0;
                color: #999;
            }
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px;
                background: white;
            }
            QLineEdit:focus {
                border-color: #2196f3;
            }
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
                background: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #2196f3;
                border-radius: 3px;
            }
            QCheckBox {
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QScrollArea {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
            }
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: #fafafa;
            }
        """)

    def get_directories(self) -> List[str]:
        dirs = []
        for i in range(self.dir_list.count()):
            item = self.dir_list.item(i)
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and os.path.exists(path):
                dirs.append(path)
        return dirs

    def browse_directory(self):
        """菜单栏兼容方法"""
        self.add_directory()

    def add_directory(self):
        paths = self._select_directories()
        for path in paths:
            self.add_directory_to_list(path)

    def _select_directories(self) -> list[str]:
        """打开多目录选择对话框，返回选中的目录路径列表"""
        dialog = QDialog(self)
        dialog.setWindowTitle("选择扫描目录")
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        
        # 路径输入栏
        path_layout = QHBoxLayout()
        path_label = QLabel("路径:")
        path_layout.addWidget(QLabel("路径:"))
        
        path_edit = QLineEdit()
        path_edit.setPlaceholderText("粘贴或输入目录路径，按 Enter 跳转...")
        path_layout.addWidget(path_edit)
        
        go_btn = QPushButton("跳转")
        go_btn.setMaximumWidth(60)
        path_layout.addWidget(go_btn)
        layout.addLayout(path_layout)
        
        # 文件系统模型
        model = QFileSystemModel()
        model.setRootPath("")
        model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        
        # 树视图
        tree = QTreeView()
        tree.setModel(model)
        tree.setRootIndex(model.index(""))
        tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        tree.setColumnWidth(0, 300)
        # 隐藏不需要的列
        for col in range(1, 4):
            tree.hideColumn(col)
        layout.addWidget(tree)
        
        # 跳转功能
        def go_to_path():
            path = path_edit.text().strip()
            if path and os.path.exists(path):
                index = model.index(path)
                if index.isValid():
                    tree.setRootIndex(index)
                    tree.scrollTo(index)
                    tree.selectionModel().clearSelection()
                    tree.selectionModel().select(index, tree.selectionModel().SelectionFlag.Select | tree.selectionModel().SelectionFlag.Rows)
        
        path_edit.returnPressed.connect(go_to_path)
        go_btn.clicked.connect(go_to_path)
        
        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        paths = []
        if dialog.exec() == QDialog.Accepted:
            indexes = tree.selectionModel().selectedRows()
            for index in indexes:
                path = model.filePath(index)
                paths.append(path)
        return paths

    def add_preset_directory(self, path: str):
        self.add_directory_to_list(path)

    def add_directory_to_list(self, path: str):
        path = os.path.abspath(path)
        # 检查是否已存在
        for i in range(self.dir_list.count()):
            item = self.dir_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                self.log(f"目录已在列表中: {path}")
                return
        
        if not os.path.exists(path):
            self.log(f"目录不存在: {path}")
            return
        
        item = QListWidgetItem(path)
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self.dir_list.addItem(item)
        self.log(f"已添加目录: {path}")

    def remove_selected_directories(self):
        selected_items = self.dir_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            path = item.data(Qt.ItemDataRole.UserRole)
            self.dir_list.takeItem(self.dir_list.row(item))
            self.log(f"已移除目录: {path}")

    def clear_directories(self):
        self.dir_list.clear()
        self.log("已清空目录列表")

    def show_dir_context_menu(self, position):
        menu = QMenu()
        remove_action = menu.addAction("移除")
        open_action = menu.addAction("打开文件夹")
        
        item = self.dir_list.itemAt(position)
        if item:
            action = menu.exec(self.dir_list.mapToGlobal(position))
            if action == remove_action:
                path = item.data(Qt.ItemDataRole.UserRole)
                self.dir_list.takeItem(self.dir_list.row(item))
                self.log(f"已移除目录: {path}")
            elif action == open_action:
                path = item.data(Qt.ItemDataRole.UserRole)
                os.startfile(path)

    def start_scan(self):
        try:
            self.log("[SCAN] 开始扫描流程...")
            directories = self.get_directories()
            self.log(f"[SCAN] 获取到 {len(directories)} 个目录")
            if not directories:
                QMessageBox.warning(self, "提示", "请先添加至少一个扫描目录")
                return
            
            settings = self.get_current_settings()
            self.log(f"扫描启动: es.exe 已内置")
            self.log(f"[SCAN] 初始化 DuplicateFinder...")
            self.finder = DuplicateFinder(settings["es_path"])
            status_text = self.finder.everything.get_status_text()
            self.log(f"状态检查: {status_text}")
            self.log(f"[SCAN] Everything 可用: {self.finder.everything.is_available()}")
            
            if not self.finder.everything.is_available():
                QMessageBox.critical(self, "错误", 
                    f"无法连接到 Everything\n\n"
                    f"状态: {status_text}\n\n"
                    f"请检查:\n"
                    f"1. Everything 是否已安装并正在运行 (系统托盘)\n"
                    f"2. Everything 是否已完成索引\n\n"
                    f"es.exe 已内置，无需另外安装。")
                self.update_es_status()
                return
            
            self.clear_results()
            self.set_ui_state(scanning=True)
            self.log(f"开始扫描 {len(directories)} 个目录: {', '.join(directories)}")
            
            self.scan_worker = ScanWorker(self.finder, directories, settings["min_size"])
            self.scan_worker.progress_updated.connect(self.on_scan_progress)
            self.scan_worker.scan_finished.connect(self.on_scan_finished)
            self.scan_worker.scan_error.connect(self.on_scan_error)
            self.scan_worker.start()
            self.log("[SCAN] ScanWorker 线程已启动")
        except Exception as e:
            import traceback
            error_msg = f"启动扫描时发生错误:\n{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
            self.log(f"[ERROR] {error_msg}")
            QMessageBox.critical(self, "错误", error_msg)

    def get_current_settings(self) -> dict:
        link_type_map = {
            0: LinkType.HARD_LINK,
            1: LinkType.SYMBOLIC_LINK,
            2: LinkType.JUNCTION,
        }
        link_type_id = self.settings.value("link_type", 0, type=int)
        link_type = link_type_map.get(link_type_id, LinkType.HARD_LINK)
        return {
            "es_path": self.settings.value("es_path", "es.exe"),
            "link_type": link_type,
            "min_size": self.settings.value("min_size", 1, type=int)
        }

    def on_scan_progress(self, current: int, total: int, message: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(message)
        self.log(message)

    def on_scan_finished(self, result: ScanResult):
        self.scan_result = result
        self.set_ui_state(scanning=False)
        self.display_results(result)
        
        if result.total_duplicate_groups == 0:
            self.log("扫描完成，未发现重复文件")
            QMessageBox.information(self, "扫描完成", "未发现重复文件")
        else:
            self.log(f"扫描完成: 发现 {result.total_duplicate_groups} 组重复文件, {result.total_duplicate_files} 个重复文件, 可节省 {self.format_size(result.total_wasted_space)}")

    def on_scan_error(self, error: str):
        self.set_ui_state(scanning=False)
        self.log(f"扫描出错: {error}")
        QMessageBox.critical(self, "扫描错误", f"扫描过程中发生错误:\n{error}")

    def display_results(self, result: ScanResult):
        self.clear_results()
        
        for i, group in enumerate(result.groups):
            if not group.confirmed_duplicates:
                continue
            
            widget = GroupWidget(group, i)
            self.group_widgets.append(widget)
            self.groups_layout.insertWidget(self.groups_layout.count() - 1, widget)
        
        self.select_all_btn.setEnabled(True)
        self.select_none_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)

    def clear_results(self):
        for widget in self.group_widgets:
            widget.deleteLater()
        self.group_widgets.clear()

    def set_ui_state(self, scanning: bool):
        self.scan_btn.setVisible(not scanning)
        self.cancel_btn.setVisible(scanning)
        self.progress_bar.setVisible(scanning)
        self.dir_list.setEnabled(not scanning)
        self.settings_btn.setEnabled(not scanning)
        
        if not scanning:
            self.progress_bar.setValue(0)

    def cancel_operation(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.finder.cancel()
            self.scan_worker.terminate()
            self.scan_worker.wait()
            self.log("扫描已取消")
            self.set_ui_state(scanning=False)
        
        if self.action_worker and self.action_worker.isRunning():
            self.action_worker.finder.cancel()
            self.action_worker.terminate()
            self.action_worker.wait()
            self.log("操作已取消")
            self.set_ui_state(scanning=False)

    def select_all_groups(self):
        for widget in self.group_widgets:
            widget.select_all()

    def select_none_groups(self):
        for widget in self.group_widgets:
            widget.select_none()

    def delete_selected(self):
        selected_groups = []
        total_selected = 0
        
        for widget in self.group_widgets:
            selected_files = widget.get_selected_files()
            if selected_files:
                widget.group.confirmed_duplicates = selected_files
                selected_groups.append(widget.group)
                total_selected += len(selected_files)
        
        if not selected_groups:
            QMessageBox.warning(self, "提示", "请先勾选要删除的文件\n\n提示：勾选文件前的复选框（不是单选按钮）")
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要处理 {total_selected} 个重复文件吗？\n\n"
            f"操作说明：\n"
            f"• 选中的重复文件会先移入回收站\n"
            f"• 原位置会创建指向保留文件的符号链接\n"
            f"• 符号链接与原文件共享同一数据块，不占用额外空间\n"
            f"• 所有路径仍可正常访问文件内容\n"
            f"• 如需恢复，可从回收站还原原文件\n\n"
            f"注：exFAT/FAT32 移动硬盘不支持链接，将仅移入回收站。\n\n"
            f"建议在回收站确认无误后再清空。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        settings = self.get_current_settings()
        self.set_ui_state(scanning=True)
        self.log(f"开始处理 {total_selected} 个文件...")
        
        self.action_worker = ActionWorker(
            self.finder, selected_groups, "delete", settings["link_type"]
        )
        self.action_worker.progress_updated.connect(self.on_action_progress)
        self.action_worker.action_finished.connect(self.on_action_finished)
        self.action_worker.action_error.connect(self.on_action_error)
        self.action_worker.start()

    def on_action_progress(self, current: int, total: int, message: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(message)

    def on_action_finished(self, results: List[tuple]):
        self.set_ui_state(scanning=False)
        
        success_count = sum(1 for _, success, _ in results if success)
        fail_count = len(results) - success_count
        
        self.log(f"处理完成: 成功 {success_count}, 失败 {fail_count}")
        
        for path, success, msg in results:
            color = "#2e7d32" if success else "#c62828"
            self.log(f'<span style="color:{color}">{"✓" if success else "✗"}</span> {os.path.basename(path)}: {msg}')
        
        if fail_count > 0:
            QMessageBox.warning(self, "处理完成", f"完成: 成功 {success_count}, 失败 {fail_count}\n请查看日志了解详情")
        else:
            QMessageBox.information(self, "处理完成", f"全部成功处理 {success_count} 个文件")
        
        self.refresh_results()

    def on_action_error(self, error: str):
        self.set_ui_state(scanning=False)
        self.log(f"操作出错: {error}")
        QMessageBox.critical(self, "操作错误", f"处理过程中发生错误:\n{error}")

    def refresh_results(self):
        if self.scan_result is None:
            return
        self.log("[SCAN] 操作完成，重新扫描以刷新结果...")
        self.start_scan()

    def show_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.save_settings()
            es_path = dialog.get_settings()["es_path"]
            self.log(f"设置保存: es.exe = {es_path} (已内置)")
            self.finder = DuplicateFinder(es_path)
            self.update_es_status()
            self.log(f"状态更新: {self.finder.everything.get_status_text()}")
            self.log("设置已保存")

    def update_es_status(self):
        if hasattr(self, 'es_status_label') and self.finder:
            available = self.finder.everything.is_available()
            if available:
                version = self.finder.everything.get_version()
                self.es_status_label.setText(f"Everything: 已连接 ({version})")
                self.es_status_label.setStyleSheet("color: #2e7d32; padding: 4px 8px; border-radius: 3px; font-weight: bold; background-color: #e8f5e9;")
            else:
                self.es_status_label.setText("Everything: 未连接")
                self.es_status_label.setStyleSheet("color: #c62828; padding: 4px 8px; border-radius: 3px; font-weight: bold; background-color: #fdeaea;")

    def show_about(self):
        QMessageBox.about(self, "关于", 
            "重复文件清理工具 v1.0\n\n"
            "功能特性:\n"
            "• 使用 Everything 快速搜索文件\n"
            "• 通过文件大小、修改时间、指纹(xxHash+SHA256)三重校验\n"
            "• 使用 NTFS 符号链接替换重复文件，原路径仍可访问\n"
            "• 支持硬链接、符号链接、目录联接\n\n"
            "依赖: Everything (仅需安装主程序，es.exe 已内置)")

    def log(self, message: str):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f'<span style="color:#888">[{timestamp}]</span> {message}')
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def format_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def load_window_state(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)

    def save_window_state(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())

    def closeEvent(self, event):
        self.save_window_state()
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.finder.cancel()
            self.scan_worker.terminate()
            self.scan_worker.wait()
        if self.action_worker and self.action_worker.isRunning():
            self.action_worker.finder.cancel()
            self.action_worker.terminate()
            self.action_worker.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DuplicateCleaner")
    app.setOrganizationName("DuplicateCleaner")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()