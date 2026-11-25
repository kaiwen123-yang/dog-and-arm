"""Persistent CPU inference in the separate Torch environment, using only causal sensors."""
import argparse
import struct
import subprocess
import sys

import numpy as np


class PolicyPipe:
    def __init__(self, python, checkpoint):
        self.child = subprocess.Popen(
            [str(python), "-m", __name__ if __name__ != "__main__" else "scripts.multimodal.mm02_inference",
             str(checkpoint)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        if self.child.stdout.readline() != b"READY\n":
            raise RuntimeError("Failed to initialize the MM-02 frozen actor")

    def reset(self, text, tick=0, prefix=None):
        tokens = text.encode("utf-8")
        parts = [b"R", struct.pack("<IIB", len(tokens), tick, int(prefix is not None)), tokens]
        if prefix is not None:
            parts.extend(np.asarray(x, dtype="<f4").tobytes() for x in prefix)
        self.child.stdin.write(b"".join(parts))
        self.image_time = None

    def step(self, proprio, previous, image, image_t, now):
        fresh = self.image_time != image_t
        parts = [b"A", struct.pack("<Bf", fresh, now-image_t),
                 np.asarray(proprio, dtype="<f4").tobytes(), np.asarray(previous, dtype="<f4").tobytes()]
        if fresh:
            rgb, depth, valid = image
            parts.extend((rgb.tobytes(), np.asarray(depth, dtype="<f4").tobytes(),
                          np.asarray(valid, dtype="?").tobytes()))
            self.image_time = image_t
        self.child.stdin.write(b"".join(parts))
        self.child.stdin.flush()
        response = self.child.stdout.read(92)
        if len(response) != 92:
            raise RuntimeError(f"Actor terminated at t={now}, exit={self.child.poll()}")
        return np.frombuffer(response, dtype="<f4").astype(np.float64)

    def close(self):
        self.child.stdin.close()
        self.child.stdout.close()
        if self.child.wait():
            raise RuntimeError("Actor subprocess exited with error")


def serve(checkpoint):
    import torch
    from learning.multimodal.actor import OnlinePolicy
    from scripts.multimodal.policy_worker import array

    torch.set_num_threads(1)
    policy = OnlinePolicy.from_checkpoint(checkpoint, device="cpu")
    src, dst = sys.stdin.buffer, sys.stdout.buffer
    dst.write(b"READY\n")
    dst.flush()
    while op := src.read(1):
        if op == b"R":
            n, tick, prefix = struct.unpack("<IIB", src.read(9))
            policy.reset(src.read(n).decode("utf-8"))
            policy.tick = tick
            if prefix:
                policy.proprio_history.extend(array(src, "<f4", (9, 52)))
                policy.previous_history.extend(array(src, "<f4", (9, 23)))
            rgb = depth = valid = None
        elif op == b"A":
            fresh, age = struct.unpack("<Bf", src.read(5))
            state = array(src, "<f4", (52,))
            previous = array(src, "<f4", (23,))
            if fresh:
                rgb = array(src, "u1", (64, 64, 3))
                depth = array(src, "<f4", (64, 64))
                valid = array(src, "?", (64, 64))
            raw = policy.step(rgb, depth, valid, state, previous, image_age_s=age, return_raw=True)
            dst.write(np.asarray(raw, dtype="<f4").tobytes())
            dst.flush()
        else:
            raise ValueError(f"Invalid policy command {op!r}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint")
    serve(parser.parse_args().checkpoint)
