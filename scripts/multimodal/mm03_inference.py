"""One CUDA actor service for the native MM03 workers, with per-client causal histories."""
import argparse
from collections import OrderedDict, defaultdict, deque
from concurrent.futures import Future
from dataclasses import dataclass, field
import json
from multiprocessing.connection import Client, Listener
import os
from pathlib import Path
import queue
import struct
import threading
import time

import numpy as np


HISTORY = 10
HEADER = struct.Struct("<BB2f")
F4 = np.dtype("<f4")


def socket_for(root):
    return Path(root) / "service" / "policy.sock"


class PolicyClient:
    def __init__(self, checkpoint, *, kind="mm02", socket_path=None):
        self.conn = Client(str(socket_path or os.environ["MM03_INFERENCE_SOCKET"]), family="AF_UNIX")
        self.kind = kind
        self.conn.send_bytes(b"M" + json.dumps([str(Path(checkpoint).resolve()), kind]).encode())
        self._reply()
        self.proprio = deque(maxlen=HISTORY)
        self.previous = deque(maxlen=HISTORY)

    def _reply(self):
        answer = self.conn.recv_bytes(4096)
        if not answer or answer[:1] != b"O":
            raise RuntimeError(answer[1:].decode(errors="replace") if answer else "empty policy response")
        return answer[1:]

    def reset(self, text, tick=0, prefix=None):
        self.tick = tick
        self.image_time = None
        self.proprio.clear()
        self.previous.clear()
        if prefix is not None:
            p, a = map(np.asarray, prefix)
            if p.shape != (9, 52) or a.shape != (9, 23):
                raise ValueError("Expected nine actual pre-anchor observations and actions")
            self.proprio.extend(p)
            self.previous.extend(a)
        self.conn.send_bytes(b"R" + text.encode("utf8"))
        self._reply()

    def step(self, proprio, previous, image, image_t, now, *, request=None, return_aux=False):
        if not self.proprio:
            self.proprio.extend([proprio] * (HISTORY - 1))
            self.previous.extend([previous] * (HISTORY - 1))
        self.proprio.append(proprio)
        self.previous.append(previous)
        low = self.kind in ("low", "low_oracle")
        fresh = not low and self.image_time != image_t
        age = 0. if low else float(now - image_t)
        fields = [b"A", HEADER.pack(fresh, return_aux, age, self.tick * .02),
                  np.asarray(self.proprio, dtype=F4).tobytes(), np.asarray(self.previous, dtype=F4).tobytes()]
        if low:
            request = np.asarray(request, dtype=F4)
            expected = 4 if self.kind=="low_oracle" else 2
            if request.shape != (expected,):
                raise ValueError(f"{self.kind} expects {expected} request/diagnostic values")
            fields.append(request.tobytes())
        if fresh:
            rgb, depth, valid = image
            fields.extend([np.asarray(rgb, np.uint8).tobytes(), np.asarray(depth, F4).tobytes(),
                           np.asarray(valid, np.bool_).tobytes()])
            self.image_time = image_t
        self.conn.send_bytes(b"".join(fields))
        answer = self._reply()
        self.tick += 1
        nraw, nhigh, nest = answer[:3]
        data = np.frombuffer(answer[3:], F4).astype(np.float64)
        if nraw + nhigh + nest != len(data):
            raise ValueError("Malformed batched policy output")
        if return_aux:
            return dict(raw=data[:nraw], high=data[nraw:nraw+nhigh], estimate=data[nraw+nhigh:])
        return data[:nraw]

    def close(self):
        self.conn.close()


@dataclass
class Stream:
    kind: str
    key: tuple
    instruction: str = ""
    visual: object = None


@dataclass
class Request:
    client: Stream
    body: bytes
    arrival: float = field(default_factory=time.monotonic)
    done: Future = field(default_factory=Future)


class FrozenTaskGraph:
    """Replay a frozen task head at the callers' actual batch width on the inference GPU."""

    def __init__(self, actor, inputs):
        import torch
        self.actor = actor
        self.inputs = tuple(t.clone() for t in inputs)
        stream = torch.cuda.Stream(device=inputs[0].device)
        current = torch.cuda.current_stream(inputs[0].device)
        stream.wait_stream(current)
        with torch.cuda.stream(stream):
            # Initialize the linear-algebra handles on the stream used for capture.
            actor.infer_features(*self.inputs)
            actor.infer_features(*self.inputs)
        current.wait_stream(stream)
        self.graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph, stream=stream, capture_error_mode="thread_local"):
            parts = actor.infer_features(*self.inputs)
            self.widths = tuple(t.shape[-1] for t in parts)
            self.output = torch.cat(parts, dim=-1)

    def run(self, inputs):
        for fixed, current in zip(self.inputs, inputs, strict=True):
            fixed.copy_(current)
        self.graph.replay()
        rows = self.output.cpu().numpy()
        first, second, _ = self.widths
        return rows[:, :first], rows[:, first:first+second], rows[:, first+second:]


