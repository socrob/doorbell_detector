# doorbell_detector

ROS 2 package for detecting doorbell-like sounds using **YAMNet**.

This node was added for the RoboCup HRI task, where the robot waits for a doorbell-like sound before continuing the interaction. It can detect sounds such as bell, chime, ding-dong, buzzer, knock, and ding.

The node supports two audio sources:

```text
alsa  -> read directly from a local microphone using sounddevice
ros   -> subscribe to a ROS audio topic
```

For our current RoboCup setup, the tested and recommended mode is:

```text
--source alsa --device pulse
```

This uses the microphone selected in the laptop’s PulseAudio settings.



## Node

### `doorbell_node`

The node listens for doorbell-like sounds and publishes a ROS event when the aggregated YAMNet confidence passes the configured threshold.



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
True  -> start listening / open microphone
False -> stop listening / release microphone
```

Example:

```bash
ros2 topic pub --once /doorbell/listen std_msgs/msg/Bool "{data: true}"
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

Monitor detections:

```bash
ros2 topic echo /doorbell/event
```



## Installation

Create and activate a virtual environment:

```bash
python3 -m venv --system-site-packages ~/venvs/doorbell_detector
source ~/venvs/doorbell_detector/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

If `sounddevice` fails:

```bash
sudo apt install portaudio19-dev
pip install -r requirements.txt
```

Useful audio tools:

```bash
sudo apt install alsa-utils pulseaudio-utils pavucontrol
```

Build:

```bash
cd ~/ros2_ws
colcon build --packages-select doorbell_detector
source install/setup.bash
```

When running the node, remember to activate the venv first:

```bash
source ~/venvs/doorbell_detector/bin/activate
source ~/ros2_ws/install/setup.bash
```



## Setup on a new laptop

First list the available audio devices:

```bash
ros2 run doorbell_detector doorbell_node --source alsa --list-devices
```

Example:

```text
0 HD-Audio Generic: HDMI 0 (hw:0,3), ALSA (0 in, 8 out)
1 hdmi, ALSA (0 in, 8 out)
2 pulse, ALSA (32 in, 32 out)
* 3 default, ALSA (32 in, 32 out)
```

Use a device with input channels. Avoid devices with `0 in`.

For our setup, use:

```text
pulse
```

Before testing the detector, verify that the microphone records sound:

```bash
arecord -D pulse -f S16_LE -c 1 -r 16000 -d 5 -vv /tmp/mic_test.wav
aplay /tmp/mic_test.wav
```

If the recording is silent, open:

```bash
pavucontrol
```

Then go to **Input Devices**, select the correct microphone, and check that the input level moves when speaking.



## Recommended test command

Use this to quickly verify that the detector works:

```bash
ros2 run doorbell_detector doorbell_node \
  --source alsa \
  --device pulse \
  --top-k 10 \
  --threshold 0.2 \
  --consecutive 1 \
  --inference-hz 0.25 \
  --window-sec 1.5
```

In another terminal:

```bash
ros2 topic echo /doorbell/event
```

Play a doorbell sound close to the microphone.

A successful detection should print something like:

```text
DOORBELL DETECTED
```

and `/doorbell/event` should publish:

```yaml
data: true
```



## Recommended RoboCup command

After the basic test works, use a slightly safer configuration:

```bash
ros2 run doorbell_detector doorbell_node \
  --source alsa \
  --device pulse \
  --top-k 5 \
  --threshold 0.2 \
  --consecutive 2 \
  --inference-hz 0.5 \
  --window-sec 1.5
