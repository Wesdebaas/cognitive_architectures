from glob import glob
from setuptools import find_packages, setup

package_name = 'goal_awareness_scenario'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*')),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='wessel',
    maintainer_email='wremmelzwaan@tudelft.nl',
    description='Package for goal awareness scenario',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'ground_truth_localization = goal_awareness_scenario.ground_truth_localization:main',
        ],
    },
)