class ModelBatcher:
    def __init__(self, root, device, max_batch, window_ms, *, task_graphs=True):
        self.root, self.device, self.max_batch = root, device, max_batch
        self.window = window_ms / 1000.
        self.pending = queue.Queue(maxsize=2*max_batch)
        self.models = OrderedDict()
        self.use_task_graphs = task_graphs
        self.graphs = OrderedDict()
        self.graph_calls = 0
        self.calls = self.batches = self.max_seen = 0
        self.wait_sum = 0.
        self.last_stats = time.monotonic()

    def model(self, stream):
        key = stream.key
        if key not in self.models:
            path, size, stamp, kind = key
            st = Path(path).stat()
            if (size, stamp) != (st.st_size, st.st_mtime_ns):
                raise RuntimeError(f"Policy checkpoint changed while in use: {path}")
            if kind == "mm02":
                from learning.multimodal.actor import load_actor
                actor, vocab, _ = load_actor(path, self.device)
            elif kind == "task":
                from learning.multimodal.mm03_task import load_task_actor
                actor, vocab, _ = load_task_actor(path, self.device)
            else:
                from learning.multimodal.mm03_low import LowPolicy
                actor, vocab = LowPolicy.load(path, self.device), None
            self.models[key] = (actor.eval(), vocab, {})
        self.models.move_to_end(key)
        while len(self.models) > 32:
            removed, _ = self.models.popitem(last=False)
            for entry in [k for k in self.graphs if k[0] == removed]:
                del self.graphs[entry]
        return self.models[key]

    def client_loop(self, conn):
        stream = None
        try:
            while True:
                msg = conn.recv_bytes(65536)
                op, body = msg[:1], msg[1:]
                if op == b"M":
                    name, kind = json.loads(body)
                    if kind not in ("mm02", "task", "low", "low_oracle"):
                        raise ValueError(f"Unknown policy family {kind!r}")
                    path = Path(name).resolve(strict=True)
                    st = path.stat()
                    stream = Stream(kind, (str(path), st.st_size, st.st_mtime_ns, kind))
                    reply = b""
                elif op == b"R" and stream is not None:
                    stream.instruction, stream.visual = body.decode(), None
                    reply = b""
                elif op == b"A" and stream is not None:
                    item = Request(stream, body)
                    self.pending.put(item)
                    reply = item.done.result()
                else:
                    raise ValueError("Expected initialized policy stream")
                conn.send_bytes(b"O" + reply)
        except (EOFError, ConnectionError, BrokenPipeError):
            pass
        except Exception as exc:
            import traceback
            traceback.print_exc()
            try:
                conn.send_bytes(b"E" + str(exc).encode()[:4000])
            except OSError:
                pass
        finally:
            conn.close()

    def infer(self, group):
        import torch
        actor, vocab, texts = self.model(group[0].client)
        def tensor(arrays):
            return torch.as_tensor(np.stack(arrays), device=self.device)
        histories, actions, rates, timing, exposures = [], [], [], [], []
        fresh_indices = []
        for i, req in enumerate(group):
            body = memoryview(req.body)
            fresh, aux, age, now = HEADER.unpack_from(body)
            off = HEADER.size
            def take(dtype, shape):
                nonlocal off
                array = np.frombuffer(body, dtype=dtype, offset=off, count=int(np.prod(shape))).reshape(shape)
                off += array.nbytes
                return array
            histories.append(take(F4, (10, 52)))
            actions.append(take(F4, (10, 23)))
            timing.append([age, 1., now])
            if req.client.kind in ("low", "low_oracle"):
                rates.append(take(F4, (4 if req.client.kind=="low_oracle" else 2,)))
            if fresh:
                fresh_indices.append(i)
                exposures.append((take("u1",(64,64,3)), take(F4,(64,64)), take("?",(64,64))))
            if off != len(body):
                raise ValueError("Wrong multimodal input byte count")
        p, a = tensor(histories), tensor(actions)
        kind = group[0].client.kind
        values = None
        high = estimate = None
        if kind in ("low", "low_oracle"):
            commands = tensor(rates)
            raw = (actor(p, a, commands[:, :2], velocity_override=commands[:, 2:]) if kind=="low_oracle"
                   else actor(p, a, commands))
            if any(x.body[1] for x in group):
                estimate = actor.estimate(p, a)
        else:
            if exposures:
                visual = actor.encode_visual(*(tensor(part) for part in zip(*exposures)))
                for j, index in enumerate(fresh_indices):
                    group[index].client.visual = visual[j].clone()
            labels = [req.client.instruction for req in group]
            missing = list(dict.fromkeys(t for t in labels if t not in texts))
            if missing:
                encoded = actor.encode_text(torch.tensor([vocab.encode(t) for t in missing],device=self.device))
                texts.update({t: encoded[j].clone() for j,t in enumerate(missing)})
            args = (torch.stack([req.client.visual for req in group]), torch.stack([texts[t] for t in labels]),
                    p, a, torch.tensor(timing, dtype=torch.float32,device=self.device))
            if kind == "task" and self.use_task_graphs:
                key = (group[0].client.key, len(group))
                if key not in self.graphs:
                    if len(self.graphs) >= 48:
                        self.graphs.popitem(last=False)
                    try:
                        self.graphs[key] = FrozenTaskGraph(actor, args)
                    except torch.OutOfMemoryError:
                        self.graphs[key] = None
                        print("Using eager inference for a batch that could not reserve CUDA graph memory",
                              key, flush=True)
                self.graphs.move_to_end(key)
                graph = self.graphs[key]
                if graph is None:
                    raw, high, estimate = actor.infer_features(*args)
                else:
                    values = graph.run(args)
                    self.graph_calls += 1
            elif kind == "task" and any(x.body[1] for x in group):
                raw, high, estimate = actor.infer_features(*args)
            else:
                raw = actor.act_features_raw(*args)
        if values is None:
            values = [x.detach().float().cpu().numpy() if x is not None else None for x in (raw, high, estimate)]
        if any(x is not None and not np.isfinite(x).all() for x in values):
            raise FloatingPointError("Nonfinite actor response")
        for i, req in enumerate(group):
            parts = [v[i].ravel().astype(F4) if v is not None and (j == 0 or req.body[1])
                     else np.empty(0, F4) for j, v in enumerate(values)]
            req.done.set_result(bytes(len(x) for x in parts) + b"".join(x.tobytes() for x in parts))

    def serve_batches(self):
        import torch
        torch.set_num_threads(1)
        with torch.inference_mode():
            while True:
                items = [self.pending.get()]
                deadline = time.monotonic() + self.window
                while len(items) < self.max_batch:
                    try:
                        items.append(self.pending.get(timeout=max(0., deadline-time.monotonic())))
                    except queue.Empty:
                        break
                grouped = defaultdict(list)
                for req in items:
                    grouped[req.client.key].append(req)
                ready = time.monotonic()
                self.wait_sum += sum(ready-x.arrival for x in items)
                for group in grouped.values():
                    try:
                        self.infer(group)
                    except Exception as exc:
                        for req in group:
                            if not req.done.done():
                                req.done.set_exception(exc)
                    self.batches += 1
                    self.max_seen = max(self.max_seen, len(group))
                self.calls += len(items)
                if ready - self.last_stats >= 10 or self.calls == len(items):
                    stats = dict(calls=self.calls, forwards=self.batches, max_batch=self.max_seen,
                                 mean_batch=self.calls/self.batches, queue_wait_mean_ms=1000*self.wait_sum/self.calls,
                                 device=self.device, queued=self.pending.qsize(), models=len(self.models),
                                 graph_calls=self.graph_calls, cached_graphs=len(self.graphs), coalesce_ms=self.window*1000,
                                 peak_torch_allocated_bytes=torch.cuda.max_memory_allocated())
                    from scripts.multimodal.mm03_launch import read,write
                    stats["pid"]=os.getpid()
                    write(self.root/f"service/stats/{os.getpid()}.json",stats)
                    if read(self.root/"service/serving.json").get("pid")==os.getpid():
                        write(self.root/"service/inference_stats.json",stats)
                    self.last_stats = ready


def serve(root, max_batch, window_ms):
    import torch
    path = socket_for(root)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not torch.cuda.is_available():
        raise RuntimeError("MM03 central inference requires the allocated GPU")
    from scripts.multimodal.mm03_launch import pid_stamp,write,now
    from uuid import uuid4
    bound=path.with_name(f"policy.{os.getpid()}.{uuid4().hex[:6]}.sock")
    service = ModelBatcher(root, "cuda", max_batch, window_ms)
    with Listener(str(bound), family="AF_UNIX", backlog=64) as listener:
        bound.chmod(0o600)
        threading.Thread(target=service.serve_batches, daemon=True).start()
        bound.replace(path)
        write(root/"service/serving.json",dict(pid=os.getpid(),pid_stamp=pid_stamp(os.getpid()),
              socket=str(path),bound_name=str(bound),ready_beijing=now()))
        print(f"CUDA inference ready at {path} (batch <= {max_batch}, coalescing {window_ms} ms)",flush=True)
        while True:
            threading.Thread(target=service.client_loop, args=(listener.accept(),), daemon=True).start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--max-batch", type=int, default=32)
    parser.add_argument("--window-ms", type=float, default=.7)
    args = parser.parse_args()
    serve(args.root, args.max_batch, args.window_ms)
