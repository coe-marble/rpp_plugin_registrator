
import json
import os
from pathlib import Path
import re
from typing import Dict, Any, List, Optional, Tuple
import shutil
import sys
import subprocess

from rpp_plugin_registrator.registry_config import (
    get_app_interfaces_path,
    get_app_registry_path,
    get_setting
)

from rpp_plugin_registrator.plugin_descriptors.core import (
    PluginInfo, PluginRegisterData, PluginRegistrationResult, PluginTypeInfo
)


from .cpp_helpers import (
    dummy_cpp_plugin_source_for_debug_symbols,
    gdb_analyze_source_template,
    get_cpp_imports_and_libraries_for_library,
    get_cpp_imports_for_rpp,
    get_dependency_source_files_for_compilation,
    get_plugin_type_shared_library_path,
    get_plugin_type_shared_library_flags,
    get_cpp_shared_libraries_path,
    get_rpp_cpp_core_shared_library_path,
    get_tmp_dir_for_compilation,
    register_cpp_plugin_source,
    register_cpp_plugin_type_source
)


def wrap_cpp_source_to_plugin_type_structure(source_file: str,
        out_dir: Path, class_name: str, lib_name: str) -> str:
    wrapped_source = register_cpp_plugin_type_source()
    source = wrapped_source.format(class_name=class_name,
            plugin_type_source_file=source_file, lib_name=lib_name)
    dest_file = out_dir / f"{class_name}__.cpp"
    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(source)
    return str(dest_file)


def wrap_cpp_source_to_plugin_structure(source_file: str,
        out_dir: Path, class_name: str, lib_name: str, plugin_type: str) -> str:
    wrapped_source = register_cpp_plugin_source()
    source = wrapped_source.format(class_name=class_name,
            lib_namespace="", plugin_type=plugin_type, source_file=source_file)
    dest_file = out_dir / f"{class_name}__.cpp"
    with open(dest_file, "w", encoding="utf-8") as f:
        f.write(source)
    return str(dest_file)


