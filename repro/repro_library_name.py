"""A bare library name must refer to the registered library, not to a folder of that name."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

from rpp_plugin_registrator import library_manager as libraries
from rpp_plugin_registrator import registry_config as rp

tmp = Path(tempfile.mkdtemp())
home = tmp / "rpp-home"
(home / "libraries").mkdir(parents=True)
rp.RPP_HOME = home
rp.load_and_set_config = Mock()

manager = libraries.LibraryManager(rpp_home=home, skip_layout_check=True)
registered = Path(manager.get_or_create_plugin_library("TestLib").path)

# A second valid library with the same name in the working directory.
workdir = tmp / "workdir"
workdir.mkdir()
local = workdir / "TestLib"
shutil.copytree(registered, local)
package = json.loads((local / "package.json").read_text(encoding="utf-8"))
package["Marker"] = "local-folder"
(local / "package.json").write_text(json.dumps(package), encoding="utf-8")
os.chdir(workdir)

path = Path(manager.get_library_path("TestLib"))
info = manager.get_library_info("TestLib")
print("registered library:", registered)
print("get_library_path('TestLib'):", path)
print("get_library_info('TestLib') has Marker:", "Marker" in info)

ok = path == registered and "Marker" not in info
print("PASS" if ok else "FAIL: the folder in the working directory hides the registered library")
shutil.rmtree(tmp)
sys.exit(0 if ok else 1)
