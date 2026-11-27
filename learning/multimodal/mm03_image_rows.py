"""Gather camera frames from the original immutable NPY files shared by all seeds."""
from bisect import bisect_right

import numpy as np
import torch


class MappedFrames:
    def __init__(self):
        self.blocks = []
        self.ends = []
        self.nbytes = 0
        self.dtype = None

    def append(self, path, frames):
        arr = np.load(path, allow_pickle=False, mmap_mode="r")
        if arr.ndim < 1 or len(arr) != frames or arr.dtype.hasobject:
            raise ValueError(f"Image/time count or dtype differs in {path}")
        if not self.blocks:
            self.blocks.append(np.zeros((1, *arr.shape[1:]), dtype=arr.dtype))
            self.ends.append(1)
            self.nbytes = self.blocks[0].nbytes
        if self.blocks[0].shape[1:] != arr.shape[1:]:
            raise ValueError(f"Inconsistent image layout in {path}")
        self.dtype = arr.dtype if self.dtype is None else np.result_type(self.dtype, arr.dtype)
        # from_file closes the descriptor after mmap. Thousands of episodes can
        # share the kernel's clean file pages under the ordinary open-file limit.
        backing = torch.from_file(str(path), shared=False, size=path.stat().st_size,
                                  dtype=torch.uint8).numpy()
        view = np.ndarray(arr.shape, dtype=arr.dtype, buffer=backing, offset=arr.offset,
                          order="F" if arr.flags.f_contiguous and not arr.flags.c_contiguous else "C")
        view.setflags(write=False)
        self.blocks.append(view)
        self.ends.append(self.ends[-1] + frames)
        self.nbytes += view.nbytes

    def gather(self, indices):
        if indices.ndim != 1:
            raise ValueError("Expected a one-dimensional camera batch")
        images = []
        for index in indices.tolist():
            if index < 0 or index >= self.ends[-1]:
                raise IndexError(index)
            block = bisect_right(self.ends, index)
            start = self.ends[block - 1] if block else 0
            images.append(self.blocks[block][index - start])
        array = np.stack(images) if images else self.blocks[0][:0].copy()
        return torch.from_numpy(array.astype(self.dtype, copy=False))