def _compile_rpp_file(source_files: List[str], out_dir: Path,
        import_flags: List[str],  linked_libs: List[str], class_name: str,
        suppress_warnings: bool = True, as_shared_lib: bool = True,
        print_to_console: bool = False, verbose: bool = False) -> Tuple[Optional[str], List[str], Path]:
    try:
        warning_flags = ["-Wno-unused-variable"] if suppress_warnings else []
        source_file = source_files[0]  # Assuming the first source file is the main one
        shared_lib_flags = []
        if as_shared_lib:
            out_file_path = out_dir / f"{class_name}.so"
            if sys.platform.startswith("win"):
                shared_lib_flags = ["/LD", "/nologo", "/EHsc"]
            else:
                shared_lib_flags = ["-shared", "-fPIC"]
        else:
            out_file_path = out_dir / f"{class_name}.out"

        out_file_flag = ["-o", str(out_file_path)]
        if sys.platform.startswith("win"):
            compile_cmd = ["cl", "/Z7"] + shared_lib_flags \
                    + import_flags + warning_flags + out_file_flag + source_files + linked_libs
        else:
            compile_cmd = ["g++", "-std=c++17", "-g"] + shared_lib_flags \
                    + import_flags + warning_flags + out_file_flag + source_files + linked_libs

        if verbose:
            print(f"Full compile command:\n{' '.join(compile_cmd)}\n\n")
        if print_to_console:
            result = subprocess.run(compile_cmd, check=True)
        else:
            result = subprocess.run(compile_cmd, check=True, \
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            return f"Compilation failed for plugin class '{class_name}'" \
                + f" in file '{source_file}': {result.stderr.decode()}", compile_cmd, out_file_path
    except subprocess.CalledProcessError as e:
        full_command = " ".join(compile_cmd)
        return f"Error during compilation of class '{class_name}'" \
            + f" in file '{source_file}'.\nCommand: {full_command}" \
            + f"\nError: {str(e)}\n{e.stderr.decode('utf-8')}", compile_cmd, out_file_path
    return None, compile_cmd, out_file_path


def _get_common_cpp_linker_flags() -> List[str]:
    return ["-Wl,-z,defs", "-lcapnp", "-lcapnp-rpc", "-lkj", "-lkj-async"]



def compile_cpp_plugin_type(source_file:str, plugin_type_info: PluginTypeInfo,
        out_dir: Path, suppress_warnings: bool = True,
        print_to_console: bool = False, verbose: bool = False) -> Tuple[Optional[str], List[str], Path]:

    info = plugin_type_info.info
    class_name = info.get("ClassName")
    plugin_type_library = info.get("Library")
    imports = get_cpp_imports_for_rpp()
    linked_libs = _get_common_cpp_linker_flags()
    rpp_cpp_core_path, rpp_cpp_core_lib_name = \
        get_rpp_cpp_core_shared_library_path()

    linked_libs += [f"-L{rpp_cpp_core_path}", f"-l{rpp_cpp_core_lib_name}"]

    use_ros2 = get_setting("USE_ROS2_COMPILATION")
    if use_ros2:
        linked_libs += ["-DUSE_ROS2_COMPILATION=1"]

    wrapped = wrap_cpp_source_to_plugin_type_structure(source_file,
            out_dir, class_name, plugin_type_library)
    source_files = [str(wrapped)]
    dependencies = get_dependency_source_files_for_compilation(
            plugin_type_library=plugin_type_library,
            dependencies=plugin_type_info.parse_data.dependencies)
    for dep in dependencies:
        if dep not in source_files:
            source_files.append(dep)

    return _compile_rpp_file(
        source_files=source_files,
        out_dir=out_dir,
        import_flags=[f"-I{imp}" for imp in imports],
        linked_libs=linked_libs,
        class_name=class_name,
        suppress_warnings=suppress_warnings,
        print_to_console=print_to_console,
        verbose=verbose
    )

def compile_cpp_plugin(source_file: PluginInfo,
        library_name: str, plugin_type_name: str, plugin_type_library: str,
        out_dir: Path, class_name: str = None, suppress_warnings: bool = True,
        print_to_console: bool = False, verbose: bool = False) -> Tuple[Optional[str], List[str], Path]:
    if class_name is None:
        class_name = Path(source_file).stem
    wrapped = wrap_cpp_source_to_plugin_structure(source_file,
            out_dir, class_name, library_name, plugin_type_name)
    imports = get_cpp_imports_for_rpp()
    includes, lib_dirs, libs_to_link = \
        get_cpp_imports_and_libraries_for_library(library_name)
    linked_libs = _get_common_cpp_linker_flags()
    flags = get_plugin_type_shared_library_flags(plugin_type_name)
    linked_libs += flags
    linked_libs += [f"-L{lib_dir}" for lib_dir in lib_dirs]
    linked_libs += [f"-l{lib}" for lib in libs_to_link]
    imports += includes

    return _compile_rpp_file(
        source_files=[str(wrapped)],
        out_dir=out_dir,
        class_name=class_name,
        import_flags=[f"-I{imp}" for imp in imports],
        linked_libs=linked_libs,
        suppress_warnings=suppress_warnings,
        print_to_console=print_to_console,
        verbose=verbose
    )

def register_cpp_plugin(plugin_info: PluginInfo) -> PluginRegistrationResult:
    """
    Registers a C++ plugin based on the provided description.

    Args:
        description (Dict[str, Any]): A dictionary containing the plugin description.
    """
    description = plugin_info.info
    source_file = description.get("SourceFile")
    class_name = description.get("ClassName")
    library = description.get("Library")
    tmp_out_dir = get_tmp_dir_for_compilation(source_file, class_name)
    if not tmp_out_dir.exists():
        tmp_out_dir.mkdir(parents=True, exist_ok=True)
        plugin_type_library = plugin_info.validation_data.plugin_type_library
        plugin_type = plugin_info.validation_data.plugin_type
        compile_error, compile_cmd, _ = compile_cpp_plugin(
            source_file=source_file,
            library_name=library,
            plugin_type_library=plugin_type_library,
            plugin_type_name=plugin_type,
            out_dir=tmp_out_dir,
            class_name=class_name,
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

def unregister_cpp_plugin(plugin_info: Dict[str, Any]) -> bool:
    """
    Unregisters a C++ plugin based on the provided plugin information.

    Args:
        plugin_info (Dict[str, Any]): A dictionary containing the plugin information.
    """
    shared_libs_path = get_cpp_shared_libraries_path(plugin_info.get("Library"), is_plugin=True)
    dest_path = shared_libs_path / f"{plugin_info.get('ClassName')}.so"
    if dest_path.exists():
        dest_path.unlink()
    return True


def generate_cpp_plugin_interface(plugin_type_info: PluginTypeInfo) -> None:
    """
    Registers a C++ plugin interface based on the provided plugin type information.

    Args:
        plugin_type_info (Dict[str, Any]): A dictionary containing the plugin type information.
    """
    description = plugin_type_info.info
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
            shutil.rmtree(str(tmp_out_dir))
            raise RuntimeError(
                f"Failed to compile C++ plugin '{class_name}'.\n"
                    + f"Error: {compile_error}")

    dest_path = get_cpp_shared_libraries_path(description["Library"], is_plugin=False)
    shutil.move(tmp_out_dir / f"{class_name}.so", dest_path / f"{class_name}.so")

    if tmp_out_dir.exists():
        shutil.rmtree(str(tmp_out_dir))

def remove_cpp_plugin_interface(plugin_type_info: PluginTypeInfo) -> None:
    """
    Unregisters a C++ plugin interface based on the provided plugin type information.

    Args:
        plugin_type_info (Dict[str, Any]): A dictionary containing the plugin type information.
    """
    # For now, we don't have any specific unregistration logic for C++ plugin interfaces.
    # This function is a placeholder for future implementation.
    return None


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
    gdb_env = os.environ.copy()
    rpp_cpp_core_path = get_setting("RPP_CPP_CORE_PATH")
    if rpp_cpp_core_path:
        existing_library_path = gdb_env.get("LD_LIBRARY_PATH")
        gdb_env["LD_LIBRARY_PATH"] = os.pathsep.join(
            filter(None, [rpp_cpp_core_path, existing_library_path]))
    try:
        result = subprocess.run(
            gdb_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=gdb_env)
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
