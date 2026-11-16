"""Record real ROS RGB/depth reception, CameraInfo, raw samples and a preview.

Image handling runs independently from the arm controller. Header time and host
callback-entry times are retained; a video montage is not hardware alignment.
"""
import argparse
import csv
import json
import os
import queue
import resource
import signal
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rclpy.serialization import serialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from sensor_msgs.msg import Image, CameraInfo


class Recorder(Node):
    def __init__(self, args):
        super().__init__("h0_camera_recorder")
        self.args = args
        self.started = time.monotonic_ns()
        self.out = args.directory
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "samples").mkdir(exist_ok=True)
        self.f = (self.out / "stream_timing.csv").open("x", newline="")
        self.w = csv.writer(self.f)
        self.w.writerow(["stream", "index", "header_ns", "host_monotonic_ns", "host_unix_ns",
                         "frame_id", "encoding", "width", "height", "step", "is_bigendian"])
        self.frames = {k: 0 for k in ("color", "depth", "color_info", "depth_info")}
        self.report = {"boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                       "started_monotonic_ns": self.started, "started_unix_ns": time.time_ns(),
                       "use_sim_time": self.get_parameter("use_sim_time").value,
                       "dds_profile": os.environ.get("FASTRTPS_DEFAULT_PROFILES_FILE"),
                       "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION", "ROS default"),
                       "queue_drops": 0, "max_queue_size": 0, "worker_error": None,
                       "subscription_qos": "RELIABLE KEEP_LAST 10 VOLATILE (matches actual Astra publishers)",
                       "video_note": "RGB with latest received depth preview, no geometric alignment; fixed 30 fps playback, see timestamps",
                       "depth_note": "Unmodified 16UC1 sample arrays. Driver uses DEPTH_1_MM; 0 invalid. Preview only: 0.2-2 m color scale."}
        self.q = queue.Queue(maxsize=64)
        self.finish = threading.Event()
        self.worker = threading.Thread(target=self.work, name="h0-image-writer")
        self.worker.start()
        self.subs = []
        for name in self.frames:
            stream = name.split("_")[0]
            info = name.endswith("_info")
            topic = f"/{args.camera_name}/{stream}/{'camera_info' if info else 'image_raw'}"
            self.subs.append(self.create_subscription(CameraInfo if info else Image, topic,
                             lambda msg, n=name, t=topic: self.receive(n, t, msg),
                             QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)))
        self.create_timer(2, self.live)

    def receive(self, name, topic, msg):
        mono, unix = time.monotonic_ns(), time.time_ns()
        index = self.frames[name]
        self.frames[name] += 1
        header = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        self.w.writerow([name, index, header, mono, unix, msg.header.frame_id,
                         getattr(msg, "encoding", "CameraInfo"), msg.width, msg.height,
                         getattr(msg, "step", ""), getattr(msg, "is_bigendian", "")])
        try:
            self.q.put_nowait((name, topic, index, mono, unix, msg))
            self.report["max_queue_size"] = max(self.report["max_queue_size"], self.q.qsize())
        except queue.Full:
            self.report["queue_drops"] += 1

    def live(self):
        self.f.flush()
        self.report["frames"] = self.frames.copy()
        self.report["last_heartbeat_monotonic_ns"] = time.monotonic_ns()
        (self.out / "camera_live.json").write_text(json.dumps(self.report, indent=2) + "\n")

    def work(self):
        video, bag = None, None
        last_sample = {"color": -float("inf"), "depth": -float("inf")}
        info_saved, bag_topics = {}, set()
        depth_panel = np.zeros((480, 640, 3), np.uint8)
        depth_mono = None
        try:
            if self.args.bag_seconds:
                import rosbag2_py
                self.args.raw_directory.mkdir(parents=True, exist_ok=True)
                bag = rosbag2_py.SequentialWriter()
                bag.open(rosbag2_py.StorageOptions(uri=str(self.args.raw_directory / "camera_bag"), storage_id="sqlite3"),
                         rosbag2_py.ConverterOptions("", ""))
            with (self.out / "sample_index.jsonl").open("x") as sample_log, \
                    (self.out / "video_frames.csv").open("x", newline="") as vf:
                vw = csv.writer(vf)
                vw.writerow(["video_index", "color_index", "color_host_monotonic_ns", "displayed_depth_host_monotonic_ns"])
                video_index = 0
                while not self.finish.is_set() or not self.q.empty():
                    try:
                        name, topic, index, mono, unix, msg = self.q.get(timeout=.1)
                    except queue.Empty:
                        continue
                    if bag is not None and (mono - self.started) / 1e9 <= self.args.bag_seconds:
                        if topic not in bag_topics:
                            import rosbag2_py
                            bag.create_topic(rosbag2_py.TopicMetadata(name=topic,
                                type="sensor_msgs/msg/CameraInfo" if name.endswith("_info") else "sensor_msgs/msg/Image",
                                serialization_format="cdr"))
                            bag_topics.add(topic)
                        bag.write(topic, serialize_message(msg), unix)
                    if name.endswith("_info"):
                        data = message_to_ordereddict(msg)
                        static = dict(data)
                        static.pop("header")
                        if info_saved.get(name) != static:
                            path = f"{name.replace('_info', '_camera_info')}.json"
                            (self.out / path).write_text(json.dumps(data, indent=2) + "\n")
                            with (self.out / "camera_info_updates.jsonl").open("a") as f:
                                f.write(json.dumps({"stream": name, "host_monotonic_ns": mono, "message": data}) + "\n")
                            info_saved[name] = static
                        continue
                    elapsed = (mono - self.started) / 1e9
                    if name == "depth":
                        if msg.encoding != "16UC1":
                            raise ValueError(f"Unexpected depth encoding {msg.encoding}")
                        dtype = np.dtype(">u2" if msg.is_bigendian else "<u2")
                        arr = np.ndarray((msg.height, msg.width), dtype=dtype, buffer=msg.data,
                                         strides=(msg.step, 2)).astype(np.uint16, copy=True)
                        shade = np.clip((arr.astype(np.float32) - 200) * (255 / 1800), 0, 255).astype(np.uint8)
                        dep = cv2.applyColorMap(shade, cv2.COLORMAP_TURBO)
                        dep[arr == 0] = 0
                        depth_panel = np.zeros((480, 640, 3), np.uint8)
                        # Padding rather than changing aspect ratio; raw sample is never resized.
                        depth_panel[:msg.height, :msg.width] = dep
                        depth_mono = mono
                    else:
                        arr = np.ndarray((msg.height, msg.width, 3), dtype=np.uint8,
                                         buffer=msg.data, strides=(msg.step, 3, 1)).copy()
                        if msg.encoding == "rgb8":
                            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                        elif msg.encoding != "bgr8":
                            raise ValueError(f"Unexpected RGB encoding {msg.encoding}")
                        if video is None:
                            video = cv2.VideoWriter(str(self.out / "preview.avi"), cv2.VideoWriter_fourcc(*"MJPG"), 30, (1280, 480))
                            if not video.isOpened():
                                raise RuntimeError("Cannot open preview video writer")
                        canvas = np.hstack((arr, depth_panel))
                        cv2.putText(canvas, f"RGB t={elapsed:.3f}s | depth preview (unregistered)", (12, 24),
                                    cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1, cv2.LINE_AA)
                        video.write(canvas)
                        vw.writerow([video_index, index, mono, depth_mono])
                        video_index += 1
                    if elapsed - last_sample[name] >= self.args.sample_period:
                        stem = f"samples/{name}_{index:06d}"
                        if name == "depth":
                            np.save(self.out / (stem + ".npy"), arr, allow_pickle=False)
                            cv2.imwrite(str(self.out / (stem + "_preview.png")), dep)
                            ext = ".npy"
                        else:
                            cv2.imwrite(str(self.out / (stem + ".png")), arr)
                            ext = ".png"
                        sample_log.write(json.dumps({"stream": name, "index": index, "path": stem + ext,
                            "host_monotonic_ns": mono, "header_ns": msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec,
                            "encoding": msg.encoding, "width": msg.width, "height": msg.height}) + "\n")
                        sample_log.flush()
                        last_sample[name] = elapsed
                    self.report["video_frames"] = video_index
        except Exception as exc:
            self.report["worker_error"] = repr(exc)
        finally:
            if video is not None:
                video.release()
            if bag is not None:
                del bag

    def close(self):
        self.finish.set()
        self.worker.join()
        self.live()
        self.f.close()
        self.report["ended_monotonic_ns"] = time.monotonic_ns()
        self.report["max_rss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        (self.out / "camera_summary.json").write_text(json.dumps(self.report, indent=2) + "\n")
        print(json.dumps(self.report), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--raw-directory", type=Path)
    p.add_argument("--bag-seconds", type=float, default=0)
    p.add_argument("--seconds", type=float, default=0)
    p.add_argument("--sample-period", type=float, default=5)
    p.add_argument("--camera-name", default="wrist_camera")
    a = p.parse_args()
    if a.bag_seconds and a.raw_directory is None:
        p.error("--bag-seconds requires --raw-directory")
    stop = threading.Event()
    rclpy.init()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    node = Recorder(a)
    print("CAMERA_RECORDER_STARTED", a.directory, flush=True)
    try:
        while not stop.is_set() and (a.seconds == 0 or (time.monotonic_ns() - node.started) / 1e9 < a.seconds):
            rclpy.spin_once(node, timeout_sec=.1)
            if node.report["worker_error"]:
                raise RuntimeError(node.report["worker_error"])
    finally:
        node.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
