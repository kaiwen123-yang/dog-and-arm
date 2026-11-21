"""Save checkpoint-level physical trials, held-out prediction errors, and trial footage."""
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

import mujoco as mj
import numpy as np

from .evaluate import PROTOCOL, ROOT, evaluate_cases, model_diagnostics


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def checkpoint_eval(run, output_dir, *, full=True):
    """Use the frozen Actor and WM of one training seed without modifying their parameters."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / 'physical').exists():
        raise FileExistsError(f'Physical results already exist in {output_dir}')
    cases = PROTOCOL['cases'] if full else [dict(id='nominal', dx_m=0., dy_m=0., dyaw_deg=0.)]
    seed, updates = int(run.seed), int(run.updates)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    raw = ROOT / 'results/raw_large/b0/diagnostics' / f'seed{seed}_u{updates}_{stamp}'
    episode_id = 'moving_arm_wm_validation'
    if set(run.refs) != set(PROTOCOL['references']):
        raise ValueError('A free-motion checkpoint requires all three frozen reference types')
    provenance = dict(seed=seed, actor_updates=updates, full_development_manifest=full,
                      physics_backend='native CPU MuJoCo', mujoco_version=mj.__version__,
                      physics_dt_s=float(run.model.opt.timestep), policy_dt_s=PROTOCOL['policy_dt_s'],
                      policy='frozen deterministic actor, fresh history each case', raw_path=str(raw.relative_to(ROOT)),
                      protocol=PROTOCOL['version'], tcp_site='p4_grasp', validation_episode_id=episode_id)
    _write_json(output_dir / 'evaluation.json', provenance)
    summary = evaluate_cases(run.model, run.refs, run.policy_factory, output_dir / 'physical',
                             seed=seed, checkpoint=f'actor_update_{updates}', cases=cases,
                             trace_directory=raw / 'physical')
    errors = model_diagnostics(run.model, run.validation, run.validation['action_clipped'], run.rollout,
                               episode_id=episode_id, train_episode_ids=list(run.refs),
                               trace_directory=raw / 'held_out')
    _write_json(output_dir / 'model_errors.json', errors)
    columns = ['horizon', 'method', 'num_starts', 'nonfinite', 'root_position_rmse_m',
               'root_orientation_rmse_deg', 'tcp_position_rmse_m', 'leg_position_rmse_rad',
               'arm_position_rmse_rad', 'wheel_speed_rmse_rad_s', 'gripper_width_rmse_m']
    with (output_dir / 'model_errors.csv').open('w') as f:
        writer = csv.DictWriter(f, lineterminator='\n', fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in errors['results']:
            writer.writerow({**row, **(row['metrics'] or {})})
    representatives = []
    for reference_id, reference in run.refs.items():
        name = f"{reference_id}_{cases[0]['id']}"
        trace = raw / 'physical' / name
        q = np.load(trace / 'qpos.npy')
        v = np.load(trace / 'qvel.npy')
        t = np.load(trace / 't.npy')
        xyz = np.load(trace / 'tcp_world.npy')
        score = json.loads((output_dir / 'physical' / f'{name}.json').read_text())
        with (output_dir / f'{name}_trace.csv').open('w') as f:
            writer = csv.writer(f, lineterminator='\n')
            writer.writerow(['frame', 'observed_time_s', 'reference_time_s', 'root_x_m', 'root_y_m',
                             'root_z_m', 'speed_xy_m_s', 'tcp_x_m', 'tcp_y_m', 'tcp_z_m', 'tcp_error_m'])
            for i in range(len(t)):
                aligned = i < score['scored_frames']
                writer.writerow([i, t[i], reference['t'][i] if aligned else '',
                                 *q[i, :3], np.linalg.norm(v[i, :2]), *xyz[i],
                                 np.linalg.norm(xyz[i] - reference['tcp_world'][i]) if aligned else ''])
        representatives.append(name)
    _write_json(output_dir / 'representatives.json', representatives)
    # The unchanged 3.3.0 project environment provides EGL, h264 and fonts.
    # Physics was already evaluated above; this subprocess only draws logged poses.
    subprocess.run(['bash', str(ROOT / 'scripts/project_env.sh'), 'python', '-m',
                    'learning.b0.diagnostics', str(output_dir)], cwd=ROOT,
                   env={**os.environ, 'MUJOCO_GL': 'egl'}, check=True)
    return summary


def render_trace_media(output_dir):
    import imageio.v2 as imageio
    from PIL import Image, ImageDraw, ImageFont
    from .physics import make_model

    model = make_model()
    data = mj.MjData(model)
    camera = mj.MjvCamera()
    camera.distance = 2.05
    camera.azimuth = 134
    camera.elevation = -17
    opt = mj.MjvOption()
    opt.geomgroup[3:5] = 0
    provenance = json.loads((output_dir / 'evaluation.json').read_text())
    raw = ROOT / provenance['raw_path'] / 'physical'
    font = ImageFont.load_default(size=17)
    with mj.Renderer(model, height=432, width=768) as renderer:
        for name in json.loads((output_dir / 'representatives.json').read_text()):
            score = json.loads((output_dir / 'physical' / f'{name}.json').read_text())
            q = np.load(raw / name / 'qpos.npy')
            t = np.load(raw / name / 't.npy')
            camera.lookat[:] = np.r_[q[0, :2] + [0.10, 0.], 0.65]

            def frame(index):
                data.qpos[:] = q[index]
                mj.mj_forward(model, data)
                renderer.update_scene(data, camera=camera, scene_option=opt)
                im = Image.fromarray(renderer.render())
                draw = ImageDraw.Draw(im)
                draw.rectangle((0, 0, im.width, 49), fill='#16222a')
                draw.text((9, 5), f"{name} | Actor update {provenance['actor_updates']} | "
                          f"t = {t[index]:.3f} / {t[-1]:.3f} s", fill='white', font=font)
                reason = 'passed' if score['passed'] else ', '.join(score['failures'][:2])
                draw.text((9, 26), f"Physical outcome: {reason}", fill='#dceef5', font=font)
                return im
            # Two distinct saved states document very early physical termination.
            if t[-1] - t[0] < 0.25:
                frame(0).save(output_dir / f'{name}_start.png')
                if len(t) > 1:
                    frame(-1).save(output_dir / f'{name}_end.png')
            else:
                with imageio.get_writer(output_dir / f'{name}.mp4', fps=25, codec='libx264',
                                        quality=6, macro_block_size=2) as writer:
                    indices = list(range(0, len(t), 2))
                    if indices[-1] != len(t) - 1:
                        indices.append(len(t) - 1)
                    for idx in indices:
                        writer.append_data(np.asarray(frame(idx)))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Render completed B0 physical traces from their recorded poses.')
    parser.add_argument('evaluation_dir', type=Path)
    render_trace_media(parser.parse_args().evaluation_dir)
