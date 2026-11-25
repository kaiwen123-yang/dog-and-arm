"""Frozen 250-us continuous starts, same-clock restore checks, and bounded physical branches."""
import argparse
import csv
import json
import os
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import mujoco
import numpy as np
import torch
import warp as wp
from supermimic.models import build_mlp
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_events import FrozenDoorReference
from learning.b0.contact_model import ContactRepresentation, contact_context, contact_state
from learning.b0.contact_policy import DoorMotions, build_actor
from learning.b0.contact_warp import ContactPlant, PHASE_ID, REASONS
from learning.b0.model import RobotActor
from learning.b0.physics import ActionMap, WHEELS, make_model
from learning.b0.temporal_dynamics import make_dynamics
from scripts.b0.dynamics_h32_pilot import read, records, write
from scripts.b0.dynamics_h32_probe import rng_state, restore_rng
from scripts.b0.eval_contact_segments import continuous_initial
from p6_base import wheel_geometry

OUT = Path('results/b0/standard_pregrasp_compatibility_20261125')
RAW = Path('results/raw_large/b0/pregrasp_compatibility_20261125')
PARENT = Path('results/b0/standard_official_flow_continuation_20261125')
WEIGHTS = Path('results/raw_large/b0/official_flow_continuation_20261125/checkpoint_010000.pt')
DEVICE = 'cuda:0'
COUNTERS = ('load_ticks', 'lost_ticks', 'slip_ticks', 'sat_ticks', 'saturation_time', 'servo_bias')


def tensor(x, dtype=torch.float32):
    return torch.as_tensor(x, device=DEVICE, dtype=dtype)


