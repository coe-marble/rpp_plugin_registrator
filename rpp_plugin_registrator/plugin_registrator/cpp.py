
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import shutil
import sys
import subprocess
import re, json

from rpp_plugin_registrator.plugin_descriptors.cpp import get_cpp_imports_for_rpp
from rpp_plugin_registrator.registry_paths import get_app_interfaces_path, get_app_registry_path

from rpp_plugin_registrator.plugin_descriptors.core import (
    PluginInfo, PluginRegisterData, PluginRegistrationResult, PluginTypeInfo
)

from .templates.register_cpp_plugin_type_source import REGISTER_CPP_PLUGIN_TYPE_SOURCE_TEMPLATE
from .templates.register_cpp_plugin_source import REGISTER_CPP_PLUGIN_SOURCE_TEMPLATE
from .templates.dummy_cpp_source_for_debug_symbols import DUMMY_CPP_SOURCE_FOR_DEBUG_SYMBOLS_TEMPLATE
from .templates.gdb_analyze_source import GDB_ANALYZE_SOURCE_TEMPLATE


def get_plugin_type_shared_library_path(plugin_type_library: str, plugin_type_class_name: str) -> Path:
    registry_path = get_app_registry_path()
    plugin_shared_library_path = registry_path / "cpp" / "shared" / \
            plugin_type_library / "plugin_types" / f"{plugin_type_class_name}.so"
    return plugin_shared_library_path.relative_to(registry_path)

def get_dependency_source_files_for_compilation(plugin_type_library: str) -> List[str]:
    interfaces = get_app_interfaces_path()
    # TODO: For now, capnp generated files are hardcoded
    # TODO: Should be smarter. Only compile the necessary files for the plugin type and its dependencies
    capnp_generated_dir = Path(interfaces) / "cpp" / "capnp_gen" / plugin_type_library
    return sorted([str(f) for f in capnp_generated_dir.glob("*.c++") if f.is_file()])
    # plugin_type_source_name = Path(plugin_type_source_file).name
    # a = Path(capnp_generated_dir / f"{plugin_type_source_name}.c++").exists()
    # return [str(capnp_generated_dir / f"{plugin_type_source_name}.c++")]

def register_cpp_plugin_type_source() -> str:
    return REGISTER_CPP_PLUGIN_TYPE_SOURCE_TEMPLATE

def register_cpp_plugin_source() -> str:
    return REGISTER_CPP_PLUGIN_SOURCE_TEMPLATE

def dummy_cpp_plugin_source_for_debug_symbols() -> str:
    return DUMMY_CPP_SOURCE_FOR_DEBUG_SYMBOLS_TEMPLATE

def gdb_analyze_source_template() -> str:
    return GDB_ANALYZE_SOURCE_TEMPLATE

def get_tmp_dir_for_compilation(source_file: str, class_name: str) -> Path:
    source_path = Path(source_file)
    tmp_out_dir = source_path.parent / f"tmp_{class_name}"
    return tmp_out_dir

def wrap_cpp_source_to_plugin_structure(source_file: str,
        out_dir: Path, class_name: str, lib_name: str, plugin_type: str, is_plugin: bool) -> str:
    if is_plugin:
        wrapped_source = register_cpp_plugin_source()
        source = wrapped_source.format(class_name=class_name, plugin_type=plugin_type, source_file=source_file)
    else:
        wrapped_source = register_cpp_plugin_type_source()
        source = wrapped_source.format(class_name=class_name, plugin_type_source_file=source_file, lib_name=lib_name)
    dest_file = out_dir / f"{class_name}__.cpp"
    with open(dest_file, "w") as f:
        f.write(source)
    return str(dest_file)


