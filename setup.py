from setuptools import find_packages, setup


setup(
    name="rpp-plugin-registrator",
    version="0.1.0",
    description="RPP plugin registrator and interface generator",
    packages=find_packages(),
    include_package_data=True,
    install_requires=["PyQt6"],
    entry_points={
        "console_scripts": [
            "rpp-plugin-manager=rpp_plugin_registrator.gui:main",
        ]
    },
)
