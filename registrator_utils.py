
def import_module_from_path(module_path: str):
    """
    Imports a Python module from a given file path.

    Args:
        module_path (str): The file path to the Python module.

    Returns:
        module: The imported Python module.

    Raises:
        ValueError: If the module cannot be found or loaded.
    """
    import importlib.util
    import os
    if not os.path.exists(module_path):
        raise ValueError(f"Module path '{module_path}' does not exist.")
    module_name = os.path.splitext(os.path.basename(module_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None:
        raise ValueError(f"Could not find module '{module_name}' at path '{module_path}'.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
