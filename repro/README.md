# Reproduction: bare library name resolves to a folder

`LibraryManager.get_library_path("TestLib")` and `get_library_info("TestLib")` return
a folder `./TestLib` in the working directory instead of the registered library
`TestLib`, when that folder is also a valid plugin library.

`repro/repro_library_name.py` registers `TestLib` in a temporary RPP home, copies it to
`workdir/TestLib` with an extra `Marker` key in `package.json`, changes into `workdir`
and resolves the bare name. It prints `PASS` (exit 0) or `FAIL` (exit 1).

## Run

Inside the registrator test environment (the CI container with the registrator installed):

    cd <rpp_dev>/src/rpp_plugin_registrator
    python repro/repro_library_name.py

Expected on `develop`: `FAIL`, `get_library_path` returns `.../workdir/TestLib` and
`get_library_info` has `Marker`. Expected with the fix
(branch `fix/registered-library-name-first`): `PASS`.

Check the fix: `git checkout fix/registered-library-name-first -- rpp_plugin_registrator/library_manager.py`
and run again.
