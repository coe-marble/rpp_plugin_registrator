from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from rpp_plugin_registrator.qt.csb_pyqt_plugin_manager import RPPPluginManager
from rpp_plugin_registrator.library_manager import LibraryManager

def main() -> int:
    app = QApplication(sys.argv)
    manager = LibraryManager()
    window = RPPPluginManager(manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
