import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from rpp_plugin_registrator.registry_config import (
    get_app_interfaces_path,
    get_app_registry_path,
    get_library_manager,
    get_setting,
)



from .templates.register_cpp_plugin_type_source import REGISTER_CPP_PLUGIN_TYPE_SOURCE_TEMPLATE
from .templates.register_cpp_plugin_source import REGISTER_CPP_PLUGIN_SOURCE_TEMPLATE
from .templates.dummy_cpp_source_for_debug_symbols import DUMMY_CPP_SOURCE_FOR_DEBUG_SYMBOLS_TEMPLATE
from .templates.gdb_analyze_source import GDB_ANALYZE_SOURCE_TEMPLATE


def get_plugin_type_shared_library_flags(
        plugin_type_name: str) -> List[str]:

    lib_name, class_name = plugin_type_name.split("::")
    registry_path = get_app_registry_path()
    so_path = registry_path / \
        get_plugin_type_shared_library_path(lib_name, class_name)

    return [f"-L{so_path.parent}", f"-l:{so_path.name}"]



def get_cpp_imports_for_rpp() -> List[str]:
    interfaces = get_app_interfaces_path()
    rpp_cpp_path = Path(__file__).parent.parent.parent.parent / "rpp_cpp" / "include"

    paths = [str(Path(interfaces) / "cpp"), str(rpp_cpp_path)]
    return paths

def get_plugin_type_shared_library_path(
        plugin_type_library: str, plugin_type_class_name: str) -> Path:
    registry_path = get_app_registry_path()
    plugin_shared_library_path = registry_path / "cpp" / "shared" / \
            plugin_type_library / "plugin_types" / f"{plugin_type_class_name}.so"
    return plugin_shared_library_path.relative_to(registry_path)

def get_dependency_source_files_for_compilation(plugin_type_library: str, dependencies: List[str]) -> List[str]:
    interfaces = get_app_interfaces_path()
    capnp_generated_dir = Path(interfaces) / "cpp" / "capnp_gen" / plugin_type_library

    files = [str(f) for f in capnp_generated_dir.glob("*.c++") if f.is_file()]
    for dep in dependencies:
        lib_name, file_name = dep
        potential_file = Path(interfaces) / "cpp" / "capnp_gen" / lib_name / f"{file_name}.c++"
        if potential_file.exists():
            files.append(str(potential_file))
    return files


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


def get_cpp_shared_libraries_path(
        library_name: str, is_plugin: bool = True) -> Path:
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



def get_cpp_imports_and_libraries_for_library(
        library_name: str) -> Tuple[List[str], List[str]]:

    def parse_dependency(dep: str) -> Tuple[str, Optional[str], Optional[str]]:
        dep_name = dep
        dep_version = None
        if "==" in dep:
            dep_name, dep_version = dep.split("==")
            return (dep_name, "==", dep_version)
        elif ">=" in dep:
            dep_name, dep_version = dep.split(">=")
            return (dep_name, ">=", dep_version)
        elif "<=" in dep:
            dep_name, dep_version = dep.split("<=")
            return (dep_name, "<=", dep_version)
        elif ">" in dep:
            dep_name, dep_version = dep.split(">")
            return (dep_name, ">", dep_version)
        elif "<" in dep:
            dep_name, dep_version = dep.split("<")
            return (dep_name, "<", dep_version)
        else:
            return (dep_name, None, None)


    def check_dependency(lib_major,
            lib_minor, lib_patch, dep_major, dep_minor, dep_patch, operator):
        if operator == "==":
            return (lib_major, lib_minor, lib_patch) \
                == (dep_major, dep_minor, dep_patch)
        elif operator == ">=":
            if lib_major > dep_major:
                return True
            elif lib_major == dep_major:
                if lib_minor > dep_minor:
                    return True
                elif lib_minor == dep_minor:
                    return lib_patch >= dep_patch
            return False
        elif operator == "<=":
            if lib_major < dep_major:
                return True
            elif lib_major == dep_major:
                if lib_minor < dep_minor:
                    return True
                elif lib_minor == dep_minor:
                    return lib_patch <= dep_patch
            return False
        elif operator == ">":
            if lib_major > dep_major:
                return True
            elif lib_major == dep_major:
                if lib_minor > dep_minor:
                    return True
                elif lib_minor == dep_minor:
                    return lib_patch > dep_patch
            return False
        elif operator == "<":
            if lib_major < dep_major:
                return True
            elif lib_major == dep_major:
                if lib_minor < dep_minor:
                    return True
                elif lib_minor == dep_minor:
                    return lib_patch < dep_patch
            return False
        else:
            return True  # No operator means any version is acceptable

    def is_dependency_satisfied(
            dep_operator: str, dep_version: str, lib: Dict[str, str]) -> bool:
        if dep_operator and dep_version:
            lib_version = lib.get("Version")
            lib_major, lib_minor, lib_patch = \
                (int(x) for x in lib_version.split(".")) if lib_version else (0, 0, 0)
            dep_major, dep_minor, dep_patch = \
                (int(x) for x in dep_version.split(".")) if dep_version else (0, 0, 0)
            return check_dependency(lib_major, lib_minor, \
                lib_patch, dep_major, dep_minor, dep_patch, dep_operator)
        return True


    lm = get_library_manager()
    library_info = lm.get_library_info(library_name)
    library_path = lm.get_library_path(library_name)

    if "Dependencies" in library_info and library_info["Dependencies"]:
        libraries = lm.list_plugin_libraries()
        for dep in library_info.get("Dependencies", []):
            dep_name, dep_operator, dep_version = parse_dependency(dep)
            lib = next((lib for lib in libraries if lib["Name"] == dep_name), None)
            if lib is None:
                raise ValueError(f"Dependency '{dep}' not found in registered libraries.")
            if not is_dependency_satisfied(dep_operator, dep_version, lib):
                dep_name, dep_operator, dep_version = parse_dependency(dep)
                raise ValueError(f"Dependency '{dep_name}'"
                    + f" version does not satisfy the requirement '{dep_operator}{dep_version}'.")

    dependency_infos = []
    if "RosDependencies" in library_info and library_info["RosDependencies"]:
        ros_dependencies = library_info["RosDependencies"]

        dependency_infos.append(get_default_ros_dependencies(library_path))
        for ros_dep in ros_dependencies:
            dep_name, dep_operator, dep_version = parse_dependency(ros_dep)
            use_ros2_compilation = get_setting("USE_ROS2_COMPILATION")
            if use_ros2_compilation:
                info = try_get_ros_dependency_info(dep_name, lm)
            else:
                info = None
            if info is None:
                info = try_get_system_dependency_info(dep_name, lm)
                if info is None:
                    raise ValueError(f"ROS dependency '{dep_name}' not found in the system.")
            if not is_dependency_satisfied(dep_operator, dep_version, info):
                raise ValueError(f"ROS dependency '{dep_name}'"
                    + f" version does not satisfy the requirement '{dep_operator}{dep_version}'.")
            dependency_infos.append(info)
    merged_includes = []
    merged_lib_dirs = []
    merged_libs_to_link = []
    for info in dependency_infos:
        for inc in info.get("IncludeDirs", []):
            if inc not in merged_includes:
                merged_includes.append(inc)
        for lib_dir in info.get("LibDirs", []):
            if lib_dir not in merged_lib_dirs:
                merged_lib_dirs.append(lib_dir)
        for lib in info.get("LibsToLink", []):
            if lib not in merged_libs_to_link:
                merged_libs_to_link.append(lib)
    return merged_includes, merged_lib_dirs, merged_libs_to_link


