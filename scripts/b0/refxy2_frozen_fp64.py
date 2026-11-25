"""Frozen original540/u10000 FP64 signed H32 rollouts, forward JVP and reverse AD."""
import argparse
import json
import os
from pathlib import Path

os.environ["TORCH_COMPILE_DISABLE"] = "1"
import numpy as np
import torch
from supermimic.models import build_mlp
from supermimic.envs.world_model_env import WorldModelEnv
from supermimic.learners.policy_learner import ActorCriticPolicyLearner
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_events import FrozenDoorReference
from learning.b0.contact_model import ContactRepresentation, contact_context, contact_state
from learning.b0.contact_policy import build_actor, DoorMotions
from learning.b0.contact_reward import reward_terms
from learning.b0.physics import ActionMap, make_model
from learning.b0.temporal_dynamics import make_dynamics
from scripts.b0.pregrasp_response import DEVICE, PARENT, OUT, RAW, WEIGHTS, read, write
from scripts.b0.pregrasp_response_objective import Fold, TERMS

DIRECTIONS = ("objective", "j2", "wheels")
SCALES = .02 * 2. ** -np.arange(11)
FIELDS = ["prefix", "J", "bootstrap", "survival", "term_prob", "weight", "endpoint_m",
          "synchronous_m", "reward", *["weighted_" + n for n in TERMS],
          *["aux_" + str(i) for i in range(7)], *["rep_" + str(i) for i in range(75)],
          *["raw_" + str(i) for i in range(23)], *["action_" + str(i) for i in range(23)]]
I = {f: i for i, f in enumerate(FIELDS)}


def to_device(x):
    return torch.as_tensor(x, device=DEVICE, dtype=torch.float64)


def promote_attributes(obj):
    """FK constants and bank tables include tensors held outside registered buffers."""
    for key, value in vars(obj).items():
        if isinstance(value, torch.Tensor) and value.is_floating_point():
            setattr(obj, key, value.double())
        elif isinstance(value, tuple) and value and all(isinstance(v, torch.Tensor) for v in value):
            setattr(obj, key, tuple(v.double() if v.is_floating_point() else v for v in value))


class Frozen:
    def __init__(self, side, k):
        self.side, self.k = side, k
        case = read(PARENT / 'physics/u010000_warp_full' / side / 'full/nominal/result.json')
        model = make_model('push' if side == 'push' else 'mobile', case['perturbation']['p6_case'])
        model.opt.timestep = .00025
        pkg = torch.load(WEIGHTS, map_location='cpu', weights_only=False)
        cfg = pkg['cfg']
        assert cfg['execution_recipe'] == 'official_flow_s0_v1'
        rep = self.rep = ContactRepresentation(model, DEVICE)
        rep.reward_coordinates = cfg['action_rate_coordinates']
        self.actor, _ = build_actor(rep, cfg, model, DEVICE)
        self.dyn = make_dynamics(model, rep, ActionMap(model), cfg['wm_hidden'], cfg['temporal_id'], DEVICE)
        self.critic = build_mlp(650, tuple(cfg['critic_hidden']), 1).to(DEVICE)
        for key, mod in [('dyn', self.dyn), ('actor', self.actor), ('critic', self.critic)]:
            mod.load_state_dict(pkg[key], strict=True)
            mod.eval().requires_grad_(False)
        assert self.actor.encoders['motion'][0].weight.shape == (2048, 540)
        assert self.dyn._apply_prediction.__self__ is rep
        paths = list(map(Path, cfg['reference_paths']))
        path = next(p for p in paths if p.name == case['episode'])
        self.bank = DoorMotions(paths, rep, DEVICE, reference_tail=cfg['reference_tail'])
        self.start = self.bank.starts[path.name]
        self.endpoint = to_device(np.asarray(FrozenDoorReference.from_episode(path, model).endpoint_pose['pregrasp'][0], np.float32))
        self.folder = RAW / 'response' / side / f'frame_{k:04}'
        with np.load(self.folder / 'solver.npz') as solver:
            state = contact_state(torch.as_tensor(solver['qpos'], device=DEVICE),
                                  torch.as_tensor(solver['qvel'], device=DEVICE))
            self.aux0, self.rep0 = state[:, :7].double(), rep.represent(state).double()
        bound = torch.load(self.folder / 'boundary.pt', map_location='cpu', weights_only=False)
        assert (bound['side'], bound['frame'], bound['physics_steps'], bound['query_phase']) == (side, k, 80*k, 'actor_query_ready')
        assert torch.equal(bound['context'].cpu(), contact_context(model, side, DEVICE)[None].cpu())
        self.ctx = to_device(bound['context'])
        noise = np.load(self.folder / 'response_noise.npy')
        assert noise.shape == (42, 77)
        self.noise = to_device(noise)
        self.hist0 = to_device(bound['history']) + self.noise[:10][None]
        self.prev0 = to_device(bound['previous'])
        with np.load(self.folder / 'directions.npz') as a:
            self.z = to_device(a['z'])
            self.directions = {n: to_device(a[n]) for n in DIRECTIONS}
        # Lift the exact parent function constants including FK lookup tables.
        for mod in (rep, self.actor, self.dyn, self.critic):
            mod.double().eval().requires_grad_(False)
            promote_attributes(mod)
            assert all(v.dtype == torch.float64 for v in (*mod.parameters(), *mod.buffers()) if v.is_floating_point())
        for obj in (rep.fk, rep.fk.hinges, self.bank):
            promote_attributes(obj)
        specs = Fold(self, k)
        self.term, self.critic_spec = specs.term_spec, specs.critic_spec

    def frame(self, j, n):
        return torch.full((n,), self.start + self.k + j, device=DEVICE, dtype=torch.long)

    def roll(self, z):
        n = z.shape[0]
        aux, rep, ctx, previous = (v.expand(n, -1) for v in (self.aux0, self.rep0, self.ctx, self.prev0))
        hist = self.hist0.expand(n, -1, -1)
        prefix = z.new_zeros(n)
        survival = z.new_ones(n)
        sums = z.new_zeros((n, len(TERMS)))
        outputs = []
        for j in range(32):
            frame = self.frame(j, n)
            if j == 0:
                raw = self.actor.home_action + self.actor.standard_action * z
            else:
                _, goal = self.bank.goals(self.rep, frame, aux, rep[:, 58])
                raw = self.actor.raw(build_actor_obs_td({'motion': goal}, hist))
            action = raw.clamp(-1, 1)
            aux, rep = self.dyn(rep, action, aux, ctx)
            target = self.bank.body_state(frame+1)
            term = WorldModelEnv._compute_term_prob(self.term, aux, *target[:2])
            reward = self.rep.compute_wm_reward_from_reference(rep, aux, self.rep.joint_state(rep), action, previous, *target)
            terms = reward_terms(self.rep, rep, aux, action, previous, target, coordinates=self.rep.reward_coordinates)
            weight = .99**j * survival
            prefix = prefix + weight * reward
            sums = sums + weight[:, None] * torch.stack([terms[nm] for nm in TERMS], -1)
            survival = survival * (1 - term)
            if j == 31:
                wm, _ = self.bank.goals(self.rep, frame+1, aux, rep[:, 58])
                bootstrap = ActorCriticPolicyLearner._bootstrap(self.critic_spec, {'critic': torch.cat((rep, wm, ctx), -1)}, survival, term)
            else:
                bootstrap = torch.zeros_like(prefix)
            tcp, _ = self.rep.tcp_pose(aux, rep[:, 10:34])
            ref_tcp, _ = self.rep.tcp_pose(self.bank.qpos[frame+1, :7], self.bank.joint_pos[frame+1])
            sensor = self.rep.compute_actor_sensor(rep, ctx, aux_state=aux, joint_state=self.rep.joint_state(rep), last_action=action)
            hist = torch.cat((hist[:, 1:], (sensor+self.noise[10+j])[:, None]), 1)
            previous = action
            scalars = torch.stack((prefix, prefix+bootstrap, bootstrap, survival, term, weight,
                                   (tcp-self.endpoint).norm(dim=-1), (tcp-ref_tcp).norm(dim=-1), reward), -1)
            outputs.append(torch.cat((scalars, sums, aux, rep, raw, action), -1))
        return torch.stack(outputs)


