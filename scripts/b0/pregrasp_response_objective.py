"""Identical closed-loop scoring for fixed-noise WM AD, finite differences, and measured successors."""
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import torch
from supermimic.envs.world_model_env import WorldModelEnv
from supermimic.learners.policy_learner import ActorCriticPolicyLearner, ActorCriticPolicyLearnerCfg
from learning.b0.contact_reward import reward_terms
from learning.b0.contact_warp import REASONS
from learning.b0.model import RobotActor
from scripts.b0.pregrasp_response import OUT, RAW, DEVICE, read, write

HORIZONS = (1,7,32)
AMPS = (.02,.04,.08)
TERMS = ('anchor_position','anchor_orientation','body_position','body_orientation',
         'body_linear_velocity','body_angular_velocity','action_rate','joint_limit')
NAMES = ['prefix_return','bootstrapped_return','critic_contribution','survival',
         'last_soft_termination','endpoint_m','synchronous_m','auxiliary_loss',
         *['weighted_'+s for s in TERMS], *[f'aux_{i}' for i in range(7)],
         *[f'rep_{i}' for i in range(75)],'tcp_x','tcp_y','tcp_z']
INDEX = {key:i for i,key in enumerate(NAMES)}


def array(x):
    return x.detach().cpu().numpy().copy()


class Fold:
    """The same floating-point reward, termination, coordinates and bootstrap on either successor."""
    def __init__(self,scene,k):
        self.scene,self.k = scene,k
        self.cfg = ActorCriticPolicyLearnerCfg()
        self.cfg.horizon = 32
        assert self.cfg.gamma == .99 and self.cfg.survival_masking
        self.term_spec = SimpleNamespace(_anchor_index=0,_anchor_pos_threshold=.1,
                                         _anchor_ori_threshold=.12,_termination_softness=.05)
        self.critic_spec = SimpleNamespace(critic=scene.critic,cfg=self.cfg,_v_max=.02*5/(1-self.cfg.gamma))
        self.total=0.
        self.survival=1.
        self.components = {key:0. for key in TERMS}
        self.aux_loss=0.
        self.outputs=[]

    def step(self, j, aux, rep, action, prev, aux_loss):
        s = self.scene
        f=s.frame(self.k+j+1,len(aux))
        target=s.bank.body_state(f)
        term=WorldModelEnv._compute_term_prob(self.term_spec,aux,*target[:2])
        rr=s.rep.compute_wm_reward_from_reference(rep,aux,s.rep.joint_state(rep),action,prev,*target)
        terms=reward_terms(s.rep,rep,aux,action,prev,target,coordinates=s.rep.reward_coordinates)
        weight=self.cfg.gamma**j*self.survival
        self.total=self.total+weight*rr
        self.survival=self.survival*(1.-term)
        self.aux_loss=self.aux_loss+aux_loss
        self.components={key:self.components[key]+weight*value for key,value in terms.items()}
        if j+1 not in HORIZONS:
            return
        tcp=s.rep.tcp_pose(aux,rep[:,10:34])[0]
        ref_tcp=s.rep.tcp_pose(s.bank.qpos[f,:7],s.bank.joint_pos[f])[0]
        if j+1==32:
            wm,_=s.bank.goals(s.rep,f,aux,rep[:,58])
            critic_obs=torch.cat((rep,wm,s.ctx),dim=-1)
            boot=ActorCriticPolicyLearner._bootstrap(self.critic_spec,{'critic':critic_obs},self.survival,term)
            self.critic_clipped=bool((s.critic(critic_obs).detach()>self.critic_spec._v_max).any())
        else:
            boot=torch.zeros_like(self.total)
        scalars=(self.total, self.total+boot,boot,self.survival,term,(tcp-s.endpoint).norm(dim=-1),
                 (tcp-ref_tcp).norm(dim=-1),self.aux_loss,*self.components.values())
        self.outputs.append(torch.cat((*[x.reshape(-1) for x in scalars],aux.flatten(),rep.flatten(),tcp.flatten())))