class Scene:
    def __init__(self, side):
        self.side = side
        self.bit = tensor([int(side == 'push')], torch.int32)
        self.rows = [r for r in read(OUT/'states.json')['states'] if r['side'] == side]
        self.case = read(PARENT/'physics/u010000_warp_full'/side/'full/nominal/result.json')
        self.model = make_model('push' if side == 'push' else 'mobile', self.case['perturbation']['p6_case'])
        self.model.opt.timestep = .00025
        package = torch.load(WEIGHTS, map_location='cpu', weights_only=False)
        cfg = package['cfg']
        self.map = ActionMap(self.model)
        self.rep = ContactRepresentation(self.model, DEVICE)
        self.rep.reward_coordinates = cfg['action_rate_coordinates']
        self.ctx = contact_context(self.model,side,DEVICE)[None]
        self.actor, _ = build_actor(self.rep,cfg,self.model,DEVICE)
        self.dyn = make_dynamics(self.model,self.rep,self.map,cfg['wm_hidden'],cfg['temporal_id'],DEVICE)
        self.critic = build_mlp(75+570+5,tuple(cfg['critic_hidden']),1).to(DEVICE)
        for key, module in [('actor',self.actor),('critic',self.critic),('dyn',self.dyn)]:
            module.load_state_dict(package[key])
            module.eval().requires_grad_(False)
        self.rep.eval().requires_grad_(False)
        paths = list(map(Path,cfg['reference_paths']))
        path = next(p for p in paths if p.name == self.case['episode'])
        self.bank = DoorMotions(paths,self.rep,DEVICE,reference_tail=cfg['reference_tail'])
        self.start = self.bank.starts[path.name]
        self.end = int(self.bank.motion_ends[self.bank.ids[path.name]].item())
        phases = read(path/'metadata.json')['phases']
        self.phases = tensor(np.array([PHASE_ID[p] for p in phases])[np.load(path/'substeps/phase.npy')],torch.long)
        self.endpoint = tensor(FrozenDoorReference.from_episode(path,self.model).endpoint_pose['pregrasp'][0])[None]
        self.plant = ContactPlant(self.model,1,DEVICE,preserve_continuous_bias=True)
        assert (self.plant.clock.policy_steps, self.plant.clock.servo_stride) == (80,8)
        assert self.rep.substep_coeff == .50625
        self.units = (self.actor.standard_action.cpu().numpy()*self.map.scale)
        np.testing.assert_allclose(self.units,read(PARENT/'interface.json')['physical_per_effort'],atol=1e-7)
        np.testing.assert_allclose(self.units[[12,13,14,15,17]],[.5,.5,.5,.5,.025],rtol=1e-6)
        d = mujoco.MjData(self.model)
        d.qpos[:] = self.case['initial_geometry']['initial_qpos']
        mujoco.mj_kinematics(self.model,d)
        self.axle_sign = wheel_geometry(d,self.model.body('m1_base_link').id,
                                        [self.model.joint(n).id for n in WHEELS])[0]
        assert np.all(abs(self.axle_sign)==1)

    def state(self):
        s = contact_state(self.plant.data.qpos[:],self.plant.data.qvel[:])
        return s[:,:7], self.rep.represent(s)

    def sense(self, aux, rep, last):
        return self.rep.compute_actor_sensor(rep,self.ctx.expand(len(aux),-1),aux_state=aux,
                                             joint_state=self.rep.joint_state(rep),last_action=last)

    def frame(self, k, n=1):
        assert 0 <= k and self.start+k < self.end
        return torch.full((n,), self.start+k,device=DEVICE,dtype=torch.long)

    def obs(self, k, hist, aux, rep):
        wm, act = self.bank.goals(self.rep,self.frame(k,len(aux)),aux,rep[:,58])
        return build_actor_obs_td({'motion':act},hist), wm

    def integrate(self, k, act, record=False):
        return self.plant.step_contact(act,self.bit,self.phases[k*10:k*10+10][None],
                                       record=record,stop_at_first_failure=True)

    def start_dir(self, k):
        return RAW/'response'/self.side/f'frame_{k:04}'

    def snapshot(self, k, hist, last):
        root = self.start_dir(k)
        root.mkdir(exist_ok=True,parents=True)
        wp.synchronize()
        np.savez_compressed(root/'solver.npz', **{k:a.numpy() for k,a in records(self.plant.sim.wp_data)})
        torch.save(dict(frame=k, physics_steps=k*80, servo_phase=0,
                        query_phase='actor_query_ready',side=self.side,dt=.00025,
                        elapsed_2ms_ticks=k*10, context=self.ctx.cpu(), history=hist.cpu(), previous=last.cpu(),
                        counters={n:getattr(self.plant,n).cpu().clone() for n in COUNTERS},
                        rng=rng_state()),root/'boundary.pt')

    def reload(self, k):
        root = self.start_dir(k)
        s = torch.load(root/'boundary.pt',map_location='cpu',weights_only=False)
        assert s['side']==self.side and s['dt']==self.model.opt.timestep and s['frame']==k
        assert s['physics_steps']==k*80 and s['servo_phase']==0 and s['query_phase']=='actor_query_ready'
        torch.testing.assert_close(self.ctx.cpu(),s['context'],rtol=0,atol=0)
        with np.load(root/'solver.npz') as data:
            fields = dict(records(self.plant.sim.wp_data))
            assert set(fields)==set(data.files)
            for name,buf in fields.items():
                buf.assign(data[name])
        wp.synchronize()
        for n,v in s['counters'].items():
            getattr(self.plant,n).copy_(v.to(DEVICE))
        restore_rng(s['rng'])
        return s['history'].to(DEVICE),s['previous'].to(DEVICE)

    def successor(self, hist,act):
        aux,rep = self.state()
        return torch.cat((hist[:,1:],self.sense(aux,rep,act)[:,None]),1)

    def output(self, hist, action, ev):
        result = dict(q=self.plant.data.qpos[:], v=self.plant.data.qvel[:], hist=hist,action=action,
                      reason=ev['reason'], fail=ev['first_fail_substep'], steps=ev['physics_steps'])
        result.update({n:getattr(self.plant,n) for n in COUNTERS})
        return {k:v.cpu().numpy().copy() for k,v in result.items()}

    @torch.no_grad()
    def replay(self):
        frames = [r['frame'] for r in self.rows]
        done_file = OUT/f'response_reconstruction_{self.side}.json'
        if done_file.exists():
            return
        if not frames:
            write(done_file,dict(side=self.side,runs=0,frames=[],reached=[],physics_steps=0,first_failure=None))
            return
        root = RAW/'response'/self.side
        root.mkdir(parents=True,exist_ok=True)
        marker = root/'frame0_started.json'
        if marker.exists():
            raise RuntimeError(f'Inspect previous run at {marker} before a second frame0 start')
        cpu_data,_,_ = continuous_initial(self.model,self.case['actual_config'],None)
        self.plant.reset(tensor(cpu_data.qpos)[None],tensor(cpu_data.qvel)[None])
        last = torch.zeros((1,23),device=DEVICE)
        aux,rep = self.state()
        hist = self.sense(aux,rep,last)[:,None].repeat(1,10,1)
        reached, failure, ticks = [], None, 0
        write(marker,dict(side=self.side,frames=frames,physics_dt=.00025))
        trace = []
        for k in range(max(frames)+1):
            if k in frames:
                self.snapshot(k,hist,last)
                reached.append(k)
            aux,rep = self.state()
            obs,_ = self.obs(k,hist,aux,rep)
            act = self.actor(obs)
            ev = self.integrate(k,act)
            micro = int(ev['physics_steps'].item())
            ticks += micro
            hist = self.successor(hist,act)
            trace.append(np.r_[k,self.plant.data.qpos[0].cpu().numpy(),self.plant.data.qvel[0].cpu().numpy(),act[0].cpu().numpy(),micro,int(ev['reason'].item())])
            if k in frames:
                np.savez_compressed(self.start_dir(k)/'continuous_successor.npz',**self.output(hist,act,ev))
            if ev['first_fail_substep'].item():
                failure=dict(frame=k,microstep=micro,absolute_microstep=ticks,
                             seconds=ticks*.00025,reason=REASONS[int(ev['reason'].item())])
                break
            last = act
            if k%100==0:
                print(self.side,'frame',k,flush=True)
        np.save(root/'frame0_trace.npy', np.array(trace))
        write(done_file,dict(side=self.side,runs=1,frames=frames,reached=reached,physics_steps=ticks,
                             first_failure=failure,trace=str(root/'frame0_trace.npy'),
                             columns=['frame','qpos[32]','qvel[31]','canonical action[23]','microsteps','reason_code'],
                             source='continuous frame0 developer replay with frozen clean-sensor Actor and original training physical monitor',
                             saved_solvers={k:str(self.start_dir(k)/'solver.npz') for k in reached},
                             no_teacher=True, collector_action_noise=False,online_training_sample=False))

    @torch.no_grad()
    def check(self,k):
        hist,last=self.reload(k)
        aux,rep=self.state()
        obs,_=self.obs(k,hist,aux,rep)
        act=self.actor(obs)
        ev=self.integrate(k,act)
        actual=self.output(self.successor(hist,act),act,ev)
        with np.load(self.start_dir(k)/'continuous_successor.npz') as expected:
            errors={n:float(np.max(np.abs(actual[n]-expected[n]))) for n in actual}
            exact=all(np.array_equal(actual[n],expected[n]) for n in actual)
        data=dict(frame=k,side=self.side,exact=exact,max_abs=errors,noise_identity='clean original frame0 replay',
                  microsteps=int(ev['physics_steps'].item()),solver_fields=len(list(records(self.plant.sim.wp_data))))
        write(OUT/f'response_reload_{self.side}_{k}.json',data)
        return exact


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['replay','responses'])
    parser.add_argument('side',choices=['pull','push'])
    parser.add_argument('--frame',type=int)
    args=parser.parse_args()
    torch.manual_seed(825251)
    np.random.seed(825251)
    scene=Scene(args.side)
    if args.stage=='replay':
        scene.replay()
    else:
        from scripts.b0.pregrasp_response_objective import run_responses
        run_responses(scene,args.frame)


if __name__=='__main__':
    main()
