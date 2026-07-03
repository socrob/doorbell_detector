from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    device = LaunchConfiguration('device')
    threshold = LaunchConfiguration('threshold')
    consecutive = LaunchConfiguration('consecutive')
    top_k = LaunchConfiguration('top_k')

    return LaunchDescription([
        DeclareLaunchArgument(
            'device',
            default_value='',
            description='External microphone device index or name. Empty means default input device.',
        ),
        DeclareLaunchArgument(
            'threshold',
            default_value='0.5',
            description='Aggregate confidence threshold for doorbell detection.',
        ),
        DeclareLaunchArgument(
            'consecutive',
            default_value='2',
            description='Number of positive windows required before detection.',
        ),
        DeclareLaunchArgument(
            'top_k',
            default_value='1',
            description='Number of YAMNet top classes to log.',
        ),

        Node(
            package='doorbell_detector',
            executable='doorbell_node',
            name='doorbell_node',
            output='screen',
            arguments=[
                '--source', 'alsa',
                '--device', device,
                '--threshold', threshold,
                '--consecutive', consecutive,
                '--top-k', top_k,
            ],
        ),
    ])