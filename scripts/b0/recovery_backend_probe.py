"""Replay identical 20 ms targets to locate engine differences at 2 ms resolution."""
import argparse
import csv
import json
from pathlib import Path

import mujoco as mj
import numpy as np

from learning.b0.contact_events import FrozenDoorReference
from learning.b0.physics import ActionMap, ContactMeter, build
from scripts.b0.eval_contact_segments import WarpSingleWorld

DEFAULT_SOURCE = Path('results/raw_large/b0/full_warp_hold_park_r1')
MODEL_FIELDS = (
    'body_mass', 'body_inertia', 'body_ipos', 'body_iquat', 'jnt_range', 'dof_armature',
    'dof_damping', 'dof_frictionloss', 'actuator_gainprm', 'actuator_biasprm', 'actuator_forcerange',
    'eq_data', 'eq_solimp', 'eq_solref', 'pair_geom1', 'pair_geom2',
    'geom_type', 'geom_size', 'geom_friction', 'geom_pos', 'geom_quat', 'geom_contype',
    'geom_conaffinity', 'geom_solimp', 'geom_solref', 'geom_margin', 'geom_gap',
)
OPTION_FIELDS = (
    'timestep', 'integrator', 'solver', 'cone', 'iterations', 'tolerance', 'ls_iterations',
    'ls_tolerance', 'ccd_iterations', 'ccd_tolerance', 'impratio', 'gravity', 'jacobian',
    'disableflags', 'enableflags', 'noslip_iterations',
)


def configure(model, variant):
    if variant == 'default':
        return
    if variant in ('wheel_deepest_only', 'wheel_deepest_and_multiccd_off'):
        if mj.__version__ != '3.16.0':
            raise ValueError('This diagnostic selects the 3.16 plane/mesh deepest-point fallback')
        # mjc_PlaneConvex returns its computed support contact without adding
        # face vertices when the mesh has no polygons. Keep vertices, faces,
        # supports, inertias, friction and solver intact. Only the four wheel
        # hulls have their polygon manifold disabled in this diagnostic model.
        wheels = [i for i in range(model.ngeom) if model.geom_contype[i]
                  and model.body(model.geom_bodyid[i]).name.endswith('FOOT_LINK')]
        mesh_ids = model.geom_dataid[wheels]
        if len(set(mesh_ids)) != 4 or min(mesh_ids) < 0:
            raise ValueError('Expected four distinct wheel meshes')
        model.mesh_polynum[mesh_ids] = 0
        if variant == 'wheel_deepest_and_multiccd_off':
            model.opt.disableflags |= int(mj.mjtDisableBit.mjDSBL_MULTICCD)
    elif variant.startswith('ccd_iterations'):
        model.opt.ccd_iterations = int(variant.rsplit('_', 1)[1])
    elif variant == 'multiccd_on':
        model.opt.enableflags |= int(mj.mjtEnableBit.mjENBL_MULTICCD)
    elif variant == 'multiccd_off':
        model.opt.disableflags |= int(mj.mjtDisableBit.mjDSBL_MULTICCD)
    else:
        raise ValueError(variant)


def write_case(path, backend, variant, output):
    cfg = json.loads((path/'config.json').read_text())
    meta = json.loads((path/'metadata.json').read_text())
    model = build(cfg)
    configure(model, variant)
    slave = WarpSingleWorld(model, 'cuda:0') if backend == 'warp316' else None
    mapping = ActionMap(model)
    side = meta['task']
    meter = ContactMeter(model, 'preview_floor', 'back' if side == 'push' else 'front',
                         cfg['contact_threshold_n'], cfg['wheel_threshold_n'])
    ref = FrozenDoorReference.from_episode(path, model)
    width, prefix = 320, 100
    openings = ref.phase_bounds['open']
    starts = dict(start=0, pregrasp=ref.phase_bounds['pregrasp'][1]//10*10 - 320,
                  stable_open=((sum(openings)//2)//10)*10)
    actions = np.load(path/'action_clipped.npy', mmap_mode='r')
    q, v = [np.load(path/'substeps'/(name+'.npy'), mmap_mode='r') for name in ('qpos', 'qvel')]
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(engine=backend, variant=variant, mujoco=mj.__version__, source=str(path),
                    intervals=width, dt=model.opt.timestep, decimation=10,
                    options={name: np.asarray(getattr(model.opt, name)).tolist() for name in OPTION_FIELDS},
                    fields={name: np.asarray(getattr(model, name)).tolist() for name in MODEL_FIELDS},
                    windows={})
    for name, start in starts.items():
        begin = max(0, start-prefix)
        d = mj.MjData(model)
        # Identical source coordinates rounded once to float32, also on the two CPU engines.
        d.qpos[:], d.qvel[:] = q[begin].astype('f4'), v[begin].astype('f4')
        mj.mj_forward(model, d)
        if slave is not None:
            slave.reset(d)
        window = dict(first_source_interval=begin, scored_source_interval=start,
                      prefix_intervals=start-begin, initial_q=d.qpos.tolist(), initial_v=d.qvel.tolist(),
                      sampled_solved_contacts={})
        manifest['windows'][name] = window
        with (output/(name+'.csv')).open('x') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(['source_tick', 'ncon', 'nefc', 'door_post_deg', 'net_N', 'both',
                             *['wheel_'+label+'_N' for label in meter.wheel_labels], 'finger1_N', 'finger2_N',
                             *['root_post_'+axis+'_m' for axis in 'xyz'],
                             *['tcp_start_'+axis+'_m' for axis in 'xyz'],
                             *['tcp_minus_handle_start_'+axis+'_m' for axis in 'xyz']])
            for k in range(begin, start+width):
                servo = ((mapping.offset+mapping.scale*actions[k//10])*mapping.finger_factor).astype('f4')
                if slave is None:
                    d.ctrl[mapping.actuator_ids] = servo + d.qfrc_bias[mapping.dof]*mapping.bias_gain
                    mj.mj_step(model, d)
                else:
                    slave.step(d, servo)
                details = k in {begin, start, start+width-1}
                c = meter.measure(d, details=details)
                if details:
                    window['sampled_solved_contacts'][k] = c.rows
                tcp = d.site('p4_grasp').xpos
                writer.writerow([k,d.ncon,d.nefc,np.rad2deg(d.qpos[-1]),np.linalg.norm(c.door_force),
                                 int(c.both),*c.normal,*c.finger_normal,*d.qpos[:3],
                                 *tcp,*(tcp-d.site(cfg['handle_site']).xpos)])
        if slave:
            window['capacity'] = slave.capacity()
    (output/'model_and_windows.json').write_text(json.dumps(manifest, indent=1, allow_nan=False)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine', required=True, choices=('native33', 'cpu316', 'warp316'))
    p.add_argument('--variant', default='default', choices=('default', 'ccd_iterations_35',
                   'ccd_iterations_50', 'multiccd_on', 'multiccd_off', 'wheel_deepest_only', 'wheel_deepest_and_multiccd_off'))
    p.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if mj.__version__ != ('3.3.0' if args.engine == 'native33' else '3.16.0'):
        p.error('Wrong interpreter for engine')
    for folder in ('pull_60_train','push_25_train'):
        write_case(args.source/folder, args.engine, args.variant,
                   args.output/(args.engine+'_'+args.variant)/folder.split('_')[0])


if __name__ == '__main__':
    main()
