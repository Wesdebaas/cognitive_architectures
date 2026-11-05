from setuptools import setup

package_name = 'awareness_replay'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml', 'plugin.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
)
