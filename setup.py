from setuptools import find_packages, setup


setup(
    name="rpp-plugin-registrator",
    version="0.1.0",
    description="RPP plugin registrator",
    packages=find_packages(include=["rpp_plugin_registrator", "rpp_plugin_registrator.*"]),
    package_dir={"": "."},
    include_package_data=True,
    install_requires=["PyQt6"],
)
