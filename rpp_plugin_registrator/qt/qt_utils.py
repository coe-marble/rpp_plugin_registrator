import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_EDITOR = "code"

def clear_form_layout(form_layout):
    while form_layout.count():
        item = form_layout.takeAt(0)
        if item is not None:
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                sublayout = item.layout()
                if sublayout is not None:
                    clear_form_layout(sublayout)


def _existing_path(path, parent):
    from PyQt6.QtWidgets import QMessageBox

    try:
        if path is None or path == "":
            raise FileNotFoundError("No path was provided.")
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"The specified path does not exist: {resolved}")
        return resolved
    except (OSError, ValueError, TypeError) as error:
        QMessageBox.warning(parent, "Cannot open path", str(error))
        return None


def _show_readonly(path, parent):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFontDatabase
    from PyQt6.QtWidgets import (
        QDialog, QDialogButtonBox, QLabel, QMessageBox, QPlainTextEdit, QVBoxLayout,
    )

    try:
        if path.is_dir():
            entries = sorted(path.iterdir(), key=lambda entry: entry.name.casefold())
            text = "\n".join(entry.name + ("/" if entry.is_dir() else "") for entry in entries)
            text = text or "(Empty folder)"
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        QMessageBox.warning(parent, "Cannot read path", f"{path}\n\n{error}")
        return

    dialog = QDialog(parent)
    dialog.setWindowTitle(f"{path.name} — Read only")
    dialog.resize(960, 640)
    layout = QVBoxLayout(dialog)
    location = QLabel(str(path))
    location.setTextFormat(Qt.TextFormat.PlainText)
    location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(location)
    viewer = QPlainTextEdit()
    viewer.setReadOnly(True)
    viewer.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
    viewer.setPlainText(text)
    layout.addWidget(viewer)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()


def open_folder(path, parent=None):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    path = _existing_path(path, parent)
    if path is None:
        return
    # Try the associated desktop application, then fall back to a folder listing.
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        _show_readonly(path, parent)


def open_file_in_editor(path, editor=DEFAULT_EDITOR, parent=None):
    path = _existing_path(path, parent)
    if path is None:
        return
    if path.is_dir():
        open_folder(path, parent=parent)
        return

    if sys.platform in {"win32", "darwin"}:
        open_folder(path, parent=parent)
        return

    executable = shutil.which(editor or DEFAULT_EDITOR)
    if executable is not None:
        try:
            subprocess.Popen([executable, str(path)])
            return
        except OSError:
            # The executable may have disappeared or become inaccessible.
            pass
    _show_readonly(path, parent)


def do_in_thread(parent, func, on_finish):
    from PyQt6.QtCore import QObject, QThread, Qt, pyqtSlot

    class WorkerThread(QThread):
        def run(self):
            self.result, self.error = None, None
            try:
                self.result = func()
            except Exception as error:
                self.error = error

    class Completion(QObject):
        @pyqtSlot()
        def finish(self):
            # This object belongs to the GUI thread. Wait for QThread.finished
            # before releasing the worker or starting another operation.
            try:
                on_finish(worker.result, worker.error)
            finally:
                worker.deleteLater()
                self.deleteLater()

    worker = WorkerThread(parent)
    completion = Completion(parent)
    worker.finished.connect(completion.finish, Qt.ConnectionType.QueuedConnection)
    worker.start()
    return worker
