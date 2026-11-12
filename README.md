# rpp_plugin_registrator

Utilities for plugin type creation, plugin registration metadata generation, and interface autogeneration for other programming languages.

By default, metadata is stored in `~/.rpp`:

- `~/.rpp/descriptions` for plugin description JSON files
- `~/.rpp/interfaces` for generated interfaces
- `~/.rpp/registry/rpp_plugin_types.registry.json` for plugin registry

## What It Does

- Creates starter plugin source files (`scaffold`)
- Prints plugin description metadata from C++ or Python plugin source (`describe`, read-only)
- Describes and registers plugins in an rpp registry file (`register`)
- Adds plugins in one step (`add` = describe + register + optional interfaces)
- Lists/removes registered plugins (`list`, `unregister`)
- Generates interfaces for other languages from a plugin description (`generate-interface`)

## Description Schema

Generated description files are JSON and include:

- Plugin identity (`plugin.id`, `plugin.name`)
- Source language and source file
- rpp factory symbols (`create_plugin`, `destroy_plugin`)
- Interface method signatures for cross-language generation

## Usage

Run all commands from this folder:

```bash
python3 rpp_registrator.py <command> [args]
```

For an editable install:

```bash
pip install -e .
```

Initialize the default `~/.rpp` structure:

```bash
python3 rpp_registrator.py init-home
```

### 1. Scaffold a Plugin Type

Create a C++ plugin skeleton:

```bash
python3 rpp_registrator.py scaffold \
  --language cpp \
  --plugin-id echo \
  --output ../rpp_core/plugins/echo_plugin.cpp
```

Create a Python plugin skeleton:

```bash
python3 rpp_registrator.py scaffold \
  --language python \
  --plugin-id my_py_plugin \
  --output ./examples/my_py_plugin.py
```

### 2. Preview Plugin Description (Read-Only)

From C++ source:

```bash
python3 rpp_registrator.py describe \
  ../rpp_core/plugins/echo_plugin.cpp
```

From Python source:

```bash
python3 rpp_registrator.py describe \
  ./examples/my_py_plugin.py
```

This command prints JSON to stdout and does not modify files.

### 3. Register Plugin Source into rpp Registry

```bash
python3 rpp_registrator.py register \
  ../rpp_core/plugins/echo_plugin.cpp
```

This command:

- infers description from source
- writes/updates `~/.rpp/descriptions/<plugin_id>.plugin.json`
- updates `~/.rpp/registry/rpp_plugin_types.registry.json`

Register from an existing description JSON file:

```bash
python3 rpp_registrator.py register \
  ~/.rpp/descriptions/echo.plugin.json
```

Register all plugin descriptions from a folder:

```bash
python3 rpp_registrator.py register \
  --folder ~/.rpp/descriptions
```

### 4. Add a Plugin in One Step

```bash
python3 rpp_registrator.py add \
  ../rpp_core/plugins/echo_plugin.cpp \
  --interface-language cpp \
  --interface-language python
```

This command:

- creates or updates the plugin description in `~/.rpp/descriptions`
- registers the plugin in `~/.rpp/registry/rpp_plugin_types.registry.json`
- optionally generates interfaces in `~/.rpp/interfaces`

### 5. Manage Registered Plugins

List registered plugins:

```bash
python3 rpp_registrator.py list
```

Remove plugin from registry:

```bash
python3 rpp_registrator.py unregister echo
```

### 6. Autogenerate Interfaces for Other Languages

Generate Python protocol:

```bash
python3 rpp_registrator.py generate-interface \
  ~/.rpp/descriptions/echo.plugin.json \
  --target-language python \
  --output ~/.rpp/interfaces/echo_plugin.py
```

Generate C++ interface header:

```bash
python3 rpp_registrator.py generate-interface \
  ~/.rpp/descriptions/echo.plugin.json \
  --target-language cpp \
  --output ~/.rpp/interfaces/echo_plugin.hpp
```

## Notes

- Plugin types may bind a local, non-generic state struct with
  `$Anot.lifecycleState("Estimate")`. Native Python callbacks receive the
  generated dataclass; C++ uses the generated owning `Estimate_Native` value
  through `LifecyclePlugin<State>`. Without the annotation, activation and
  deactivation callbacks take no state argument.
- Generated adapter clients are concrete for both stateful and stateless types.
  Their lifecycle callbacks report unsupported remote control until lifecycle
  RPC is implemented; ordinary domain-method RPC remains available. Regenerate
  adapters and rebuild C++ artifacts with the matching runtime.
- Generated C++ interface headers (`<Type>.hpp`) keep adapter implementations
  separate so optimized native calls do not introduce RPC linkage dependencies.
  Code constructing adapters must explicitly include `<Type>_Adapter_Client.hpp`
  or `<Type>_Adapter_Server.hpp`; each adapter header includes its interface.
  The registrator includes both when building the plugin-type shared library.
  Refresh existing plugin types to regenerate these headers for all libraries,
  including `rpp_control` and `rpp_localization`.
- C++ extraction is heuristic and expects plugins similar to `rpp::Plugin` implementations in `rpp_core`.
- Python extraction expects a class deriving from `Plugin`.
- The registry file is upsert-based: registering the same `plugin.id` replaces the previous entry.

## C++ compilation

`BUILD_TYPE=RelWithDebInfo` is the default: validation uses an optimized
plugin with debug symbols for GDB metadata extraction, and registration reuses
that binary. The GDB helper executable always retains an unoptimized debug build.
With `Debug`, validation and registration also reuse the same symbol-rich
binary, preserving the explicit request for an unoptimized debug build.
Only `Release` uses a separate debug plugin for metadata extraction, then
recompiles with Release optimization before installation. Plugin types use
the selected profile directly.

Select a profile with `rpp registry config set BUILD_TYPE RelWithDebInfo`,
then re-register the affected libraries. CMake's build type does not control
registration.

The GUI plugin table has a read-only **Debug** checkbox for each plugin,
showing whether its recorded `BuildType` is Debug. The tooltip shows the
registered mode, or Unknown for plugins registered before mode tracking.
Each language backend decides how to apply the requested mode.

**Register in Debug** selects the mode for individual plugin registration and
refresh, plugin-type registration, and whole-library registration and refresh.
It is unchecked by default (Release), including generated plugin-type libraries.
`refresh_plugin_library(name, build_type="Debug")` similarly applies
one build type to every plugin; `register_plugin_from_source(path, name,
build_type="Release")` selects a mode for an individual registration. Build
choices are passed to registration without changing the global `BUILD_TYPE`.

GUI registration and refresh run in a worker. The log panel shows each plugin
and plugin type starting registration and completing, with its final build type,
through queued Qt signals while management controls are disabled. Compilation,
GDB inspection, compiler commands and raw output use DEBUG logging; build failures retain their diagnostic
details in the log and an error dialog with expandable Details. GUI library
refresh stops and reports failure when a plugin fails to compile. Scrolling
and copying the log remain available. Batch operations are
processed sequentially without a busy-wait loop.