def array(t):
    assert t.dtype == torch.float64
    return t.detach().cpu().numpy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jvp-engine', choices=('reverse-over-reverse', 'native-dual'),
                        default='reverse-over-reverse', help='The original bounded run used native-dual.')
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    write(root / 'fields.json', dict(fields=FIELDS, scales=SCALES.tolist(), directions=DIRECTIONS,
          axes='step,batch,field; signed batch: amplitude-major then sign +,- within each direction',
          parent=str(WEIGHTS.resolve()), source=str(RAW.resolve()), prediction_dt=.02, training_physics_dt=.00025))
    for row in read(OUT / 'states.json')['states']:
        side, k = row['side'], row['frame']
        path = root / f'{side}_{k}'
        path.mkdir(exist_ok=True)
        torch.set_default_dtype(torch.float32)
        frozen = Frozen(side, k)
        torch.set_default_dtype(torch.float64)
        for label in ('warmup', 'baseline_1', 'baseline_2', 'grad', *['jvp_'+d for d in DIRECTIONS], *['signed_'+d for d in DIRECTIONS]):
            dest = path / (label+'.npy')
            if dest.is_file():
                continue
            marker = path / (label+'.started.json')
            if marker.exists():
                raise RuntimeError(f'Unresolved previous execution at {marker}')
            write(marker, dict(side=side, frame=k, call=label, jvp_engine=args.jvp_engine if label.startswith('jvp_') else None))
            if label == 'grad':
                z = frozen.z.clone().requires_grad_(True)
                value = frozen.roll(z)[-1, 0, I['J']]
                data = array(torch.autograd.grad(value, z)[0])
            elif label.startswith('jvp_'):
                d = frozen.directions[label[4:]]
                if args.jvp_engine == 'reverse-over-reverse':
                    _, derivative = torch.autograd.functional.jvp(frozen.roll, frozen.z, d)
                    data = array(derivative)
                else:
                    # Original diagnostic path, retained for provenance. Scripted
                    # quaternion ops can lose forward duals even for an identity.
                    with torch.no_grad(), torch.autograd.forward_ad.dual_level():
                        dual_z = torch.autograd.forward_ad.make_dual(frozen.z, d)
                        pair = torch.autograd.forward_ad.unpack_dual(frozen.roll(dual_z))
                        data = array(pair.tangent)
            else:
                z = frozen.z
                if label.startswith('signed_'):
                    d = frozen.directions[label[7:]]
                    z = torch.cat([z + float(sign*h)*d for h in SCALES for sign in (1, -1)])
                with torch.no_grad():
                    data = array(frozen.roll(z))
            assert np.isfinite(data).all(), label
            with dest.with_suffix('.tmp').open('wb') as handle:
                np.save(handle, data)
            dest.with_suffix('.tmp').replace(dest)
            print(side, k, label, data.shape, flush=True)


if __name__ == '__main__':
    main()
