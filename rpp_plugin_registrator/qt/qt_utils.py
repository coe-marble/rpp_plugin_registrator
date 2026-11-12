import sys, os, subprocess
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


def open_folder(path):
    if path is None or not os.path.exists(path):
        raise FileNotFoundError(f"The specified path does not exist: {path}")
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

def open_file_in_editor(path, editor=DEFAULT_EDITOR):
    if editor is None:
        editor = DEFAULT_EDITOR
    if path is None or not os.path.exists(path):
        raise FileNotFoundError(f"The specified path does not exist: {path}")
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':  # macOS
        subprocess.call(['open', path])
    else:  # Linux, Unix
        # subprocess.call(['xdg-open', path])
        if Path(path).is_file():
            subprocess.call([editor, path])
        else:
            subprocess.call(['xdg-open', path])


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