def get_default_ros_dependencies(
        library_path: str) -> Dict[str, Any]:
    from ament_index_python.packages import (
        get_package_share_directory,
    )
    rclpy_info = get_package_share_directory("rclpy")
    ros_directory = Path(rclpy_info).parent.parent
    ros_base = f"{str(ros_directory)}/include"
    include_dirs = [ros_base]
    possible_lib_include_dir = os.path.join(library_path, "include")
    if os.path.isdir(possible_lib_include_dir):
        include_dirs.append(possible_lib_include_dir)
    include_dirs.extend([f"{os.path.join(ros_base, d)}" \
                    for d in os.listdir(ros_base) \
                        if os.path.isdir(os.path.join(ros_base, d, d))])
    lib_dirs = [os.path.join(ros_directory, "lib")]
    libs_to_link = ["rclcpp", "rcutils", "rosidl_runtime_c", "rosidl_typesupport_cpp"]
    return {
        "Name": "ros2",
        "IncludeDirs": include_dirs,
        "LibDirs": lib_dirs,
        "LibsToLink": libs_to_link
    }



def try_get_ros_dependency_info(dep_name: str, lm) -> Optional[Dict[str, Any]]:
    from ament_index_python.packages import (
        get_package_share_directory,
        PackageNotFoundError
    )

    include_dirs = []
    lib_dirs = []
    libs_to_link = []
    try:
        share_directory = get_package_share_directory(dep_name)
        info = lm.load_package_file(share_directory)
        version = info.get("Version", None)

        prefix_dir = Path(share_directory).parent.parent
        include_dirs.append(str(prefix_dir / "include" / dep_name))
        lib_dirs.append(str(prefix_dir / "lib"))
        libs_to_link.append(dep_name)
        return {
            "Name": dep_name,
            "Version": version,
            "IncludeDirs": include_dirs,
            "LibDirs": lib_dirs,
            "LibsToLink": libs_to_link
        }
    except PackageNotFoundError:
        return None


def try_get_system_dependency_info(dep_name: str, lm) -> Optional[Dict[str, Any]]:
    pkg_search_name = dep_name.replace('1g-dev', '').replace('-dev', '')

    include_dirs = []
    lib_dirs = []
    libs_to_link = []

    if sys.platform.startswith("win"):
        # Windows-specific logic to find include and lib directories
        # This is a placeholder; actual implementation may vary based on the system setup
        # TODO: Implement Windows-specific logic to find include and lib directories
        return

    cflags = subprocess.check_output(["pkg-config", "--cflags-only-I", pkg_search_name]).decode("utf-8").strip()
    libs_L = subprocess.check_output(["pkg-config", "--libs-only-L", pkg_search_name]).decode("utf-8").strip()
    libs_l = subprocess.check_output(["pkg-config", "--libs-only-l", pkg_search_name]).decode("utf-8").strip()

    version = subprocess.check_output(["pkg-config", "--modversion", pkg_search_name]).decode("utf-8").strip()

    # Parsiranje i dodavanje u liste ako putanje postoje
    if cflags:
        include_dirs.extend([p[2:] for p in cflags.split() if p.startswith("-I")])
    if libs_L:
        lib_dirs.extend([p[2:] for p in libs_L.split() if p.startswith("-L")])
    if libs_l:
        libs_to_link.extend([p[2:] for p in libs_l.split() if p.startswith("-l")])

    return {
        "Name": dep_name,
        "Version": version,
        "IncludeDirs": include_dirs,
        "LibDirs": lib_dirs,
        "LibsToLink": libs_to_link
    }