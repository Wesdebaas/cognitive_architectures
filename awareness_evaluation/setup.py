from setuptools import setup

package_name = 'awareness_evaluation'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    entry_points={'console_scripts': [f'simulate = {package_name}.simulate:main',
                                      f'draw_moves = {package_name}.draw_moves:main']},
)