def _compile_rpp_file(source_files: List[str], out_dir: Path,
        import_flags: List[str],  linked_libs: List[str], class_name: str,
        suppress_warnings: bool = True, as_shared_lib: bool = True) -> Tuple[Optional[str], List[str], Path]:
    try:
        warning_flags = ["-Wno-unused-variable"] if suppress_warnings else []
        source_file = source_files[0]  # Assuming the first source file is the main one
        shared_lib_flags = []
        if as_shared_lib:
            out_file_path = out_dir / f"{class_name}.so"
            if sys.platform == "win32":
                shared_lib_flags = ["/LD", "/nologo", "/EHsc"]
            else:
                shared_lib_flags = ["-shared", "-fPIC"]
        else:
            out_file_path = out_dir / f"{class_name}.out"

        out_file_flag = ["-o", str(out_file_path)]
        if sys.platform == "win32":
            compile_cmd = ["cl", "/Z7"] + shared_lib_flags \
                    + import_flags + warning_flags + out_file_flag + source_files + linked_libs
        else:
            compile_cmd = ["g++", "-std=c++17", "-g"] + shared_lib_flags \
                    + import_flags + warning_flags + out_file_flag + source_files + linked_libs
        result = subprocess.run(compile_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            return f"Compilation failed for plugin class '{class_name}'" \
                + f" in file '{source_file}': {result.stderr.decode()}", compile_cmd
    except Exception as e:
        full_command = " ".join(compile_cmd)
        return f"Error during compilation of plugin class '{class_name}'" \
            + f" in file '{source_file}'.\nCommand: {full_command}\nError: {str(e)}", compile_cmd, out_file_path
    return None, compile_cmd, out_file_path

def compile_cpp_plugin_type(source_file:str, plugin_type_info: PluginTypeInfo,
        out_dir: Path, suppress_warnings: bool = True) -> Tuple[Optional[str], List[str], Path]:

    class_name = plugin_type_info.get("ClassName")
    plugin_type = plugin_type_info.get("PluginType")
    plugin_type_library = plugin_type_info.get("Library")
    imports = get_cpp_imports_for_rpp()
    linked_libs = ["-lcapnp", "-lcapnp-rpc", "-lkj", "-lkj-async"]

    wrapped = wrap_cpp_source_to_plugin_structure(source_file,
            out_dir, class_name, plugin_type_library, plugin_type, False)
    source_files = [str(wrapped)] \
        + get_dependency_source_files_for_compilation(plugin_type_library=plugin_type_library)

    return _compile_rpp_file(
        source_files=source_files,
        out_dir=out_dir,
        import_flags=[f"-I{imp}" for imp in imports],
        linked_libs=linked_libs,
        class_name=class_name,
        suppress_warnings=suppress_warnings
    )

def compile_cpp_plugin(plugin_info: PluginInfo,
        plugin_type_name: str, plugin_type_library: str,
        out_dir: Path, suppress_warnings: bool = True) -> Tuple[Optional[str], List[str], Path]:
    class_name = plugin_info.info.get("ClassName")
    source_file = plugin_info.info.get("SourceFile")
    lib_name = plugin_type_library
    wrapped = wrap_cpp_source_to_plugin_structure(source_file,
            out_dir, class_name, lib_name, plugin_type_name, True)
    imports = get_cpp_imports_for_rpp()
    # plugin_type_shared_lib_path = get_cpp_shared_libraries_path(plugin_type_library, is_plugin=False)
    # _, plugin_type_class_name = plugin_type_name.split("::")[-2:]
    linked_libs = ["-lcapnp", "-lcapnp-rpc", "-lkj", "-lkj-async"]
    # linked_libs += [f"-L{plugin_type_shared_lib_path}", f"-l:{plugin_type_class_name}.so"]
    return _compile_rpp_file(
        source_files=[str(wrapped)],
        out_dir=out_dir,
        class_name=class_name,
        import_flags=[f"-I{imp}" for imp in imports],
        linked_libs=linked_libs,
        suppress_warnings=suppress_warnings
    )


def get_cpp_shared_libraries_path(library_name: str, is_plugin: bool = True) -> Path:
    """Get the path to the shared libraries for a C++ plugin."""
    registry_path = get_app_registry_path()
    dest_path = registry_path / "cpp" / "shared" / library_name
    if is_plugin:
        dest_path = dest_path / "plugins"
    else:
        dest_path = dest_path / "plugin_types"
    if not dest_path.exists():
        dest_path.mkdir(parents=True, exist_ok=True)
    return dest_path

def get_cpp_plugin_info_string_from_debug_symbols(
            shared_lib_path: Path, class_name: str) -> Dict[str, Any]:
    path = get_tmp_dir_for_compilation(shared_lib_path.parent, class_name)
    dummy_source = dummy_cpp_plugin_source_for_debug_symbols()
    gdb_source = gdb_analyze_source_template()
    dummy_source_file = path / f"dummy_{class_name}.cpp"
    with open(dummy_source_file, "w", encoding="utf-8") as f:
        dummy_source_formatted = dummy_source.format(
            plugin_source_file=str(shared_lib_path),
            class_name=class_name
        )
        f.write(dummy_source_formatted)

    compile_error, compile_cmd, out_file = _compile_rpp_file(
        source_files=[str(dummy_source_file)],
        out_dir=path,
        import_flags=[],
        linked_libs=[f"-L{shared_lib_path.parent}", f"-l:{shared_lib_path.name}"],
        class_name=f"dummy_{class_name}",
        suppress_warnings=True,
        as_shared_lib=False
    )

    gdb_source_file = path / f"gdb_analyze_{class_name}.gdb"
    with open(gdb_source_file, "w", encoding="utf-8") as f:
        gdb_source_formatted = gdb_source.format(
            dummy_file_path=str(out_file),
            so_path=str(shared_lib_path),
            class_name=class_name
        )
        f.write(gdb_source_formatted)
    if compile_error:
        raise RuntimeError(
            "Failed to compile dummy C++ plugin for extracting parameters of "
            + f"'{class_name}' from shared library '{shared_lib_path}'.\n"
            + f"Compilation command: {' '.join(compile_cmd)}\n"
            + f"Error: {compile_error}")

    gdb_cmd = ["gdb", "-batch", "-x", str(gdb_source_file)]
    try:
        result = subprocess.run(
            gdb_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(
                f"GDB analysis failed for plugin class '{class_name}' "
                 + f"in shared library '{shared_lib_path}': {result.stderr.decode()}")
        output = result.stdout.decode()
    except Exception as e:
        full_command = " ".join(gdb_cmd)
        raise RuntimeError(
            f"Error during GDB analysis of plugin class '{class_name}' "
             + f"in shared library '{shared_lib_path}'."
             + f"\nCommand: {full_command}\nError: {str(e)}") from e
    return output


def extract_plugin_metadata(shared_lib_path: Path, class_name: str) -> dict:

    info_str = get_cpp_plugin_info_string_from_debug_symbols(shared_lib_path, class_name)

    if "[ERROR DURING GDB ANALYSIS]" in info_str:
        raise RuntimeError(f"Error during GDB analysis of plugin class '{class_name}' "
            + f"in shared library '{shared_lib_path}': {info_str}")

    #
    result = re.search(r"RESULT_START(.*?)RESULT_END", info_str, re.DOTALL)

    result_str = result.group(1).strip() if result else ""
    result = json.loads(result_str) if result_str else {}


    return result


def register_cpp_plugin(plugin_info: PluginInfo) -> PluginRegistrationResult:
    """
    Registers a C++ plugin based on the provided description.

    Args:
        description (Dict[str, Any]): A dictionary containing the plugin description.
    """
    description = plugin_info.info
    source_file = description.get("PluginPath")
    class_name = description.get("ClassName")
    tmp_out_dir = get_tmp_dir_for_compilation(source_file, class_name)
    if not tmp_out_dir.exists():
        tmp_out_dir.mkdir(parents=True, exist_ok=True)
        plugin_type_library = plugin_info.validation_data.plugin_type_library
        plugin_type = plugin_info.validation_data.plugin_type
        compile_error, compile_cmd, _ = compile_cpp_plugin(
            plugin_info=plugin_info,
            plugin_type_library=plugin_type_library,
            plugin_type_name=plugin_type,
            out_dir=tmp_out_dir,
            suppress_warnings=True
        )
        if compile_error:
            raise RuntimeError(f"Failed to compile C++ plugin '{class_name}' from source file '{source_file}'.\n"
                            f"Compilation command: {' '.join(compile_cmd)}\n"
                            f"Error: {compile_error}")

    shared_libs_path = get_cpp_shared_libraries_path(description.get("Library"), is_plugin=True)
    dest_path = shared_libs_path / f"{class_name}.so"
    shared_lib_path = tmp_out_dir / f"{class_name}.so"
    metadata = extract_plugin_metadata(shared_lib_path, class_name)
    shutil.move(shared_lib_path, dest_path)

    if tmp_out_dir.exists():
        shutil.rmtree(str(tmp_out_dir))


    registry_path = get_app_registry_path()
    dest_path_relative = dest_path.relative_to(registry_path)
    plugin_type_shared_lib_path = get_plugin_type_shared_library_path(
        plugin_info.validation_data.plugin_type_library,
        plugin_info.validation_data.plugin_type_class_name
    )
    return PluginRegistrationResult(
        success=True,
        message=f"C++ plugin '{class_name}' registered successfully.",
        register_data=PluginRegisterData(
            plugin_shared_library_path=str(dest_path_relative),
            plugin_type_shared_library_path=str(plugin_type_shared_lib_path),
            plugin_metadata=metadata
        )
    )

def unregister_cpp_plugin(plugin_info: Dict[str, Any]) -> None:
    """
    Unregisters a C++ plugin based on the provided plugin information.

    Args:
        plugin_info (Dict[str, Any]): A dictionary containing the plugin information.
    """
    shared_libs_path = get_cpp_shared_libraries_path(plugin_info.get("Library"), is_plugin=True)
    dest_path = shared_libs_path / f"{plugin_info.get('ClassName')}.so"
    if dest_path.exists():
        dest_path.unlink()


def generate_cpp_plugin_interface(plugin_type_info: Dict[str, str]) -> None:
    """
    Registers a C++ plugin interface based on the provided plugin type information.

    Args:
        plugin_type_info (Dict[str, Any]): A dictionary containing the plugin type information.
    """
    description = plugin_type_info
    class_name = description.get("ClassName")
    lib_name = description.get("Library")
    hpp_source_file = get_app_interfaces_path() / "cpp" / "rpp_plugin_types" / lib_name / f"{class_name}.hpp"
    tmp_out_dir = get_tmp_dir_for_compilation(hpp_source_file, class_name)
    if not tmp_out_dir.exists():
        tmp_out_dir.mkdir(parents=True, exist_ok=True)
        compile_error, compile_cmd, _ = compile_cpp_plugin_type(
            source_file=hpp_source_file,
            plugin_type_info=plugin_type_info,
            out_dir=tmp_out_dir,
            suppress_warnings=True
        )
        if compile_error:
            raise RuntimeError(f"Failed to compile C++ plugin '{class_name}' from source file '{hpp_source_file}'.\n"
                            f"Compilation command: {' '.join(compile_cmd)}\n"
                            f"Error: {compile_error}")

    dest_path = get_cpp_shared_libraries_path(description["Library"], is_plugin=False)
    shutil.move(tmp_out_dir / f"{class_name}.so", dest_path / f"{class_name}.so")

    if tmp_out_dir.exists():
        shutil.rmtree(str(tmp_out_dir))

def remove_cpp_plugin_interface(plugin_type_info: Dict[str, Any]) -> None:
    """
    Unregisters a C++ plugin interface based on the provided plugin type information.

    Args:
        plugin_type_info (Dict[str, Any]): A dictionary containing the plugin type information.
    """
    # For now, we don't have any specific unregistration logic for C++ plugin interfaces.
    # This function is a placeholder for future implementation.
    return None