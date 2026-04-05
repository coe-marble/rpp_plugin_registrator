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

- C++ extraction is heuristic and expects plugins similar to `rpp::Plugin` implementations in `rpp_core`.
- Python extraction expects a class deriving from `RPP_Plugin` with both `name(self)` and `execute(self, ...)` methods.
- The registry file is upsert-based: registering the same `plugin.id` replaces the previous entry.
