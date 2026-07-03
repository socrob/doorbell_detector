#!/usr/bin/env python3
"""Doorbell detector ROS2 node using YAMNet.

YAMNet (Google) is a pretrained AudioSet classifier with 521 classes,
including several doorbell-related ones (Doorbell, Ding-dong, Buzzer,
Door, Knock, Bell, Bicycle bell, Chime). We trigger when the *aggregate*
confidence across the doorbell-family classes exceeds a threshold across
N consecutive inference windows.

Why aggregate + consecutive: "could be any doorbell" means a single class
isn't enough (ding-dong vs buzzer vs chime). "Can't misidentify" means a
single noisy spike shouldn't trigger.

Install on perception board:
    pip install tensorflow tensorflow-hub librosa numpy

Run:
    python3 scripts/doorbell_node.py --audio /audio/in
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections import deque


# YAMNet class indices, verified against yamnet_class_map.csv.
# Knock is allowed by 2026 rulebook 5.1 as a doorbell substitute.
DOORBELL_CLASS_INDICES = (
    195,  # Bell
    198,  # Bicycle bell
    200,  # Chime
    349,  # Doorbell
    350,  # Ding-dong
    353,  # Knock
    384,  # Telephone bell ringing
    392,  # Buzzer
    477,  # Ding
)


def _aggregate_doorbell_score(scores_per_class, doorbell_class_indices=DOORBELL_CLASS_INDICES):
    """Sum the score across doorbell-family classes from a YAMNet output frame.

    Pure function. scores_per_class is a 1-D iterable indexed by class id.
    Returns clipped float in [0, 1].
    """
    total = 0.0
    for idx in doorbell_class_indices:
        if 0 <= idx < len(scores_per_class):
            total += float(scores_per_class[idx])
    return min(1.0, total)


def _confirm_event(recent_scores, threshold, n_required):
    """Decide if a doorbell event should fire given a deque of recent aggregate scores."""
    if len(recent_scores) < n_required:
        return False
    return sum(1 for s in recent_scores if s >= threshold) >= n_required


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="ros", choices=["ros", "alsa"],
                        help="ros: subscribe to AudioStamped topic; alsa: read mic directly via sounddevice")
    parser.add_argument("--audio", default="/audio/in",
                        help="audio topic (ros source only)")
    parser.add_argument("--device", default=None,
                        help="ALSA device index or name (alsa source only)")
    parser.add_argument("--list-devices", action="store_true",
                        help="list ALSA devices and exit")
    parser.add_argument("--out", default="/doorbell/event")
    parser.add_argument("--listen-cmd", default="/doorbell/listen",
                        help="Bool topic the FSM uses to gate the mic: True=listen, False=release")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="aggregate confidence to consider one window a hit")
    parser.add_argument("--consecutive", type=int, default=2,
                        help="number of consecutive hits required to fire event")
    parser.add_argument("--inference-hz", type=float, default=2.0,
                        help="run inference at most this often (YAMNet uses 0.96s windows)")
    parser.add_argument("--cooldown-sec", type=float, default=5.0,
                        help="silence the trigger for this long after a firing")
    parser.add_argument("--top-k", type=int, default=1,
                        help="log top-K classes per window (use 5 to debug what YAMNet hears)")
    parser.add_argument("--gain", type=float, default=1.0,
                        help="software multiplier applied to samples before inference")
    parser.add_argument("--window-sec", type=float, default=3.0,
                        help="seconds of audio fed to YAMNet per inference; longer catches drawn-out doorbells")
    parser.add_argument("--release-on-fire", action=argparse.BooleanOptionalAction, default=True,
                        help="release the mic after detection so STT can take it, then reopen")
    parser.add_argument("--listen-after-sec", type=float, default=60.0,
                        help="seconds to stay quiet after a fire before reopening the mic for the next guest")
    args = parser.parse_args()

    try:
        import numpy as np
        import tensorflow as tf
        import tensorflow_hub as hub
    except Exception as exc:
        print(f"missing dependency: {exc}", file=sys.stderr)
        print("install: pip install tensorflow tensorflow-hub numpy scipy", file=sys.stderr)
        sys.exit(1)

    if args.source == "alsa" or args.list_devices:
        try:
            import sounddevice as sd
        except Exception as exc:
            print(f"missing dependency: {exc}; pip install sounddevice", file=sys.stderr)
            sys.exit(1)
        if args.list_devices:
            print(sd.query_devices())
            sys.exit(0)

    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import Bool

    print("loading YAMNet from tensorflow-hub...", flush=True)
    model = hub.load("https://tfhub.dev/google/yamnet/1")

    rclpy.init()
    node = Node("doorbell_node")
    pub = node.create_publisher(Bool, args.out, 10)

    audio_buffer = []
    last_inference_t = 0.0
    last_fire_t = 0.0
    last_log_t = 0.0
    score_history: deque = deque(maxlen=max(8, args.consecutive * 2))
    src_rate = {"value": None}

    # release the mic on detection so STT can take over
    fire_event = threading.Event()
    # gated by --listen-cmd from the FSM; default on so a standalone run still listens
    listen_event = threading.Event()
    listen_event.set()

    YAMNET_RATE = 16000
    WINDOW_SAMPLES = max(15360, int(YAMNET_RATE * args.window_sec))

    def process_samples(samples_f32, rate):
        nonlocal last_inference_t, last_fire_t, last_log_t

        if src_rate["value"] is None:
            src_rate["value"] = rate or YAMNET_RATE
            node.get_logger().info(f"first audio: rate={rate}Hz samples={len(samples_f32)}")

        if rate and rate != YAMNET_RATE:
            try:
                from scipy.signal import resample_poly
                from math import gcd
                g = gcd(rate, YAMNET_RATE)
                samples_f32 = resample_poly(samples_f32, YAMNET_RATE // g, rate // g).astype(np.float32)
            except Exception as exc:
                node.get_logger().warn(f"resample failed ({rate}->{YAMNET_RATE}): {exc}; assuming 16kHz")

        audio_buffer.extend(samples_f32.tolist())
        if len(audio_buffer) < WINDOW_SAMPLES:
            return

        now = time.time()
        if now - last_inference_t < (1.0 / max(0.1, args.inference_hz)):
            if len(audio_buffer) > WINDOW_SAMPLES * 3:
                del audio_buffer[:-WINDOW_SAMPLES]
            return
        last_inference_t = now

        chunk = np.array(audio_buffer[-WINDOW_SAMPLES:], dtype=np.float32) * args.gain

        del audio_buffer[:-WINDOW_SAMPLES]

        try:
            scores, _, _ = model(chunk)
            mean_scores = scores.numpy().max(axis=0)  # max per-frame; transients survive
        except Exception as exc:
            node.get_logger().warn(f"YAMNet inference: {exc}")
            return

        agg = _aggregate_doorbell_score(mean_scores)
        score_history.append(agg)

        if now - last_log_t > 2.0 or agg >= args.threshold * 0.5:
            k = max(1, args.top_k)
            top_idxs = np.argsort(mean_scores)[::-1][:k]
            top_str = " ".join(f"{int(i)}={mean_scores[int(i)]:.2f}" for i in top_idxs)
            doorbell_scores = " ".join(
                f"{i}={mean_scores[i]:.2f}" for i in DOORBELL_CLASS_INDICES if mean_scores[i] > 0.01
            )
            node.get_logger().info(
                f"agg={agg:.2f} thr={args.threshold} hits={sum(1 for s in score_history if s>=args.threshold)}/{args.consecutive} top={top_str} bell={{{doorbell_scores}}}"
            )
            last_log_t = now

        if now - last_fire_t < args.cooldown_sec:
            return
        if _confirm_event(score_history, args.threshold, args.consecutive):
            out = Bool()
            out.data = True
            pub.publish(out)
            node.get_logger().info(
                f"DOORBELL DETECTED (agg={agg:.2f}, recent={[round(s,2) for s in score_history]})"
            )
            last_fire_t = now
            score_history.clear()
            if args.release_on_fire:
                fire_event.set()

    def on_listen(msg):
        if msg.data:
            listen_event.set()
        else:
            listen_event.clear()
        node.get_logger().info(f"listen command: {'ON' if msg.data else 'OFF'}")

    node.create_subscription(Bool, args.listen_cmd, on_listen, 10)

    if args.source == "ros":
        from audio_common_msgs.msg import AudioStamped

        def on_audio(msg):
            try:
                samples = np.frombuffer(bytes(msg.audio.data), dtype=np.int16).astype(np.float32) / 32768.0
            except Exception:
                return
            rate = int(getattr(msg.audio.info, "rate", 0) or 0)
            process_samples(samples, rate)

        node.create_subscription(AudioStamped, args.audio, on_audio, 50)
        node.get_logger().info(f"listening on ROS topic {args.audio}, publishing on {args.out}")
    else:
        device = args.device
        if device is not None:
            try:
                device = int(device)
            except ValueError:
                pass
        try:
            info = sd.query_devices(device, "input")
            device_rate = int(info["default_samplerate"])
            node.get_logger().info(f"ALSA device: {info['name']}, default_rate={device_rate}Hz")
        except Exception as exc:
            node.get_logger().error(f"sounddevice query failed: {exc}")
            sys.exit(1)

        def alsa_worker():
            blocksize = 4096
            while rclpy.ok():
                # only hold the mic while the FSM has us listening
                if not listen_event.wait(timeout=0.5):
                    continue
                if not rclpy.ok():
                    break
                audio_buffer.clear()
                try:
                    with sd.InputStream(device=device, channels=1, samplerate=device_rate,
                                        dtype="float32", blocksize=blocksize) as stream:
                        node.get_logger().info(f"mic open on {device}; listening")
                        while (rclpy.ok() and listen_event.is_set()
                               and not fire_event.is_set()):
                            data, overflowed = stream.read(blocksize)
                            if overflowed:
                                node.get_logger().warn("ALSA input overflow")
                            process_samples(data[:, 0].copy(), device_rate)
                except Exception as exc:
                    node.get_logger().error(f"ALSA stream error: {exc}")
                    time.sleep(2.0)
                    continue
                node.get_logger().info("mic released")
                if fire_event.is_set():
                    fire_event.clear()
                    listen_event.clear()  # idle until the FSM re-asks

        threading.Thread(target=alsa_worker, daemon=True).start()
        node.get_logger().info(f"capturing ALSA device={device}, publishing on {args.out}")

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
