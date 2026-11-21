"""Compare the open-loop action-to-TCP Jacobian with real native MuJoCo perturbations."""
import argparse
import copy
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from learning.b0.action_diagnostics import GROUPS  # noqa: E402
from learning.b0.physics import ActionMap, NativePlant, make_model  # noqa: E402
from learning.b0.reference import load_episode  # noqa: E402


def jac_stats(actual, estimate):
    actual, estimate = np.asarray(actual), np.asarray(estimate)
    na, nb = np.linalg.norm(actual), np.linalg.norm(estimate)
    return dict(actual_norm=float(na), estimate_norm=float(nb), relative_frobenius_error=(
                float(np.linalg.norm(actual-estimate)/na) if na > 1e-12 else None),
                cosine=float(np.sum(actual*estimate)/(na*nb)) if na*nb > 1e-20 else None)


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(obj, indent=2, allow_nan=False) + '\n')


def physical(args):
    import mujoco as mj
    model = make_model()
    plant = NativePlant(model)
    ep = load_episode(args.reference_root / 'moving_arm_wm_validation')
    # Reconstruct the solver/servo state by actual recorded controls up to k.
    k = args.start
    actions = np.array(ep['action_clipped'][k:k+7], dtype=float)
    if len(actions) != 7 or k < 0 or np.any(np.abs(actions[0]) >= 1 - .002):
        raise ValueError('Need 7 future true inputs and interior first action for signed differences')
    plant.reset(ep['qpos'][0], ep['qvel'][0])
    for a in ep['action_clipped'][:k]:
        r = plant.step(a)
        if r['failure_reason']:
            raise RuntimeError(f'Cannot reconstruct native start: {r}')
    qdiff = float(np.max(np.abs(plant.data.qpos - ep['qpos'][k])))
    vdiff = float(np.max(np.abs(plant.data.qvel - ep['qvel'][k])))
    snapshot = copy.copy(plant.data)
    sat = plant.sat_time.copy()
    unloaded = plant.unloaded_time
    tcp_id = model.site('p4_grasp').id
    scratch = mj.MjData(model)

    def play(current):
        plant.data = copy.copy(snapshot)
        plant.sat_time = sat.copy()
        plant.unloaded_time = unloaded
        xyz, signatures = {}, []
        def record(d, c):
            active = tuple(sorted(tuple(sorted((int(x.geom1), int(x.geom2))))
                                  for x in d.contact if x.efc_address >= 0))
            signatures.append((tuple(c.supported.tolist()), active))
        for i, a in enumerate(current):
            info = plant.step(a, record)
            if info['failure_reason']:
                raise RuntimeError(f'Physical perturbation interrupted at tick {i}: {info}')
            if i + 1 in (1, 7):
                scratch.qpos[:] = plant.data.qpos
                mj.mj_kinematics(model, scratch)
                xyz[i+1] = scratch.site_xpos[tcp_id].copy()
        return xyz, signatures

    zero, contact0 = play(actions)
    samples = {}
    for epsilon in (.0005, .002):
        jac = {h: np.empty((3, 23)) for h in (1, 7)}
        changes = {h: [] for h in (1, 7)}
        for j in range(23):
            forward, backward = actions.copy(), actions.copy()
            forward[0, j] += epsilon
            backward[0, j] -= epsilon
            p, cp = play(forward)
            m, cm = play(backward)
            for h in (1, 7):
                jac[h][:, j] = (p[h] - m[h]) / (2 * epsilon)
                sl = slice(0, 10*h)
                if cp[sl] != contact0[sl] or cm[sl] != contact0[sl]:
                    changes[h].append(j)
        samples[str(epsilon)] = {h: dict(jacobian=jac[h].tolist(), contact_mode_changed_channels=changes[h])
                                 for h in (1, 7)}
    convergence = {}
    for h in (1, 7):
        a = np.asarray(samples['0.002'][h]['jacobian'])
        b = np.asarray(samples['0.0005'][h]['jacobian'])
        convergence[h] = {g: jac_stats(a[:, sl], b[:, sl]) for g, sl in GROUPS.items()}
        convergence[h]['all'] = jac_stats(a, b)
    save(args.output, dict(backend='native CPU MuJoCo', mujoco=mj.__version__, reference='moving_arm_wm_validation',
         reference_root=str(args.reference_root), start=k, start_s=float(ep['t'][k]), horizons=[1,7],
         action_units='derivative per unit normalized post-clamp action at the first tick only',
         physical_action_units=plant.mapping.describe(model), tcp='p4_grasp world XYZ in m',
         start_state='recorded actions physically replayed from frame 0, solver caches restored with MjData copy for each signed perturbation',
         max_start_qpos_error=qdiff, max_start_qvel_error=vdiff,
         unperturbed_endpoint_error_m={h:float(np.linalg.norm(zero[h]-ep['tcp_world'][k+h])) for h in (1,7)},
         initial_action=actions[0].tolist(), initial_tcp=ep['tcp_world'][k].tolist(),
         contact_convention='per-substep four 1 N loaded-wheel bits and multiset of active MuJoCo geom pairs',
         centered_differences=samples, epsilon_convergence=convergence))


