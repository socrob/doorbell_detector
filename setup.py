from setuptools import setup, find_packages


package_name = 'doorbell_detector'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/doorbell_detector.launch.py']),
        ('share/' + package_name, ['readme.md']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='you@example.com',
    description='Doorbell detection node for ROS 2 using YAMNet.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'doorbell_node = doorbell_detector.doorbell_node:main',
        ],
    },
)