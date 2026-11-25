"""Read back each saved 250-us boundary and trace without integrating another physical step."""
import numpy as np
import torch
from scripts.b0.pregrasp_response import OUT, RAW, Scene, DEVICE, tensor, records, read, write
from learning.b0.contact_model import contact_state
from learning.b0.model import RobotActor


@torch.no_grad()
def verify(s,k):
    folder=s.start_dir(k)
    hist,previous=s.reload(k)
    with np.load(folder/'solver.npz') as solver:
        fields=dict(records(s.plant.sim.wp_data))
        for name,field in fields.items():
            np.testing.assert_array_equal(field.numpy(),solver[name])
    receipt=read(OUT/f'response_reload_{s.side}_{k}.json')
    trace=np.load(folder.parent/'frame0_trace.npy')
    boundary=trace[k-1]
    np.testing.assert_array_equal(boundary[1:33],s.plant.data.qpos[0].cpu().numpy())
    np.testing.assert_array_equal(boundary[33:64],s.plant.data.qvel[0].cpu().numpy())
    np.testing.assert_array_equal(boundary[64:87],previous[0].cpu().numpy())
    old=[]
    for j in range(k-9,k+1):
        row=trace[j-1]
        physical=contact_state(tensor(row[1:33])[None],tensor(row[33:64])[None])
        old.append(s.sense(physical[:,:7],s.rep.represent(physical),tensor(row[64:87])[None]))
    remade=torch.stack(old,1)
    aux,rep=s.state()
    obs,_=s.obs(k,hist,aux,rep)
    decoder=RobotActor.raw(s.actor,obs)
    canonical=s.actor.home_action+s.actor.standard_action*decoder
    torch.testing.assert_close(canonical,s.actor.raw(obs),atol=0,rtol=0)
    bound=torch.load(folder/'boundary.pt',map_location='cpu',weights_only=False)
    assert all(torch.equal(getattr(s.plant,n).cpu(),v) for n,v in bound['counters'].items())
    np.testing.assert_array_equal(np.load(folder/'continuous_successor.npz')['q'][0],trace[k,1:33])
    diff=(remade-hist).abs().max().item()
    write(OUT/f'response_reload_{s.side}_{k}.json',dict(receipt,start_solver_arrays_bitwise_equal=True,
          exact_start_fields=len(fields),saved_physics_dt=s.model.opt.timestep,frame0_start_q_v_previous_exact=True,
          full_history_reconstruction_max_abs=diff,start_counters_and_servo_bias_bitwise_equal=True,
          saved_initial_history_shape=list(hist.shape),saved_context=s.ctx[0].cpu().tolist(),original_effort_map_exact=True,
          discrete_successor_counters_exact=all(receipt['max_abs'][n]==0 for n in
              ('reason','fail','steps','load_ticks','lost_ticks','slip_ticks','sat_ticks','saturation_time')),
          saved_continuous_successor_matches_frame0_trace=True,extra_physical_steps_for_readback=0))


if __name__=='__main__':
    for side in ('pull','push'):
        s=Scene(side)
        for k in read(OUT/f'response_reconstruction_{side}.json')['reached']:
            verify(s,k)