def compare_model(args):
    import torch
    from supermimic.models import Dynamics
    from learning.b0.model import RobotRepresentation, full_state, tensor
    truth = json.loads(args.physics.read_text())
    ckpt = torch.load(args.checkpoint, weights_only=True, map_location='cpu')
    if Path(truth['reference_root']).resolve() != Path(ckpt['cfg']['reference_root']).resolve():
        raise ValueError('Physical and model reference roots differ')
    model = make_model()
    amap = ActionMap(model)
    rep = RobotRepresentation(model, 'cpu')
    dyn = Dynamics(rep, 23, 1, tensor(amap.scale, 'cpu'), tensor(amap.offset, 'cpu'), tuple(ckpt['cfg']['wm_hidden']))
    dyn.load_state_dict(ckpt['dyn'])
    dyn.eval().requires_grad_(False)
    rep.eval().requires_grad_(False)
    ep = load_episode(Path(truth['reference_root']) / truth['reference'])
    k = truth['start']
    s = full_state(tensor(ep['qpos'][k:k+1], 'cpu'), tensor(ep['qvel'][k:k+1], 'cpu'))
    aux, r = s[:, :7], rep.represent(s)
    actions = tensor(ep['action_clipped'][k:k+7], 'cpu')
    first = actions[:1].clone().requires_grad_()
    results = {}
    for i in range(7):
        a = first if i == 0 else actions[i:i+1]
        aux, r = dyn(r, a, aux, torch.ones((1,1)))
        h = i + 1
        if h not in (1,7):
            continue
        tcp = rep.world_frame_bodies(aux, r)[0][0, -1]
        jac = torch.stack([torch.autograd.grad(c, first, retain_graph=True)[0][0] for c in tcp]).numpy()
        if not np.isfinite(jac).all():
            raise RuntimeError('Nonfinite model Jacobian')
        compares = {}
        for eps, samples in truth['centered_differences'].items():
            actual = np.array(samples[str(h)]['jacobian'])
            grouped = {g: jac_stats(actual[:, sl], jac[:, sl]) for g, sl in GROUPS.items()}
            grouped['all'] = jac_stats(actual, jac)
            compares[eps] = grouped
        predicted_tcp = tcp.detach().numpy()
        results[h] = dict(jacobian=jac.tolist(), predicted_tcp=predicted_tcp.tolist(),
                          endpoint_error_m=float(np.linalg.norm(predicted_tcp - ep['tcp_world'][k+h])),
                          versus_native=compares)
    save(args.output, dict(checkpoint=str(args.checkpoint), actor_update=ckpt['updates'],
         episode=truth['reference'], start=k, native_file=str(args.physics), horizons=results,
         all_wm_parameters_frozen=not any(p.requires_grad for p in dyn.parameters()),
         any_wm_parameter_gradient=any(p.grad is not None for p in dyn.parameters())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    explicit = commands.add_parser('native')
    explicit.add_argument('reference_root', type=Path)
    explicit.add_argument('output', type=Path)
    explicit.add_argument('--start', type=int, default=100)
    wm = commands.add_parser('wm')
    wm.add_argument('checkpoint', type=Path)
    wm.add_argument('physics', type=Path)
    wm.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'native':
        physical(args)
    else:
        compare_model(args)
