"""Render the two archived native u1 successes from their recorded joint positions."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import mujoco as mj
import numpy as np
from OpenGL import GL

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from p6_scene import build

RUN = Path("results/b0/recovery_b_stance_u1_native_r1")
OUT = Path("results/b0/success_video_hd_20261125")
REVIEW = Path("results/b0/success_video_review_20261125/manifest.json")
CAMERA = "p6_overview"
WIDTH, HEIGHT, FPS = 1920, 1080, 25
CRF = 17


def read(path):
    return json.loads(path.read_text())


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_video(path, n):
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-nostdin", "-i", str(path),
                    "-map", "0:v:0", "-f", "null", "-"], check=True)
    info = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_frames",
        "-show_entries", "frame=best_effort_timestamp:stream=codec_name,pix_fmt,width,height,avg_frame_rate,time_base,duration_ts,nb_frames",
        "-of", "json", str(path)]))
    stream, = info["streams"]
    tb = Fraction(stream["time_base"])
    assert (stream["codec_name"], stream["pix_fmt"], stream["width"], stream["height"]) == ("h264","yuv420p",WIDTH,HEIGHT)
    assert Fraction(stream["avg_frame_rate"]) == FPS and int(stream["nb_frames"]) == len(info["frames"]) == n
    assert all(int(f["best_effort_timestamp"]) * tb == Fraction(i, FPS) for i, f in enumerate(info["frames"]))
    assert int(stream["duration_ts"]) * tb == Fraction(n, FPS)
    return stream


def render(side, source, archives, review):
    case = RUN / side / "full/nominal"
    result = read(ROOT / case / "result.json")
    cfg = result["actual_config"]
    assert result["passed"] and result["first_failure"] is None
    assert result["start_substep"] == result["prefix_physics_steps"] == 0 and len(result["events"]) == 13
    assert review["side"] == result["side"] == side and cfg["timestep_s"] == .002
    original = Path(result["raw_directory"])
    folder = source / side / "full/nominal" if source else original
    sources = {}
    for name in ("qpos.npy", "physics_step.npy"):
        p = folder / name
        key = str(original / name)
        digest = file_hash(p)
        entry = dict(original=key, read_path=str(p.resolve()), sha256=digest)
        if archives is not None:
            assert digest == archives[key]["sha256"] and p.stat().st_size == archives[key]["bytes"]
            entry.update(archives[key])
        sources[name] = entry

    q = np.load(folder / "qpos.npy", mmap_mode="r")
    steps = np.load(folder / "physics_step.npy", mmap_mode="r")
    model = build(cfg)
    assert q.shape == (len(steps), model.nq) and np.isfinite(q).all()
    assert steps[0] == 0 and np.all(np.diff(steps) > 0) and steps[-1] == result["physics_steps"] == review["physics_steps"]
    assert np.all(np.diff(steps) <= 10) and model.opt.timestep == .002
    end_deg = float(np.rad2deg(q[-1, model.joint("door_single_hinge").qposadr.item()]))
    assert abs(end_deg - result["final_door_deg"]) < 1e-9
    selected = np.flatnonzero((steps % 20 == 0) | (np.arange(len(steps)) == len(steps) - 1))
    assert len(selected) == review["frame_count"] and selected[0] == 0 and selected[-1] == len(q)-1
    assert np.array_equal(steps[selected[:-1]], np.arange(0, steps[-1], 20))
    assert np.array_equal(selected[:-1], np.arange(0, 2*(len(selected)-1), 2))

    model.vis.global_.offwidth = WIDTH
    model.vis.global_.offheight = HEIGHT
    data = mj.MjData(model)
    output = ROOT / OUT / f"{side}_full_1080p.mp4"
    temp = output.with_suffix(".partial.mp4")
    output.parent.mkdir(parents=True, exist_ok=True)
    encode = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
              "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
              "-framerate", str(FPS), "-i", "pipe:0", "-an", "-c:v", "libx264",
              "-crf", str(CRF), "-preset", "medium", "-threads", "3", "-pix_fmt", "yuv420p",
              "-movflags", "+faststart", str(temp)]
    with mj.Renderer(model, height=HEIGHT, width=WIDTH) as renderer:
        gl_renderer = GL.glGetString(GL.GL_RENDERER).decode()
        with subprocess.Popen(encode, stdin=subprocess.PIPE) as proc:
            try:
                for j, i in enumerate(selected):
                    data.qpos[:] = q[i]
                    mj.mj_forward(model, data)
                    renderer.update_scene(data, camera=CAMERA)
                    rgb = renderer.render()
                    proc.stdin.write(memoryview(np.ascontiguousarray(rgb)))
                    if j % 250 == 0:
                        print(f"{side} {j+1}/{len(selected)}", flush=True)
            finally:
                proc.stdin.close()
            if proc.wait():
                raise RuntimeError(f"{side} encoder exited with {proc.returncode}")
    stream = verify_video(temp, len(selected))
    temp.replace(output)
    return dict(side=side, result=str(case/"result.json"), original_video=str(case/"episode.mp4"),
                actual_config_source=str(case/"result.json")+"#actual_config", input_arrays=sources,
                saved_states=len(q), qpos_dim=model.nq, model_meshes=model.nmesh, gl_renderer=gl_renderer,
                model_camera_id=model.camera(CAMERA).id, physics_steps=int(steps[-1]),
                physics_seconds=float(steps[-1]*model.opt.timestep), final_door_deg=end_deg,
                selected_qpos_row_indices=dict(start=0,through=int(selected[-2]),stride=2,append_final=int(selected[-1])),
                selected_physics_steps=dict(start=0,through=int(steps[selected[-2]]),stride=20,append_final=int(steps[-1])),
                original_judgment=dict(passed=True,first_failure=None,events=[e["phase"] for e in result["events"]]),
                output=str(OUT/output.name), frames=len(selected), playback_seconds=len(selected)/FPS,
                header=stream, full_decode_and_all_pts_verified=True, sha256=file_hash(output), bytes=output.stat().st_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, help="Verified archive restore containing pull/ and push/")
    parser.add_argument("--archive-index", type=Path, help="Original-path archive members, sizes and SHA-256")
    args = parser.parse_args()
    review = read(ROOT / REVIEW)
    spec = read(ROOT / RUN / "run_spec.json")["plan"]
    evaluation = read(ROOT / RUN / "evaluation.json")
    assert mj.__version__ == spec["mujoco"] == "3.3.0" and spec["backend"] == "native"
    assert evaluation["checkpoint"] == spec["checkpoint"] == review["checkpoint"]
    assert evaluation["passed"] == evaluation["evaluated"] == 2 and not evaluation["failures"]
    archives = read(args.archive_index) if args.archive_index else None
    videos = [render(r["side"], args.source_root, archives, r) for r in review["videos"]]
    manifest = dict(method=review["method"], control_provenance=review["control_provenance"],
                    checkpoint_identity_only=review["checkpoint"], source_review=str(REVIEW),
                    run_spec=str(RUN/"run_spec.json"), evaluation=str(RUN/"evaluation.json"),
                    model_builder="scripts/p6_scene.py:build", scene="sim/scenes/assembly_preview.xml",
                    mujoco=mj.__version__, camera=CAMERA, resolution=[WIDTH,HEIGHT], fps=FPS, playback_speed=1,
                    encoder="libx264", crf=CRF, preset="medium", pixel_format="yuv420p", faststart=True,
                    selection="physics_step % 20 == 0 plus the last saved row, once",
                    state_replay="saved qpos to MjData, mj_forward, update_scene, render",
                    training_updates=0, new_physics_steps=0, policy_queries=0, original_scores_modified=False,
                    videos=videos)
    (ROOT/OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")


if __name__ == "__main__":
    main()
