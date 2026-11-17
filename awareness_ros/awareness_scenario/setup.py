import os

from setuptools import setup

package_name = 'awareness_scenario'


def scenario_files(top):
    """Every file under top, installed at the same place under share/."""
    return [(os.path.join('share', package_name, folder), [os.path.join(folder, name) for name in names])
            for folder, _, names in os.walk(top) if names]


setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml']),
    ] + scenario_files('household'),
    install_requires=['setuptools'],
    zip_safe=True,
    entry_points={'console_scripts': [f'world = {package_name}.world:main',
                                    f'executor = {package_name}.executor:main']},
)
