import os
from setuptools import find_packages, setup
from glob import glob

package_name = 'hw_insight'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*')),
        (os.path.join('share', package_name, 'rviz'), glob('rviz/*')),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='hw',
    maintainer_email='toplaya@126.com',
    description='PX4/AirSim obstacle avoidance, QGC mission bridge, and mapping',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'cloud_relay = hw_insight.cloud_relay:main',
            'depth_clamp = hw_insight.depth_clamp:main',
            'avoid_node = hw_insight.avoid_node:main',
            'qgc_mission_runner = hw_insight.qgc_mission_runner:main',
        ],
    },
)