class Experiment:
    def __init__(self, scene,k):
        self.s,self.k=scene,k
        self.hist,self.last=scene.reload(k)
        self.aux,self.rep=scene.state()
        self.aux=self.aux.clone()
        self.rep=self.rep.clone()
        self.root=scene.start_dir(k)
        # Independent fixed generator; both models consume identical noise at each sensor clock.
        gen=torch.Generator(device=DEVICE)
        gen.manual_seed(825251)
        anchors=read(OUT/'states.json')['states']
        index=next(i for i,r in enumerate(anchors) if (r['side'],r['frame'])==(scene.side,k))
        draws=torch.rand((len(anchors),42,77),generator=gen,device=DEVICE)
        self.noise=((draws[index]*2-1)*scene.rep._proprio_noise_bounds).detach()
        self.hist=self.hist+self.noise[:10][None]
        obs,_=scene.obs(k,self.hist,self.aux,self.rep)
        self.z=RobotActor.raw(scene.actor,obs).detach()
        np.save(self.root/'response_noise.npy',array(self.noise))

    def cmd(self,z):
        a=self.s.actor
        return a.home_action + a.standard_action*z

    def roll(self, z, actual=False, details=None):
        s,k=self.s,self.k
        hist,last=self.hist,self.last
        aux,rep=self.aux,self.rep
        fold=Fold(s,k)
        if actual:
            s.reload(k)
        for j in range(32):
            if j:
                obs,_=s.obs(k+j,hist,aux,rep)
                raw=s.actor.raw(obs)
            else:
                raw=self.cmd(z)
            act=raw.clamp(-1,1)
            aux_loss=s.actor.auxiliary_loss()
            if details is not None:
                details['raw'].append(array(raw)[0])
            if actual:
                ev=s.integrate(k+j,act,record=True)
                record=ev['substeps']
                micro=int(ev['physics_steps'].item())
                details['steps'].append(micro)
                for name in ('finger_load_N','wheel_load_N','unexpected_contact_N','door_force_norm_sum_N',
                             'wheel_slip_m_s','actuator_force','ctrl'):
                    details[name].append(array(record[name])[0])
                if ev['first_fail_substep'].item():
                    details['first_failure']=dict(frame=k+j,microstep=micro,reason=REASONS[int(ev['reason'].item())])
                    break
                aux,rep=s.state()
            else:
                aux,rep=s.dyn(rep,act,aux,s.ctx)
            fold.step(j,aux,rep,act,last,aux_loss)
            clean=s.sense(aux,rep,act)
            hist=torch.cat((hist[:,1:],(clean+self.noise[10+j])[:,None]),dim=1)
            last=act
        if details is not None:
            details['critic_clipped']=getattr(fold,'critic_clipped',None)
        return torch.stack(fold.outputs) if fold.outputs else torch.empty((0,len(NAMES)),device=DEVICE)

    def directions(self):
        z=self.z.clone().requires_grad_(True)
        objective=self.roll(z)[-1,INDEX['bootstrapped_return']]
        grad=torch.autograd.grad(objective,z)[0]
        maximum=float(grad.abs().max())
        dirs={}
        if torch.isfinite(grad).all().item() and maximum>0:
            dirs['objective']=grad.detach()/maximum
        j2=torch.zeros_like(z)
        j2[0,17]=1.
        wheels=torch.zeros_like(z)
        wheels[0,12:16]=torch.tensor(self.s.axle_sign,device=DEVICE,dtype=z.dtype)
        dirs['j2']=j2
        dirs['wheels']=wheels
        np.savez(self.root/'directions.npz',z=array(z),gradient=array(grad),**{n:array(d) for n,d in dirs.items()})
        return dirs

    def run(self):
        dirs=self.directions()
        ad={}
        for n,d in dirs.items():
            _,der=torch.autograd.functional.jvp(self.roll,(self.z,),(d,))
            ad[n]=array(der)
        np.savez_compressed(self.root/'wm_directional_derivatives.npz',**ad)
        branches=[('baseline',0.,0,self.z)]
        for n,d in dirs.items():
            for a in AMPS:
                for sign in (1,-1):
                    branches.append((n,a,sign,self.z+sign*a*d))
        rows=[]
        with torch.no_grad():
            for n,a,sign,z in branches:
                label=f'{n}_{int(round(a*100)):02}_{sign}'
                path=self.root/f'{label}.npz'
                receipt=self.root/f'{label}.json'
                if receipt.is_file() and path.is_file():
                    rows.append(read(receipt))
                    continue
                marker=self.root/f'{label}.started.json'
                if marker.is_file():
                    raise RuntimeError(f'Inspect interrupted branch before further collection: {marker}')
                pred_detail={'raw':[]}
                pred=self.roll(z,details=pred_detail)
                detail={name:[] for name in ('raw','steps','finger_load_N','wheel_load_N','unexpected_contact_N',
                                             'door_force_norm_sum_N','wheel_slip_m_s','actuator_force','ctrl')}
                write(marker,dict(side=self.s.side,frame=self.k,label=label))
                measured=self.roll(z,actual=True,details=detail)
                arrays={name:np.concatenate(detail[name]) for name in ('finger_load_N','wheel_load_N','unexpected_contact_N',
                                                                       'door_force_norm_sum_N','wheel_slip_m_s','actuator_force','ctrl')}
                np.savez_compressed(path,wm=array(pred),real=array(measured),wm_raw=np.array(pred_detail['raw']),
                                    real_raw=np.array(detail['raw']),microsteps=detail['steps'],**arrays)
                rec=dict(side=self.s.side,frame=self.k,label=label,direction=n,amplitude=a,sign=sign,
                         microsteps=sum(detail['steps']),policy_queries=len(detail['steps']),
                         physical_first_failure=detail.get('first_failure'),real_horizons=list(HORIZONS[:len(measured)]),
                         wm_critic_clipped=pred_detail['critic_clipped'],real_critic_clipped=detail['critic_clipped'],
                         raw=str(path))
                write(receipt,rec)
                rows.append(rec)
                print(self.s.side,self.k,label,rec['microsteps'],flush=True)
        write(OUT/f'response_cases_{self.s.side}_{self.k}.json',dict(rows=rows,fields=NAMES,raw=str(self.root),
              auxiliary='Original latent BC loss; motion-only allocation',axle_sign=self.s.axle_sign.tolist(),
              physical_per_effort=self.s.units.tolist(),directions=list(dirs)))