```

This requires two positive inference windows before publishing the event, reducing false positives.



## Parameters

### `--source`

Audio source.

Options:

```text
ros
alsa
```

Recommended:

```bash
--source alsa
```

### `--audio`

ROS audio topic used only with:

```bash
--source ros
```

Default:

```text
/audio/in
```

Example:

```bash
--source ros --audio /audio/in
```

For the current RoboCup setup, this mode was not the main tested path.

### `--device`

Audio input device used with:

```bash
--source alsa
```

Examples:

```bash
--device pulse
--device default
--device 2
```

Recommended:

```bash
--device pulse
```

### `--list-devices`

Lists available audio devices and exits:

```bash
ros2 run doorbell_detector doorbell_node --source alsa --list-devices
```

### `--out`

Detection output topic.

Default:

```text
/doorbell/event
```

### `--listen-cmd`

Command topic used to enable or disable listening.

Default:

```text
/doorbell/listen
```

### `--threshold`

Doorbell confidence threshold.

Lower values are more sensitive but may create false positives. Higher values are safer but may miss quiet doorbells.

Tested value:

```bash
--threshold 0.2
```

### `--consecutive`

Number of positive inference windows required before detection.

For testing:

```bash
--consecutive 1
```

For competition:

```bash
--consecutive 2
```

### `--inference-hz`

Maximum YAMNet inference rate.

Lower values use less CPU but react slower.

Tested values:

```bash
--inference-hz 0.25
--inference-hz 0.5
```

### `--window-sec`

Seconds of audio used per inference.

Tested value:

```bash
--window-sec 1.5
```

### `--top-k`

Number of top YAMNet classes printed in the logs.

Useful for debugging:

```bash
--top-k 10
```

For normal use:

```bash
--top-k 5
```

### `--gain`

Software gain applied before inference.

Default:

```bash
--gain 1.0
```

Use this only if the microphone is too quiet.

### `--cooldown-sec`

Minimum time between detections.

Default:

```bash
--cooldown-sec 5.0
```

### `--release-on-fire` / `--no-release-on-fire`

By default, the node releases the microphone after detection.

This is useful for HRI because the speech pipeline may need the microphone after the doorbell event.

Recommended:

```bash
--release-on-fire
```



## HRI usage

The HRI state machine should:

1. Publish `True` to `/doorbell/listen`.
2. Wait for `True` on `/doorbell/event`.
3. Continue the task.
4. Let the detector release the microphone after detection.
5. Start or resume speech recognition if needed.

Expected flow:

```text
WAIT_FOR_DOORBELL
  -> publish /doorbell/listen=True
  -> wait for /doorbell/event=True

DOORBELL_DETECTED
  -> detector publishes /doorbell/event=True
  -> detector releases microphone

CONTINUE_HRI_TASK
```

To listen again later:

```bash
ros2 topic pub --once /doorbell/listen std_msgs/msg/Bool "{data: true}"
```



## Troubleshooting

### `/doorbell/event` does not publish

First check the microphone:

```bash
arecord -D pulse -f S16_LE -c 1 -r 16000 -d 5 -vv /tmp/mic_test.wav
aplay /tmp/mic_test.wav
```

If the recording is silent, fix the input device in:

```bash
pavucontrol
```

### The node prints `agg=0.00` and `bell={}`

The node is running, but YAMNet is not hearing doorbell-like audio.

Check that:

* the microphone records sound;
* the selected input in `pavucontrol` is correct;
* the doorbell sound is loud enough;
* the node is using `--device pulse`.

### `Device or resource busy`

Another process is using the microphone.

Check:

```bash
sudo fuser -v /dev/snd/*
```

If PulseAudio is using the device, prefer:

```bash
--device pulse
```

instead of opening raw hardware devices.

### `sounddevice query failed`

The selected device is not available.

Re-list devices:

```bash
ros2 run doorbell_detector doorbell_node --source alsa --list-devices
```

Then use `pulse`, `default`, or another valid input device.

### TensorFlow GPU warnings

Warnings about missing GPU/CUDA libraries are usually not fatal. TensorFlow falls back to CPU, which is acceptable for this detector.

### First run may need internet

The node loads YAMNet from TensorFlow Hub. Run the node once before the competition to make sure the model is cached on the laptop.
