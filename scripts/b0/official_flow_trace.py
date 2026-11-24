"""Additional read-only traces and the registered training-clock single-world diagnostic."""
import json
import traceback
import sys
import warnings
from pathlib import Path
import numpy as np
from learning.b0.contact_clock import ContactClock

WARNING_CONTEXT = {'side':'startup','case':None}


def capture_warnings(path):
    original = warnings.showwarning
    def report(message, category, filename, lineno, file=None, line=None):
        if 'overflow' in str(message).lower():
            details={}
            frame=sys._getframe()
            while frame is not None:
                local=frame.f_locals
                if frame.f_code.co_name=='evaluate_segment':
                    details['active_side']=local.get('side')
                if frame.f_code.co_name=='put_data' and 'f' in local:
                    details['warp_data_field']=local['f'].name
                    val=np.asarray(local['val'])
                    bad=np.abs(val)>np.finfo(np.float32).max
                    details.update(shape=list(val.shape),dtype=str(val.dtype),outside_float32=int(bad.sum()),
                                   first_bad_indices=np.argwhere(bad)[:4].tolist())
                frame=frame.f_back
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a') as f:
                f.write(json.dumps(dict(category=category.__name__,message=str(message),file=filename,
                    line=lineno,stack=traceback.format_stack(),**WARNING_CONTEXT,**details))+'\n')
        original(message,category,filename,lineno,file,line)
    warnings.simplefilter('always',RuntimeWarning)
    warnings.showwarning=report


class FineServo:
    def __init__(self,model,device):
        from scripts.b0.eval_contact_segments import WarpSingleWorld
        from learning.b0.contact_warp import ContactPlant
        self.world=WarpSingleWorld.__new__(WarpSingleWorld)
        import torch, mujoco_warp
        self.world.m,self.world.device,self.world.torch,self.world.mjw=model,device,torch,mujoco_warp
        self.world.plant=ContactPlant(model,1,device,preserve_continuous_bias=True)
        self.clock=ContactClock(model.opt.timestep)
        assert (self.clock.policy_steps,self.clock.servo_stride)==(80,8)
        self.step_count=0

    def reset(self,d):
        self.world.reset(d)
        self.step_count=0

    def command(self,action):
        p=self.world.plant
        self.target=(self.world.tensor(action)[None]*p.scale+p.offset)*p.finger_factor

    def step(self,d,servo):
        p=self.world.plant
        refresh=self.step_count%self.clock.servo_stride==0
        if refresh:
            p.data.ctrl[:,p.actuator_ids]=self.target+p.servo_bias[:,p.dof]*p.bias_gain
        p.sim.step()
        if refresh:
            p.servo_bias.copy_(p.data.qfrc_bias[:])
        self.world.read_solve(d)
        self.step_count+=1

    def capacity(self):
        return self.world.capacity()


class ServoTrace:
    def __init__(self,windows=None):
        self.windows=windows
        self.rows=[]

    def record(self,k,q,v,d,judge,command,mapping,model):
        if self.windows is not None and not any(lo<=k<=hi for lo,hi in self.windows):
            return
        ids=mapping.actuator_ids
        # MuJoCo's scalar affine actuators use solved actuator length and velocity.
        ctrl=d.ctrl[ids]
        effective=np.where(model.actuator_ctrllimited[ids],np.clip(ctrl,*model.actuator_ctrlrange[ids].T),ctrl)
        raw=(model.actuator_gainprm[ids,0]*effective+model.actuator_biasprm[ids,0]
             +model.actuator_biasprm[ids,1]*d.actuator_length[ids]
             +model.actuator_biasprm[ids,2]*d.actuator_velocity[ids])
        ob=judge.latest
        self.rows.append(dict(step=k,q_pre=q.copy(),v_pre=v.copy(),q_post=d.qpos.copy(),v_post=d.qvel.copy(),
            ctrl=ctrl.copy(),bias=d.qfrc_bias[mapping.dof].copy(),force_prelimit=raw.copy(),
            force=d.actuator_force[ids].copy(),physical_target=command.copy(),phase=ob['phase'],
            heading_deg=ob['heading_error_deg'],xy_m=ob['station_error_m'],finger_n=ob['finger_n'],
            resultant_n=ob['net_door_force_n']))

    def save(self,folder):
        if self.rows:
            np.savez_compressed(folder/'solved_servo_trace.npz',**{k:np.asarray([r[k] for r in self.rows]) for k in self.rows[0]})