def run_responses(scene,only_frame=None):
    reconstruction=read(OUT/f'response_reconstruction_{scene.side}.json')
    for k in reconstruction['reached']:
        if only_frame is not None and only_frame != k:
            continue
        check=OUT/f'response_reload_{scene.side}_{k}.json'
        if not check.is_file():
            scene.check(k)
        receipt=read(check)
        errors=receipt['max_abs']
        # Absolute differences are retained even when all discrete decisions agree.
        # Verify every solver array directly at the start before interpreting floating roundoff in the successor.
        scene.reload(k)
        from scripts.b0.dynamics_h32_pilot import records
        with np.load(scene.start_dir(k)/'solver.npz') as solver:
            for name,buf in records(scene.plant.sim.wp_data):
                np.testing.assert_array_equal(buf.numpy(),solver[name])
        discrete=('reason','fail','steps','load_ticks','lost_ticks','slip_ticks','sat_ticks','saturation_time')
        assert all(errors[name]==0 for name in discrete) and receipt['microsteps']==80
        # Magnitudes are expressed in saved physical/canonical coordinates, not scored under a bitwise pass rule.
        roundoff_limits=dict(q=1e-7,v=1e-5,hist=1e-5,action=5e-7,servo_bias=1e-6)
        if any(errors[name]>limit for name,limit in roundoff_limits.items()):
            raise ValueError(f'Unresolved reload difference, inspect {check}')
        write(check,receipt|dict(start_solver_arrays_bitwise_equal=True,discrete_successor_counters_exact=True,
                                numerical_review_limits=roundoff_limits,review='Numerical review after measured reload; see individual residuals'))
        Experiment(scene,k).run()
