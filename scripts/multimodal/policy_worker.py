"""Frozen multimodal inference in the Torch environment for native MuJoCo 3.3."""
import argparse
import struct
import sys

import numpy as np
import torch

from learning.multimodal.actor import OnlinePolicy


HEADER = struct.Struct("<Bf")


def array(stream, dtype, shape):
    dtype = np.dtype(dtype)
    size = int(np.prod(shape)) * dtype.itemsize
    buf = stream.read(size)
    if len(buf) != size:
        raise EOFError("Incomplete sensor packet")
    return np.frombuffer(buf, dtype=dtype).reshape(shape).copy()


def serve(checkpoint, text):
    torch.set_num_threads(1)
    policy = OnlinePolicy.from_checkpoint(checkpoint, device="cpu")
    policy.reset(text)
    src, dst = sys.stdin.buffer, sys.stdout.buffer
    dst.write(b"READY\n")
    dst.flush()
    rgb = depth = valid = None
    while header := src.read(HEADER.size):
        new_image, age = HEADER.unpack(header)
        proprio = array(src, "<f4", (52,))
        previous = array(src, "<f4", (23,))
        if new_image:
            rgb = array(src, "u1", (64,64,3))
            depth = array(src, "<f4", (64,64))
            valid = array(src, "?", (64,64))
        if rgb is None:
            raise ValueError("First decision has no wrist exposure")
        action = policy.step(rgb,depth,valid,proprio,previous,image_age_s=age,image_valid=True,return_raw=True)
        dst.write(np.asarray(action, dtype="<f4").tobytes())
        dst.flush()


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("checkpoint")
    p.add_argument("text")
    a=p.parse_args()
    serve(a.checkpoint,a.text)
