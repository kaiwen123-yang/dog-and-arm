"""Check the saved first draws against their actual physical histories and WM targets."""
import numpy as np
import torch
from scripts.b0.official_flow import OUT, RAW, io


def verify():
    rec=io.read(OUT/'first_update.json')
    snap=torch.load(RAW/'resume_000001/state.pt',weights_only=False,map_location='cpu')
    replay=snap['replay']
    pack=torch.load(RAW/'checkpoint_000001.pt',weights_only=False,map_location='cpu')
    initial=torch.load(RAW/'checkpoint_000000.pt',weights_only=False,map_location='cpu')
    assert replay['clock']==rec['tick']
    def field(lanes,frame,key):
        page,offset=divmod(frame,replay['page_size'])
        dest=None
        for p in np.unique(page):
            ix=page==p
            sample=replay['pages'][int(p)][key][offset[ix],lanes[ix]].numpy()
            if dest is None:
                dest=np.empty((*frame.shape,*sample.shape[1:]),dtype=sample.dtype)
            dest[ix]=sample
        return dest
    rows=[]
    probe={}
    with np.load(OUT/'first_draws.npz') as groups:
        for name,ij in groups.items():
            lanes,t=ij.T
            h=1 if name=='actor' else 7
            frames=t[:,None]+np.arange(h)
            lanes=np.broadcast_to(lanes[:,None],frames.shape)
            assert field(lanes,frames,'valid').all()
            episodes=field(lanes,frames,'episode')
            assert np.all(episodes==episodes[:,:1])
            if h>1:
                next_state=field(lanes[:,:-1],frames[:,:-1],'next_state')
                np.testing.assert_array_equal(next_state,field(lanes[:,1:],frames[:,1:],'state'))
                np.testing.assert_array_equal(field(lanes[:,:-1],frames[:,:-1],'action'),
                                              field(lanes[:,1:],frames[:,1:],'prev_action'))
            actions=field(lanes,frames,'action')
            processed=actions*pack['dyn']['action_scale'].numpy()+pack['dyn']['action_offset'].numpy()
            assert np.isfinite(processed).all() and abs(actions).max()<=1
            rows.append(dict(group=name,samples=len(ij),scored_successors=h if h==7 else None,
                episodes=len(np.unique(episodes)),sides=np.unique(field(lanes,frames,'sim_ctx')[...,0]).tolist(),
                terminal_rows=int(field(lanes,frames,'terminated').sum())))
            if name=='actor':
                probe=dict(first_lane_tick=ij[0].tolist(),motion_time=int(field(lanes,frames,'motion_time')[0,0]),
                    history_shape=list(field(lanes[:1],frames[:1],'history').shape),
                    real_action=actions[0,0].tolist(),real_processed=processed[0,0].tolist(),
                    sim_context=field(lanes[:1],frames[:1],'sim_ctx').reshape(-1).tolist())
    weight_delta={k:max(float((a-initial[k][key]).abs().max()) for key,a in pack[k].items()
                        if key.endswith('weight')) for k in ('actor','critic','dyn')}
    assert min(weight_delta.values())>0
    old_path=RAW.parent/'joint_contact_20261124/collection/train/state.pt'
    old=torch.load(old_path,map_location='cpu',weights_only=False,mmap=True)
    historical_context=torch.cat([data['sim_ctx'][starts[1][:,0],starts[1][:,1]]
                                  for data,starts in old['chunks']]).unique(dim=0)
    expected=torch.tensor(io.read(OUT/'interface.json')['pull_push_context'])
    torch.testing.assert_close(historical_context,expected,rtol=0,atol=0)
    io.write(OUT/'first_draw_recheck.json',dict(groups=rows,first_policy_start=probe,
        historical_context_source=str(old_path),historical_context_exact=historical_context.tolist(),
        parameter_max_abs_changes=weight_delta,wm_stored_frames=8,h7_sampled_successors=10*2048*7,
        h32_initial_states=4096,ratio=rec['ratio'],normalization_before=io.read(OUT/'interface.json')['normalizers'],
        normalization_after=rec['statistics'],exact_state_adjacency=True,exact_previous_action_adjacency=True))


if __name__=='__main__':
    verify()
