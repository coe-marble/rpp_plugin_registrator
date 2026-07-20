from PyQt6.QtWidgets import *
from PyQt6 import uic, QtCore
import sys, os
from pathlib import Path
from rpp_plugin_registrator.plugin_type_registrator import get_plugin_types
from rpp_plugin_registrator.library_manager import LibraryManager
from rpp_plugin_registrator.qt.qt_utils import do_in_thread, open_file_in_editor, open_folder

class NewLibraryDialog(QDialog):
    def __init__(self, parent=None, title="Enter values"):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle(title)
        layout = QFormLayout(self)
        self.le = QLineEdit(self)
        self.le.setMinimumWidth(300)
        layout.addRow("Name", self.le)
        self.is_linked = QCheckBox(self)
        layout.addRow("Is Linked Library", self.is_linked)
        self.is_linked.stateChanged.connect(self.on_is_linked)
        self.browse_btn = QPushButton("Browse", self)
        self.browse_btn.clicked.connect(self.on_browse)
        hlayout = QHBoxLayout()
        self.link_path = QLineEdit(self)
        hlayout.addWidget(self.link_path)
        hlayout.addWidget(self.browse_btn)
        self.link_path_w = QWidget(self)
        self.link_path_w.setLayout(hlayout)
        layout.addRow("Link Path", self.link_path_w)
        # hide whole row initially
        layout.labelForField(self.link_path_w).setVisible(False)
        self.link_path_w.setVisible(False)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.layout = layout

    def accept(self):
        name, is_linked, link_path = self.values()
        if name is None or name.strip() == "":
            self.parent.log("Invalid library name.")
            return
        if is_linked:
            if link_path is None or link_path.strip() == "":
                self.parent.log("Invalid link path for linked library.")
                return
        return super().accept()

    def on_browse(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Link Directory", "")
        if dir_path:
            self.link_path.setText(dir_path)
    def on_is_linked(self, state):
        if state == QtCore.Qt.CheckState.Checked.value:
            self.layout.labelForField(self.link_path_w).setVisible(True)
            self.link_path_w.setVisible(True)
        else:
            self.layout.labelForField(self.link_path_w).setVisible(False)
            self.link_path_w.setVisible(False)

    def values(self):
        return [self.le.text(), self.is_linked.isChecked(), self.link_path.text()]

class RPPPluginManager(QMainWindow):
    def __init__(self, lib_manager : LibraryManager, parent=None):
        QMainWindow.__init__(self, parent=parent)

        ui_path = Path(__file__).resolve().parents[2] / "ui"
        self.ui_path = str(ui_path) if ui_path is not None else ''
        uic.loadUi(os.path.join(self.ui_path, 'plugin_manager.ui'), self)
        self.lib_manager = lib_manager
        self.plugin_type_items = []
        self.init()
        self.load_plugins()
        self.active_plugins = []
        self.libraryListWidget.setCurrentRow(0)
        self.do_in_progress = False

    def init(self):
        self.libraryListWidget.itemSelectionChanged.connect(self.on_library_selected)
        self.libraryListWidget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.pluginTypesTreeView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.pluginTypesTreeView.itemDoubleClicked.connect(self.on_plugin_type_double_clicked)
        # self.pluginTypesTreeView.itemClicked.connect(self.on_plugin_type_selected)
        self._init_plugin_table()

        # on app click, remove active plugins
        self.centralwidget.mousePressEvent = self.on_app_clicked
        self.openContextBtn.clicked.connect(self.open_context)

        self.registerComponentBtn.clicked.connect(self.register_plugin)
        self.unregisterComponentBtn.clicked.connect(self.unregister_plugin)
        self.refreshLibraryBtn.clicked.connect(self.refresh_library)
        self.unregisterLibraryBtn.clicked.connect(self.unregister_library)
        self.createLibraryBtn.clicked.connect(self.create_library)

        self.exportLibraryBtn.clicked.connect(self.export_library)
        self.installLibraryBtn.clicked.connect(self.install_library)
        self.linkLibraryBtn.clicked.connect(self.link_library)
        self.detectLibrariesFromFolderBtn.clicked.connect(self.detect_libraries_from_folder)

    def on_app_clicked(self, event):
        self.clear_selected_plugins()

    def _init_plugin_table(self):
        self.pluginTableWidget = QTableWidget(self)
        self.pluginTableWidget.setColumnCount(5)
        self.pluginTableWidget.setHorizontalHeaderLabels(["Name", "Plugin Name", "Plugin Type", "Library", "Description"])
        self.pluginTableWidget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pluginTableWidget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.pluginTableWidget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pluginTableWidget.setAlternatingRowColors(True)
        self.pluginTableWidget.horizontalHeader().setStretchLastSection(True)
        self.pluginTableWidget.itemDoubleClicked.connect(self.on_plugin_row_double_clicked)

        parent_layout = self.tabWidget.parentWidget().layout()
        parent_layout.replaceWidget(self.tabWidget, self.pluginTableWidget)
        self.tabWidget.hide()

    def _current_library_name(self):
        lib = self.get_active_library()
        if lib is not None:
            return lib
        if self.libraryListWidget.count() > 0:
            return self.libraryListWidget.item(0).text()
        return None

    def refresh_plugin_types_list(self):
        self.pluginTypesTreeView.clear()
        current_lib = self._current_library_name()
        if current_lib is None:
            return

        self.pluginTypesTreeView.setHeaderLabel(f"Plugin Types in Library '{current_lib}'")
        for plugin_type in self.plugin_types.values():
            lib = plugin_type.get("Library", None)
            if lib is None or lib != current_lib:
                continue
            _, name_in_lib = self.lib_manager.parse_plugin_name(plugin_type.get("PluginTypeName", ""))
            item_child = QTreeWidgetItem([f"{name_in_lib}"], 0)
            item_child.setData(0, QtCore.Qt.ItemDataRole.UserRole, {
                "type": "plugin_type",
                "library": lib,
                "plugin_type": plugin_type,
            })
            self.pluginTypesTreeView.addTopLevelItem(item_child)

        if self.pluginTypesTreeView.topLevelItemCount() > 0:
            self.pluginTypesTreeView.setCurrentItem(self.pluginTypesTreeView.topLevelItem(0))

    def refresh_plugin_table(self):
        current_lib = self._current_library_name()
        if current_lib is None:
            self.pluginTableWidget.setRowCount(0)
            return
        plugins = self.plugins.get(current_lib, [])

        total_count = sum(len(plugins_of_type) for plugins_of_type in plugins.values())
        self.pluginTableWidget.setRowCount(total_count)
        row = 0
        for plugin_type, plugins_of_type in plugins.items():
            for plugin in plugins_of_type:
                name_item = QTableWidgetItem(plugin.get("Name", ""))
                type_item = QTableWidgetItem(plugin.get("PluginType", ""))
                plugin_name_item = QTableWidgetItem(plugin.get("PluginName", ""))
                lib_item = QTableWidgetItem(plugin.get("Library", ""))
                desc_item = QTableWidgetItem(plugin.get("Description", ""))
                self.pluginTableWidget.setItem(row, 0, name_item)
                self.pluginTableWidget.setItem(row, 1, plugin_name_item)
                self.pluginTableWidget.setItem(row, 2, type_item)
                self.pluginTableWidget.setItem(row, 3, lib_item)
                self.pluginTableWidget.setItem(row, 4, desc_item)
                # store plugin data in the first column item
                name_item.setData(QtCore.Qt.ItemDataRole.UserRole, plugin)
                row += 1

        self.pluginTableWidget.resizeColumnsToContents()
        self.pluginTableWidget.resizeRowsToContents()

    def ask_library_path(self):

        fileName, _ = QFileDialog.getOpenFileName(self, "Select Library File", "",
                                                  "Shared Library File (*.json)")
        # check that it is package.json
        if fileName and os.path.basename(fileName) == "package.json":
            return fileName
        return None

    def log(self, msg):
        from datetime import datetime
        t_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        max_lines = 1000
        cursor = self.logTxt.textCursor()
        if self.logTxt.document().blockCount() > max_lines:
            # clear last 100 lines
            cursor.movePosition(cursor.End)
            for _ in range(100):
                cursor.select(cursor.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()
            self.logTxt.setTextCursor(cursor)
        cursor.setPosition(0)
        self.logTxt.setTextCursor(cursor)
        self.logTxt.insertPlainText(f"[{t_now}] {msg}\n")

    def register_plugin_library(self, path=None, link_install=False):
        if path is None:
            path = Path(self.ask_library_path()).parent
        if path is None:
            self.log("Invalid library file selected.")
            return
        self.log(f"Registering library from '{path}'. This may take a few moments...")

        def on_finish(result, error):
            if error is not None:
                self.log(f"Failed to register library from '{path}': {error}")
                return
            self.log("Library registered.")
            self.load_plugins()

        def run():
            self.lib_manager.register_plugin_library(Path(path), int(link_install), 0)

        self._do_fn(run, on_finish)

    def create_library(self):
        # get name and install/link and path from QInputDialog
        # name, ok = QInputDialog.getText(self, 'Create Library', 'Enter library name:')

        dlg = NewLibraryDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, is_linked, link_path = dlg.values()
        else:
            return

        self.log(f"Creating library '{name}'. This may take a few moments...")

        if is_linked:
            self.lib_manager.get_or_create_plugin_library(name, link_path)
        else:
            self.lib_manager.get_or_create_plugin_library(name)

        self.load_plugins()
        self.log(f"Library '{name}' created.")

    def install_library(self):
        self.register_plugin_library(link_install=False)

    def link_library(self):
        self.register_plugin_library(link_install=True)

    def detect_libraries_from_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory to Scan for Libraries", "")
        if not dir_path:
            self.log("Invalid directory selected.")
            return
        self.log(f"Detecting libraries in '{dir_path}'. This may take a few moments...")

        for d in Path(dir_path).iterdir():
            if str(d) == dir_path:
                continue
            # check library already registered
            if any(l['Path'] == str(d) for l in self.libraries):
                self.log(f"Library in '{d}' is already registered. Skipping...")
                continue
            # check library name already exists
            if any(l['Name'] == d.name for l in self.libraries):
                self.log(f"Library name '{d.name}' already exists. Skipping library in '{d}'...")
                continue

            if self.lib_manager.is_valid_plugin_library(d):
                self.log(f"Library detected in '{d}'. Registering...")
                self.register_plugin_library(path=d, link_install=True)

        self.load_plugins()
        self.log(f"Library detection in '{dir_path}' completed.")

    def export_library(self):
        lib = self.get_active_library()
        if lib is None:
            QMessageBox.warning(self, "Warning", "No library selected.")
            return
        export_path = QFileDialog.getExistingDirectory(self, "Select Export Directory", "")
        if not export_path:
            self.log("Invalid export directory selected.")
            return
        pass
        self.lib_manager.export_plugin_library(lib, export_path)
        self.log(f"Library '{lib}' exported to '{export_path}'.")

    def refresh_library(self):

        lib = self.get_active_library()
        if lib is None:
            QMessageBox.warning(self, "Warning", "No library selected.")
            return
        self.log(f"Refreshing library '{lib}'. This may take a few moments...")

        def on_finish(result, error):
            if error is not None:
                self.log(f"Failed to refresh library '{lib}': {error}")
                return
            self.log(f"Library '{lib}' refreshed.")
            self.load_plugins()
            self.setEnabled(True)

        def run():
            QApplication.instance().processEvents()
            self.lib_manager.refresh_plugin_library(lib, throw=False)

        self._do_fn(run, on_finish)

    def register_plugin(self):
        lib = self.get_active_library()
        if lib is None:
            QMessageBox.warning(self, "Warning", "No library selected.")
            return
        # .m, .py or .slx files
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Plugin File", "",
                                                  "Plugin Files (*.m *.py *.slx)")
        if not file_path:
            self.log("No plugin file selected.")
            return

        if file_path.endswith('.slx'):
            block_path = QInputDialog.getText(self, 'Simulink Block Path',
                                              'Enter Simulink block path (e.g., subsystem/myblock):')[0]
            if not block_path:
                self.log("Invalid Simulink block path.")
                return
        l = next((l for l in self.libraries if l['Name'] == lib), None)
        if l is None:
            QMessageBox.warning(self, "Warning", f"Library '{lib}' is not registered in the registry.")
            return
        # open folder in file explorer, for all os
        path = l.get('Path', None)
        if not file_path.startswith(path):
            # ask user to copy file to library path
            reply = QMessageBox.question(self, 'Copy Plugin File',
                                         f"The selected plugin file is not in the library path.\n"
                                         f"Do you want to copy it to the library '{lib}'?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            import shutil
            # copy file to library path
            dest_path = os.path.join(path, 'src', os.path.basename(file_path))
            shutil.copyfile(file_path, dest_path)
            file_path = dest_path
            self.log(f"Plugin file '{file_path}' copied to library '{lib}'.")

        full_plugin_path = file_path
        if file_path.endswith('.slx'):
            full_plugin_path = f"{file_path}:{block_path}"

        if not self.lib_manager.is_supported_plugin_file(file_path):
            self.log(f"Unsupported plugin file type: '{file_path}'. Only '*.py' files are supported with python backend.")
            return

        def run():
            self.lib_manager.register_plugin_from_source(full_plugin_path, lib)

        self.log(f"Registering plugin from '{file_path}' to library '{lib}'. This may take a few moments...")
        def on_finish(result, error):
            if error is not None:
                self.log(f"Failed to register plugin '{full_plugin_path}' in library '{lib}': {error}")
                return
            if result is False:
                self.log(f"Failed to register plugin '{full_plugin_path}' in library '{lib}'.")
            else:
                self.log(f"Plugin '{full_plugin_path}' registered in library '{lib}'.")
                self.load_plugins()

        self._do_fn(run, on_finish)

    def _do_fn(self, fn, on_finish):

        while self.do_in_progress:
            QtCore.QCoreApplication.processEvents()

        if self.lib_manager.is_long_library_management:
            self.do_in_progress = True
            def on_finish_wrapper(result, error):
                self.do_in_progress = False
                on_finish(result, error)
            do_in_thread(self, fn, on_finish_wrapper)
        else:
            try:
                result = fn()
                on_finish(result, None)
            except Exception as e:
                on_finish(None, e)
        self.do_in_progress = False

    def unregister_plugin(self):
        lib = self.get_active_library()
        if lib is None:
            QMessageBox.warning(self, "Warning", "No library selected.")
            return

        selected_plugins = self.active_plugins
        if not selected_plugins:
            QMessageBox.warning(self, "Warning", "No plugin selected.")
            return

        reply = QMessageBox.question(self, 'Unregister Plugin',
                                        f"Are you sure you want to unregister the selected plugin(s) from library '{lib}'?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                        QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return

        for p in selected_plugins:
            name = p.findChild(QLabel).text()
            self.lib_manager.unregister_plugin(name, lib)
            self.log(f"Plugin '{name}' unregistered from library '{lib}'.")
        self.load_plugins()

    def unregister_library(self):
        # are you sure
        if self.get_active_library() is None:
            QMessageBox.warning(self, "Warning", "No library selected.")
            return
        reply = QMessageBox.question(self, 'Unregister Library',
                                     f"Are you sure you want to unregister library '{self.get_active_library()}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.lib_manager.remove_plugin_library(self.get_active_library())
            self.load_plugins()

    def clear_selected_plugins(self):
        for p in self.active_plugins:
            # check if p is not deleted
            try:
                if p is not None and p.isVisible():
                    p.setStyleSheet("border: 1px solid transparent;")
            except:
                pass


        self.active_plugins = []

    def on_plugin_selected(self, widget):
        if widget:

            # if ctrl is pressed, allow multiple selection
            if not (QApplication.keyboardModifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
                self.clear_selected_plugins()
            # if already selected, deselect
            if widget in self.active_plugins:
                widget.setStyleSheet("border: 1px solid transparent;")
                self.active_plugins.remove(widget)
                return


            # set border only for this widget, not for its children
            widget.setStyleSheet("border: 1px solid #ff7e67;")
            for c in widget.children():
                if isinstance(c, QWidget):
                    c.setStyleSheet("border: 1px solid transparent;")
            self.active_plugins.append(widget)

    def get_active_library(self):
        selected_items = self.libraryListWidget.selectedItems()
        if selected_items:
            item = selected_items[0]
            return item.text()
        return None

    def _collect_plugin_types(self):
        return get_plugin_types()

    def open_plugin_file(self, plugin):
        path = plugin.get('PluginPath', "")
        if plugin["Type"] == 'slx':
            path = path.split(':')[0]
            self.log(f"Cannot open Simulink plugin file '{path}' from here. " \
            "Please open it from MATLAB.")
            return
        open_file_in_editor(path)

    def open_context(self):
        lib = self.get_active_library()
        if lib is None:
            try:
                lib = self.libraryListWidget.item(0).text()
            except:
                QMessageBox.warning(self, "Warning", "No library selected and no libraries available.")
                return

        l = next((l for l in self.libraries if l['Name'] == lib), None)
        # open folder in file explorer, for all os
        path = l.get('Path', None)
        if path is not None and self.lib_manager.is_valid_plugin_library(path):
            open_folder(path)
        else:
            QMessageBox.warning(self, "Warning", "Library path not found.")

    def on_plugin_double_clicked(self, plugin):
        # open plugin file
        self.open_plugin_file(plugin)

    def on_library_selected(self):
        self.refresh_plugin_types_list()
        self.refresh_plugin_table()

    def on_plugin_type_selected(self):
        self.refresh_plugin_types_list()

    def on_plugin_type_double_clicked(self, item):
        payload = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        typ = payload.get("type", None) if payload else ""
        if typ == "library":
            return
        plugin_type = payload.get("plugin_type", None) if payload else None
        if plugin_type is None:
            return
        source_file = plugin_type.get("SourceFile", None)
        if source_file is not None:
            open_file_in_editor(source_file)
        else:
            QMessageBox.warning(self, "Warning", "Library path not found.")

    def on_plugin_row_double_clicked(self, item):
        row = item.row()
        name_item = self.pluginTableWidget.item(row, 0)
        plugin = name_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if plugin:
            self.open_plugin_file(plugin)

    def fill_data(self):
        self.libraryListWidget.clear()
        for lib, p in self.plugins.items():
            item = QListWidgetItem(lib)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, p)
            self.libraryListWidget.addItem(item)

    def load_plugins(self):
        self.plugins = self.lib_manager.get_available_plugins()
        self.libraries = self.lib_manager.list_plugin_libraries()
        self.plugin_types = self._collect_plugin_types()
        self.fill_data()
        self.refresh_plugin_types_list()
        self.refresh_plugin_table()

