#! /usr/bin/env python3
import os
import sys
import time
from datetime import datetime
from enum import Enum
from typing import List

from PySide2 import QtCore, QtWidgets, QtGui
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class DrawingStyle(Enum):
    NONE = "none"
    ELLIPSE = "ellipse"
    PEN = "pen"
    RECT = "rect"


class Config:
    filename: str = os.path.join(os.path.expanduser("~"), ".config", "screenshot-manager", "config.ini")

    screenshot_source_folder_use: bool = None
    screenshot_source_folder_path: str = None
    screenshot_source_filelist_use: bool = None
    screenshot_source_filelist_path: str = None

    @staticmethod
    def load():
        settings = QtCore.QSettings(Config.filename, QtCore.QSettings.IniFormat)

        settings.beginGroup("source-folder")
        Config.screenshot_source_folder_use = Config.to_boolean(str(settings.value("use", defaultValue=False)))
        Config.screenshot_source_folder_path = str(settings.value("path"))
        settings.endGroup()

        settings.beginGroup("source-filelist")
        Config.screenshot_source_filelist_use = Config.to_boolean(str(settings.value("use", defaultValue=False)))
        Config.screenshot_source_filelist_path = str(settings.value("path"))
        settings.endGroup()

    @staticmethod
    def to_boolean(string: str):
        return string.lower() in ["1", "yes", "true", "on"]

    @staticmethod
    def save():
        settings = QtCore.QSettings(Config.filename, QtCore.QSettings.IniFormat)

        settings.beginGroup("source-folder")
        settings.setValue("use", Config.screenshot_source_folder_use)
        settings.setValue("path", Config.screenshot_source_folder_path)
        settings.endGroup()

        settings.beginGroup("source-filelist")
        settings.setValue("use", Config.screenshot_source_filelist_use)
        settings.setValue("path", Config.screenshot_source_filelist_path)
        settings.endGroup()


class ScreenshotEditor(QtWidgets.QGraphicsView):
    items_changed = QtCore.Signal()

    def __init__(self, parent, image_path):
        super().__init__(parent)

        self.image_path = image_path
        self.changed = False
        self.items: List[QtWidgets.QGraphicsItem] = []
        self.redo_items: List[QtWidgets.QGraphicsItem] = []
        self.mouse_pressed = False
        self.previous_point = None
        self.drawing_style = DrawingStyle.PEN
        self.scene = QtWidgets.QGraphicsScene(self)
        self.photo = QtWidgets.QGraphicsPixmapItem()
        self.scene.addItem(self.photo)
        self.setScene(self.scene)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(30, 30, 30)))
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self.photo.setPixmap(QtGui.QPixmap(image_path))
        self.fitInView()

        self.draw_pen = QtGui.QPen(QtCore.Qt.red, 3, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)

    def fitInView(self, scale=True):
        rect = QtCore.QRectF(self.photo.pixmap().rect())
        if not rect.isNull():
            self.setSceneRect(rect)
            unity = self.transform().mapRect(QtCore.QRectF(0, 0, 1, 1))
            self.scale(1 / unity.width(), 1 / unity.height())
            viewrect = self.viewport().rect()
            scenerect = self.transform().mapRect(rect)
            factor = min(viewrect.width() / scenerect.width(), viewrect.height() / scenerect.height())
            self.scale(factor, factor)

    def mousePressEvent(self, event):
        if self.photo.isUnderMouse():
            self.mouse_pressed = True
            self.previous_point = self.mapToScene(event.pos())

            if self.drawing_style == DrawingStyle.PEN:
                self.add_item(self.scene.createItemGroup([]))
            elif self.drawing_style == DrawingStyle.ELLIPSE:
                self.add_item(self.scene.addEllipse(self.previous_point.x(), self.previous_point.y(), 0, 0, self.draw_pen))
            elif self.drawing_style == DrawingStyle.RECT:
                self.add_item(self.scene.addRect(self.previous_point.x(), self.previous_point.y(), 0, 0, self.draw_pen))

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.mouse_pressed = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.mouse_pressed and self.photo.isUnderMouse():
            current_point = self.mapToScene(event.pos())

            if self.drawing_style == DrawingStyle.PEN:
                # last item is a QGraphicsItemGroup previously added in mousePressEvent
                item_group: QtWidgets.QGraphicsItemGroup = self.items[-1]
                item_group.addToGroup(self.scene.addLine(self.previous_point.x(), self.previous_point.y(), current_point.x(), current_point.y(), self.draw_pen))

                self.previous_point = current_point
                self.changed = True
            elif self.drawing_style in [DrawingStyle.ELLIPSE, DrawingStyle.RECT]:
                # last item is a QGraphicsEllipseItem or QGraphicsRectItem previously added in mousePressEvent (both having a setRect method)
                item = self.items[-1]

                item.setRect(self.previous_point.x(), self.previous_point.y(), current_point.x() - self.previous_point.x(), current_point.y() - self.previous_point.y())
                self.changed = True

        super().mouseMoveEvent(event)

    def resizeEvent(self, *args, **kwargs):
        self.fitInView()

    def set_draw_pen_width(self, width):
        self.draw_pen.setWidth(width)

    def render_to_image(self):
        image = QtGui.QImage(self.scene.width(), self.scene.height(), QtGui.QImage.Format_RGB32)

        painter = QtGui.QPainter(image)
        self.scene.render(painter)
        painter.end()

        return image

    def save(self):
        self.render_to_image().save(self.image_path)
        self.changed = False
        pass

    def copy_to_clipboard(self):
        QtGui.QClipboard().setImage(self.render_to_image())

    def add_item(self, item):
        self.items.append(item)
        self.redo_items.clear()
        self.items_changed.emit()

    def undo(self):
        if self.items:
            item = self.items.pop()
            self.redo_items.append(item)
            self.scene.removeItem(item)
            self.items_changed.emit()

    def redo(self):
        if self.redo_items:
            item = self.redo_items.pop()
            self.items.append(item)
            self.scene.addItem(item)
            self.items_changed.emit()

    def set_drawing_style(self, style):
        self.drawing_style = style


