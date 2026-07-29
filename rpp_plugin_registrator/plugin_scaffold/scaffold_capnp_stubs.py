from pathlib import Path
import os
import re
from rpp_plugin_registrator.registry_config import get_app_capnp_interfaces_path


def fix_capnp_includes(file_path: Path) -> None:
    pattern = r'#include\s+"([^"\n]+\.capnp\.h)"'

    content = file_path.read_text(encoding="utf-8")

    # Zamjenjuje pronađeno s #include "test1/naziv.capnp.h"
    # \1 ubacuje sadržaj prve zagrade (samo ime datoteke sa .capnp.h)
    new_content = re.sub(pattern, r'#include "capnp_gen/\1"', content)
    file_path.write_text(new_content, encoding="utf-8")


def scaffold_capnp_stubs(source_file: Path, lib_name: str, output_path: Path,
                         capnp_language: str, language_dir_name: str) -> None:

    capnp_dir = output_path / language_dir_name / "capnp_gen" / lib_name
    capnp_dir.mkdir(parents=True, exist_ok=True)

    # use capnp compile to generate the C++ stubs
    # Wait for completion of the subprocess to ensure that the generated files are available before proceeding
    import subprocess

    root_dir = get_app_capnp_interfaces_path()
    import_flags = [f"-I{root_dir}"]
    tmp_file_in_root = root_dir / source_file.name
    tmp_file_in_root.write_text(source_file.read_text(encoding="utf-8"), encoding="utf-8")

    try:
        cmd = ["capnp", "compile", "--src-prefix", str(tmp_file_in_root.parent),
               f"-o{capnp_language}:{str(capnp_dir)}"] + import_flags + [str(tmp_file_in_root)]
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as e:
        full_command = " ".join(e.cmd)
        raise RuntimeError(f"Failed to compile Cap'n Proto schema. Full command: \n{full_command}\nError: {e}") from e
    finally:

        assert (capnp_dir / f"{source_file.stem}.capnp.h").exists(), \
            f"Expected generated file {capnp_dir / f'{source_file.stem}.capnp.h'} not found"

        if tmp_file_in_root.exists():
            tmp_file_in_root.unlink()

    fix_capnp_includes(capnp_dir / f"{source_file.stem}.capnp.h")


    return capnp_dir