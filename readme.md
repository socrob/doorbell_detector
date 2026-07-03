# doorbell_detector

ROS 2 package for detecting doorbell-like sounds using YAMNet.

The node can read audio either from a ROS audio topic or directly from an external microphone using ALSA/sounddevice.

## Node

### `doorbell_node`

The node detects doorbell-like sounds such as bell, chime, ding-dong, buzzer, and knock.

## Topics

### Subscribed

```text
/doorbell/listen
```

Type:

```text
std_msgs/msg/Bool
```

Usage:

```text
True  -> start listening
False -> stop listening / release microphone
```

### Published

```text
/doorbell/event
```

Type:

```text
std_msgs/msg/Bool
```

Usage:

```text
True -> doorbell-like sound detected
```

## Python dependencies

Install with:

```bash
pip install -r requirements.txt
```

If `sounddevice` fails:

```bash
sudo apt install portaudio19-dev
pip install -r requirements.txt
```

## Build

```bash
cd ~/ros2_ws
colcon build --packages-select doorbell_detector
source install/setup.bash
```

## Run with ROS audio topic

```bash
ros2 run doorbell_detector doorbell_node --source ros --audio /audio/in
```

## List external microphones

```bash
ros2 run doorbell_detector doorbell_node --source alsa --list-devices
```

## Run with external microphone

```bash
ros2 run doorbell_detector doorbell_node --source alsa --device 2 --top-k 5
```

## Run with launch file

```bash
ros2 launch doorbell_detector doorbell_detector.launch.py device:=2 top_k:=5
```

## HRI usage

The HRI state machine should:

1. Publish `True` to `/doorbell/listen`.
2. Wait for `True` on `/doorbell/event`.
3. Continue the task.
4. The node releases the microphone after detection if `--release-on-fire` is enabled.