class WatchdogFilesystemHandler(FileSystemEventHandler):
    def __init__(self, on_created: callable = None, on_deleted: callable = None, on_modified: callable = None):
        super().__init__()

        self.on_created_callback = on_created
        self.on_deleted_callback = on_deleted
        self.on_modified_callback = on_modified

    def on_created(self, event):
        if event.is_directory:
            return

        if not self.on_created_callback:
            return

        self.on_created_callback(event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            return

        if not self.on_deleted_callback:
            return

        self.on_deleted_callback(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return

        if not self.on_modified_callback:
            return

        self.on_deleted_callback(event.src_path)
        self.on_created_callback(event.dest_path)

    def on_modified(self, event):
        if event.is_directory:
            return

        if not self.on_modified_callback:
            return

        self.on_modified_callback(event.src_path)


class WatchdogFileModificationHandler(FileSystemEventHandler):
    def __init__(self, callback: callable, paths: List[str]):
        super().__init__()

        self.callback = callback
        self.paths = paths

    def on_modified(self, event):
        if event.is_directory:
            return

        if event.src_path in self.paths:
            self.callback(event.src_path)


class ScreenshotListItem(QtWidgets.QListWidgetItem):
    def __init__(self, file_path):
        super().__init__()

        self.file_path = file_path
        self.timestamp = None
        self.image: QtGui.QImage = None
        self.image_size: QtCore.QSize = None

        self.load()

    def load(self):
        self.image = QtGui.QImage(self.file_path)
        self.image_size = self.image.size()
        self.timestamp = os.path.getmtime(self.file_path)

        self.setText("\n".join([
            os.path.basename(self.file_path),
            datetime.fromtimestamp(self.timestamp).strftime("%c"),
            "{} x {}".format(self.image_size.width(), self.image_size.height())
        ]))

        self.setIcon(QtGui.QIcon(QtGui.QPixmap(self.image)))
        self.setToolTip(self.file_path)

    def __lt__(self, other: "ScreenshotListItem"):
        return self.timestamp > other.timestamp


class ScreenshotList(QtWidgets.QListWidget):
    def __init__(self):
        super().__init__()

        self.old_filelist = set()

        self.setViewMode(QtWidgets.QListView.ListMode)
        self.setSelectionMode(QtWidgets.QListWidget.ExtendedSelection)
        self.setIconSize(QtCore.QSize(256, 256))
        self.setResizeMode(QtWidgets.QListView.Adjust)

        self.load_screenshots()

        self.observer = Observer()
        self.reload_file_watcher()

    def load_screenshots(self):
        self.clear()

        if Config.screenshot_source_folder_use and os.path.isdir(Config.screenshot_source_folder_path):
            now = time.time()

            for root, directories, files in os.walk(Config.screenshot_source_folder_path):
                for file in files:
                    full_path = os.path.join(root, file)

                    if os.path.getmtime(full_path) < now - 86400:
                        continue

                    self.add_file(full_path)

        if Config.screenshot_source_filelist_use and os.path.isfile(Config.screenshot_source_filelist_path):
            self.update_from_filelist()

    def reload_file_watcher(self):
        self.observer.unschedule_all()

        if Config.screenshot_source_folder_use and os.path.isdir(Config.screenshot_source_folder_path):
            # Monitor filesystem for new files
            self.observer.schedule(WatchdogFilesystemHandler(on_created=self.add_file, on_modified=self.add_file, on_deleted=self.remove_file), Config.screenshot_source_folder_path, True)

        if Config.screenshot_source_filelist_use:
            self.observer.schedule(WatchdogFileModificationHandler(self.update_filelist, [Config.screenshot_source_filelist_path]), os.path.dirname(Config.screenshot_source_filelist_path))

        self.observer.start()

    def update_from_filelist(self):
        new_filelist = set()

        if os.path.isfile(Config.screenshot_source_filelist_path):
            with open(Config.screenshot_source_filelist_path, "r") as file:
                for line in file.readlines():
                    file_path = line.strip()
                    if not len(file_path) or not os.path.isfile(file_path):
                        continue

                    new_filelist.add(file_path)

        added_files = new_filelist - self.old_filelist
        removed_files = self.old_filelist - new_filelist

        self.old_filelist = new_filelist

        for file_path in added_files:
            self.add_file(file_path)

        for file_path in removed_files:
            self.remove_file(file_path)

    def add_file(self, file_path):
        self.remove_file(file_path)
        self.addItem(ScreenshotListItem(file_path))
        self.sortItems()

    def remove_file(self, file_path):
        for row in range(self.count()):
            item: ScreenshotListItem = self.item(row)
            if item.file_path == file_path:
                self.takeItem(row)
                self.sortItems()
                break


class SettingsWindow(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.screenshot_source_folder_use: QtWidgets.QCheckBox = None
        self.screenshot_source_folder_path: QtWidgets.QLineEdit = None
        self.screenshot_source_folder_browse: QtWidgets.QPushButton = None
        self.screenshot_source_filelist_use: QtWidgets.QCheckBox = None
        self.screenshot_source_filelist_path: QtWidgets.QLineEdit = None
        self.screenshot_source_filelist_browse: QtWidgets.QPushButton = None

        self.setWindowTitle("Settings")
        self.setModal(True)

        self.dialog_layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.dialog_layout)

        self.add_screenshot_source_settings()

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.dialog_layout.addWidget(button_box)

        button_box.accepted.connect(self.save)
        button_box.rejected.connect(self.close)

        self.show()
        self.setFixedSize(self.size())

    def add_screenshot_source_settings(self):
        group_box = QtWidgets.QGroupBox("Screenshot source")
        self.dialog_layout.addWidget(group_box)

        layout = QtWidgets.QGridLayout()
        group_box.setLayout(layout)

        dir_completer = QtWidgets.QCompleter()
        dir_model = QtWidgets.QFileSystemModel(dir_completer)
        dir_model.setRootPath("/")
        dir_completer.setModel(dir_model)

        file_completer = QtWidgets.QCompleter()
        file_model = QtWidgets.QFileSystemModel(file_completer)
        file_model.setRootPath("/")
        file_completer.setModel(dir_model)

        self.screenshot_source_folder_use = QtWidgets.QCheckBox("Folder")
        self.screenshot_source_folder_use.setChecked(Config.screenshot_source_folder_use)
        self.screenshot_source_folder_use.stateChanged.connect(self.update_screenshot_source_widgets)
        layout.addWidget(self.screenshot_source_folder_use, 0, 0)

        self.screenshot_source_folder_path = QtWidgets.QLineEdit()
        self.screenshot_source_folder_path.setMinimumWidth(300)
        self.screenshot_source_folder_path.setText(Config.screenshot_source_folder_path)
        self.screenshot_source_folder_path.setCompleter(dir_completer)
        layout.addWidget(self.screenshot_source_folder_path, 0, 1)

        self.screenshot_source_folder_browse = QtWidgets.QPushButton("Browse...")
        self.screenshot_source_folder_browse.clicked.connect(self.select_screenshot_source_folder)
        layout.addWidget(self.screenshot_source_folder_browse, 0, 2)

        self.screenshot_source_filelist_use = QtWidgets.QCheckBox("Filelist")
        self.screenshot_source_filelist_use.setChecked(Config.screenshot_source_filelist_use)
        self.screenshot_source_filelist_use.stateChanged.connect(self.update_screenshot_source_widgets)
        layout.addWidget(self.screenshot_source_filelist_use, 1, 0)

        self.screenshot_source_filelist_path = QtWidgets.QLineEdit()
        self.screenshot_source_filelist_path.setMinimumWidth(300)
        self.screenshot_source_filelist_path.setText(Config.screenshot_source_filelist_path)
        self.screenshot_source_filelist_path.setCompleter(file_completer)
        layout.addWidget(self.screenshot_source_filelist_path, 1, 1)

        self.screenshot_source_filelist_browse = QtWidgets.QPushButton("Browse...")
        self.screenshot_source_filelist_browse.clicked.connect(self.select_screenshot_source_filelist)
        layout.addWidget(self.screenshot_source_filelist_browse, 1, 2)

        self.update_screenshot_source_widgets()

    def update_screenshot_source_widgets(self):
        checked = self.screenshot_source_folder_use.isChecked()
        self.screenshot_source_folder_path.setEnabled(checked)
        self.screenshot_source_folder_browse.setEnabled(checked)

        checked = self.screenshot_source_filelist_use.isChecked()
        self.screenshot_source_filelist_path.setEnabled(checked)
        self.screenshot_source_filelist_browse.setEnabled(checked)

    def select_screenshot_source_folder(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder to use", self.screenshot_source_folder_path.text(), QtWidgets.QFileDialog.DontUseNativeDialog | QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks)

        if path:
            self.screenshot_source_folder_path.setText(path)

    def select_screenshot_source_filelist(self):
        path = QtWidgets.QFileDialog.getOpenFileName(self, "Select file list to use", self.screenshot_source_filelist_path.text(), QtWidgets.QFileDialog.DontUseNativeDialog | QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks)

        if path:
            self.screenshot_source_filelist_path.setText(path)

    def save(self):
        screenshot_source_folder_path = self.screenshot_source_folder_path.text()
        screenshot_source_filelist_path = self.screenshot_source_filelist_path.text()

        if self.screenshot_source_folder_use.isChecked():
            if not screenshot_source_folder_path or not os.path.isdir(screenshot_source_folder_path):
                QtWidgets.QMessageBox.critical(self, "Invalid screenshot source folder selected", "The selected screenshot source folder is not a directory or does not exist!")
                return

        if self.screenshot_source_filelist_use.isChecked():
            if not screenshot_source_filelist_path or not os.path.isfile(screenshot_source_filelist_path):
                QtWidgets.QMessageBox.critical(self, "Invalid screenshot source file list selected", "The selected screenshot source file list is not a file or does not exist!")
                return

        Config.screenshot_source_folder_use = self.screenshot_source_folder_use.isChecked()
        Config.screenshot_source_folder_path = screenshot_source_folder_path
        Config.screenshot_source_filelist_use = self.screenshot_source_filelist_use.isChecked()
        Config.screenshot_source_filelist_path = screenshot_source_filelist_path
        Config.save()

        self.accept()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.screenshot_tabs = {}

        self.screenshot_toolbar = self.addToolBar("Screenshot")
        self.screenshot_toolbar.setMovable(False)
        self.screenshot_toolbar.setContextMenuPolicy(QtCore.Qt.PreventContextMenu)

        self.screenshot_menu = QtWidgets.QMenu("Screenshot")

        self.open_screenshot_action = QtWidgets.QAction(QtGui.QIcon.fromTheme("document-open"), "Open")
        self.open_screenshot_action.setShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return))
        self.open_screenshot_action.triggered.connect(self.open_screenshot_by_selection)
        self.screenshot_menu.addAction(self.open_screenshot_action)
        self.screenshot_toolbar.addAction(self.open_screenshot_action)

        self.copy_to_clipboard_action = QtWidgets.QAction(QtGui.QIcon.fromTheme("edit-copy"), "Copy to clipboard")
        self.copy_to_clipboard_action.triggered.connect(self.copy_to_clipboard)
        self.copy_to_clipboard_action.setShortcuts(QtGui.QKeySequence.Copy)
        self.screenshot_menu.addAction(self.copy_to_clipboard_action)
        self.screenshot_toolbar.addAction(self.copy_to_clipboard_action)

        self.screenshot_toolbar.addSeparator()

        self.screenshot_toolbar.addAction(QtGui.QIcon.fromTheme("settings-configure"), "Settings", self.open_settings)

        self.edit_toolbar = self.addToolBar("Edit")
        self.edit_toolbar.setMovable(False)
        self.edit_toolbar.setContextMenuPolicy(QtCore.Qt.PreventContextMenu)
        self.edit_toolbar.hide()

        self.edit_toolbar.addAction(QtGui.QIcon.fromTheme("document-close"), "Close", self.close_current)
        self.edit_toolbar.addSeparator()
        self.edit_toolbar.addAction(QtGui.QIcon.fromTheme("document-save"), "Save", self.edit_save).setShortcuts(QtGui.QKeySequence.Save)
        self.edit_toolbar.addAction(QtGui.QIcon.fromTheme("edit-copy"), "Copy to clipboard", self.edit_copy_to_clipboard).setShortcuts(QtGui.QKeySequence.Copy)
        self.edit_toolbar.addSeparator()
        self.undo_action = self.edit_toolbar.addAction(QtGui.QIcon.fromTheme("edit-undo"), "Undo", self.edit_undo)
        self.undo_action.setShortcuts(QtGui.QKeySequence.Undo)
        self.redo_action = self.edit_toolbar.addAction(QtGui.QIcon.fromTheme("edit-redo"), "Redo", self.edit_redo)
        self.redo_action.setShortcuts(QtGui.QKeySequence.Redo)
        self.edit_toolbar.addSeparator()

        self.drawing_style_action_group = QtWidgets.QActionGroup(self)

        drawing_style_action = self.drawing_style_action_group.addAction("None")
        drawing_style_action.setCheckable(True)
        drawing_style_action.setChecked(True)
        drawing_style_action.setData(DrawingStyle.NONE)

        drawing_style_action = self.drawing_style_action_group.addAction("Pen")
        drawing_style_action.setCheckable(True)
        drawing_style_action.setData(DrawingStyle.PEN)

        drawing_style_action = self.drawing_style_action_group.addAction("Ellipse")
        drawing_style_action.setCheckable(True)
        drawing_style_action.setData(DrawingStyle.ELLIPSE)

        drawing_style_action = self.drawing_style_action_group.addAction("Rect")
        drawing_style_action.setCheckable(True)
        drawing_style_action.setData(DrawingStyle.RECT)

        self.drawing_style_action_group.triggered.connect(lambda action: self.set_drawing_style(action.data()))
        self.edit_toolbar.addActions(self.drawing_style_action_group.actions())

        self.tab_widget = QtWidgets.QTabWidget()

        self.tab_widget.setTabsClosable(True)
        self.tab_widget.currentChanged.connect(self.tab_changed)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)

        tab_bar = self.tab_widget.tabBar()
        tab_bar.installEventFilter(self)
        tab_bar.previousMiddleIndex = -1

        self.screenshot_list = ScreenshotList()

        self.screenshot_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.screenshot_list.customContextMenuRequested.connect(self.show_screenshot_list_context_menu)

        self.tab_widget.addTab(self.screenshot_list, "Screenshots")
        tab_bar.setTabButton(0, QtWidgets.QTabBar.RightSide, None)

        self.screenshot_list.itemSelectionChanged.connect(self.update_actions)
        self.screenshot_list.itemDoubleClicked.connect(self.open_screenshot_by_selection)

        self.update_actions()

        self.setCentralWidget(self.tab_widget)
        self.resize(800, 500)
        self.showMaximized()

    def show_screenshot_list_context_menu(self, position):
        self.screenshot_menu.exec_(self.screenshot_list.mapToGlobal(position))

    def update_actions(self):
        item_selected = bool(len(self.screenshot_list.selectedItems()))

        self.open_screenshot_action.setEnabled(item_selected)
        self.copy_to_clipboard_action.setEnabled(item_selected)

    def update_edit_toolbar(self):
        screenshot_editor = self.get_active_screenshot_editor()
        if screenshot_editor is not None:
            self.undo_action.setEnabled(bool(len(screenshot_editor.items)))
            self.redo_action.setEnabled(bool(len(screenshot_editor.redo_items)))

    def open_screenshot_by_selection(self):
        item: ScreenshotListItem

        for item in self.screenshot_list.selectedItems():
            self.open_screenshot(item.file_path)

    def open_screenshot(self, image_path):
        if image_path in self.screenshot_tabs:
            screenshot_page = self.screenshot_tabs[image_path]
        else:
            screenshot_page = ScreenshotEditor(self, image_path)
            screenshot_page.items_changed.connect(self.update_edit_toolbar)
            self.screenshot_tabs[image_path] = screenshot_page
            self.tab_widget.addTab(screenshot_page, os.path.basename(image_path))

        self.tab_widget.setCurrentWidget(screenshot_page)

    def tab_changed(self):
        screenshot_editor = self.get_active_screenshot_editor()
        if screenshot_editor:
            self.screenshot_toolbar.hide()
            self.edit_toolbar.show()

            screenshot_editor.set_drawing_style(self.drawing_style_action_group.checkedAction().data())
        else:
            self.screenshot_toolbar.show()
            self.edit_toolbar.hide()

        self.update_edit_toolbar()

    def close_current(self):
        index = self.tab_widget.currentIndex()
        if index == 0:
            return False

        return self.close_tab(index)

    def close_tab(self, index):
        # Prevent closing the first tab
        if index == 0:
            return False

        screenshot_editor = self.tab_widget.widget(index)
        if screenshot_editor.changed:
            question = QtWidgets.QMessageBox()
            question.setText("The image has been modified.")
            question.setInformativeText("Do you want to save your changes?")
            question.setStandardButtons(QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)
            question.setDefaultButton(QtWidgets.QMessageBox.Save)
            response = question.exec_()
            if response == QtWidgets.QMessageBox.Save:
                screenshot_editor.save()
            elif response == QtWidgets.QMessageBox.Cancel:
                return False

        for image_path in list(self.screenshot_tabs):
            if self.screenshot_tabs[image_path] == screenshot_editor:
                del self.screenshot_tabs[image_path]

        self.tab_widget.removeTab(index)

        return True

    def closeEvent(self, event):
        for image_path in list(self.screenshot_tabs):
            screenshot_editor = self.screenshot_tabs[image_path]

            if screenshot_editor.changed:
                self.tab_widget.setCurrentWidget(screenshot_editor)

                if not self.close_current():
                    event.ignore()
                    return

        event.accept()

    def eventFilter(self, event_object, event):
        if event_object == self.tab_widget.tabBar() and event.type() in [QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease] and event.button() == QtCore.Qt.MidButton:
            tab_index = event_object.tabAt(event.pos())
            if event.type() == QtCore.QEvent.MouseButtonPress:
                event_object.previousMiddleIndex = tab_index
            else:
                if tab_index != -1 and tab_index == event_object.previousMiddleIndex:
                    self.close_tab(tab_index)
                event_object.previousMiddleIndex = -1
            return True
        return False

    def copy_to_clipboard(self):
        item: ScreenshotListItem

        mime_data = QtCore.QMimeData()

        urls = []

        for item in self.screenshot_list.selectedItems():
            urls.append(QtCore.QUrl.fromLocalFile(item.file_path))

        mime_data.setUrls(urls)

        QtGui.QClipboard().setMimeData(mime_data)

    def open_settings(self):
        settings = SettingsWindow(self)
        settings.accepted.connect(self.reload)

    def reload(self):
        self.screenshot_list.load_screenshots()
        self.screenshot_list.reload_file_watcher()

    def get_active_screenshot_editor(self):
        screenshot_editor = self.tab_widget.currentWidget()
        if isinstance(screenshot_editor, ScreenshotEditor):
            return screenshot_editor
        else:
            return None

    def edit_save(self):
        self.get_active_screenshot_editor().save()

    def edit_copy_to_clipboard(self):
        self.get_active_screenshot_editor().copy_to_clipboard()

    def edit_undo(self):
        self.get_active_screenshot_editor().undo()

    def edit_redo(self):
        self.get_active_screenshot_editor().redo()

    def set_drawing_style(self, style):
        self.get_active_screenshot_editor().set_drawing_style(style)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Screenshot Manager")

    Config.load()

    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
