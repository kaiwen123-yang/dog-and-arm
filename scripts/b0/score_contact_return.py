"""Score newly measured, stopping-rule-aware contact trajectories on their fixed physical clock."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_model import ContactRepresentation, contact_state
from learning.b0.contact_reward import reward_terms
from learning.b0.evaluate import ErrorMeasures
from learning.b0.model import full_state, tensor
from learning.b0.physics import ActionMap, make_model


SCORE_PROTOCOL = 'fixed_effort_successor_2ms_v1'
SUBSTEP_S = .002
MAX_RATE = .5 + .5 + 1. + 1. + 1. + 1.


def save_json(path, data):
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


@torch.no_grad()
def score_case(record, reference, model):
    raw = Path(record['raw_directory'])
    ticks, actions, q, v = [np.load(raw/(key+'.npy'), mmap_mode='r')
                            for key in ('physics_step','clipped_action','qpos','qvel')]
    start, end = record['start_substep'], record['reference_phase_end_substep']
    steps = np.diff(ticks)
    if (not end > start or ticks[0] != 0 or ticks[-1] != record['physics_steps']
            or ticks[-1] > end-start or len(actions) != len(steps) or len(q) != len(ticks)
            or len(v) != len(ticks) or np.any((steps <= 0) | (steps > 10))):
        raise ValueError(f'Inconsistent measured or planned boundaries at {raw}')
    planned_s = (end-start)*SUBSTEP_S
    score = dict(protocol=SCORE_PROTOCOL,
                 scope='full_from_start' if record['segment']=='full' else 'segment_from_registered_start',
                 side=record['side'], segment=record['segment'], episode=record['episode'],
                 backend=record['backend'], physical_passed=record['passed'], case=raw.name,
                 prefix_excluded_substeps=record['prefix_physics_steps'],
                 previous_action_valid_at_start=record['score_initial_previous_action_valid'],
                 reference_query='registered reference substeps/qpos,qvel at start+executed interval end (2 ms grid)',
                 score_hold='after the original terminal event, preserve its physical constraints and readiness through reference end',
                 planned_start_substep=start, planned_end_substep=end, executed_substeps=int(ticks[-1]),
                 absorbed_substeps=int(end-start-ticks[-1]), planned_duration_s=planned_s,
                 measured_duration_s=float(ticks[-1]*SUBSTEP_S), equivalent_planned_20ms=planned_s/.02,
                 max_positive_reward_per_20ms=MAX_RATE*.02, denominator=planned_s*MAX_RATE,
                 first_failure=record['score_first_failure'],
                 measured_peak_net_force_n=record['measured_peak_net_force_n'],
                 physical_gate_pass_step=record['physical_gate_pass_step'], physical_wall_seconds=record['physical_wall_seconds'])
    if not len(steps) or not np.isfinite(q).all() or not np.isfinite(v).all():
        score.update(normalized_fixed_effort=None, normalized_canonical=None, tracking_errors=None,
                     unavailable='no finite measurable policy successor')
        return score
    if ticks[-1] < end-start and record['score_first_failure'] is None:
        raise ValueError(f'Unexecuted score suffix without a failure at {raw}')
    query = start + ticks[1:]
    ref_q, ref_v = [np.load(reference/'substeps'/(name+'.npy'),mmap_mode='r')[query]
                    for name in ('qpos','qvel')]
    phases = np.load(reference/'substeps/phase.npy', mmap_mode='r')
    labels = np.asarray(json.loads((reference/'metadata.json').read_text())['phases'])
    reference_phase = labels[phases[query-1]]
    previous = np.concatenate((np.asarray(record['score_initial_previous_action'])[None],actions[:-1]))
    valid = np.ones(len(actions), dtype=bool)
    valid[0] = record['score_initial_previous_action_valid']
    device = 'cpu'
    rep = ContactRepresentation(model, device)
    state = contact_state(tensor(q[1:],device),tensor(v[1:],device))
    r_q,r_v = tensor(ref_q,device),tensor(ref_v,device)
    ref_state = full_state(r_q,r_v)
    targets = rep.fk(r_q[:,:3],r_q[:,3:7],r_q[:,7:31],ref_state[:,31:34],
                     ref_state[:,34:37],r_v[:,6:30])
    dt = tensor(steps*SUBSTEP_S,device)
    arrays = dict(reference_query_substep=query, elapsed_substeps=steps,
                  previous_action_valid=valid,reference_endpoint_phase=reference_phase)
    sums = {}
    for coordinates in ('fixed_effort','canonical'):
        terms = reward_terms(rep,rep.represent(state),state[:,:7],tensor(actions,device),
                             tensor(previous,device),targets,coordinates=coordinates,
                             previous_valid=torch.from_numpy(valid),dt=dt)
        parts = {name: value.detach().cpu().numpy().reshape(-1).astype(np.float64)
                 for name,value in terms.items()}
        if any(values.shape != steps.shape for values in parts.values()):
            raise ValueError('Reward terms must contain one scalar per measured interval')
        sums[coordinates] = {name:float(values.sum()) for name,values in parts.items()}
        values = sum(parts.values())
        score['normalized_'+coordinates] = float(values.sum()/score['denominator'])
        arrays.update({f'{coordinates}_{name}':part for name,part in parts.items()})
        if coordinates == 'fixed_effort':
            score['reference_phase_contributions'] = {
                str(phase): dict(measured_reward=float(values[reference_phase==phase].sum()),
                                 contribution_to_case=float(values[reference_phase==phase].sum()/score['denominator']))
                for phase in np.unique(reference_phase)}
    measures = ErrorMeasures(model)
    score['tracking_errors'] = measures.compare(q[1:],v[1:],ref_q,ref_v)
    score['error_samples'] = 'unweighted measured control-interval endpoints including any last partial interval'
    score['signed_reward_term_sums'] = sums
    delta = np.asarray(actions[0])-previous[0]
    score['first_canonical_action_l2_jump_from_applied'] = (float(np.linalg.norm(delta)) if valid[0] else None)
    score['first_piper_j2_jump_rad'] = (float(delta[17]*ActionMap(model).scale[17]) if valid[0] else None)
    np.savez(raw/'return_intervals.npz',**arrays)
    return score


def main(output):
    plan = json.loads((output/'run_spec.json').read_text())['plan']
    if plan.get('score_protocol') != SCORE_PROTOCOL:
        raise ValueError('Scoring requires a prospective run under this protocol')
    inherited_file = output/'inherited_cases.json'
    inherited = set(json.loads(inherited_file.read_text())['cases']) if inherited_file.is_file() else set()
    rows = []
    for path in sorted(output.glob('*/*/*/result.json')):
        record = json.loads(path.read_text())
        side = 'mobile' if record['side']=='pull' else 'push'
        case = record['perturbation'].get('p6_case',1)
        score_path = path.with_name('return.json')
        if str(path.parent.relative_to(output)) in inherited:
            score = json.loads(score_path.read_text())
            if score['protocol'] != SCORE_PROTOCOL or score['executed_substeps'] != record['physics_steps']:
                raise ValueError(f'Incompatible inherited return at {score_path}')
        else:
            score = score_case(record,Path(plan['source'])/record['episode'],make_model(side,case))
            save_json(score_path,score)
        rows.append(dict(group='/'.join(path.relative_to(output).parts[:2]),
                         case=path.parent.name,passed=record['passed'],measured_substeps=score['executed_substeps'],
                         planned_substeps=score['planned_end_substep']-score['planned_start_substep'],
                         normalized_fixed_effort=score['normalized_fixed_effort'],
                         normalized_canonical=score['normalized_canonical'],
                         net_force_peak_n=score['measured_peak_net_force_n'],
                         first_piper_j2_jump_rad=score.get('first_piper_j2_jump_rad'),
                         failure=(record['score_first_failure'] or {}).get('reason')))
    if not rows:
        raise ValueError('No physical cases available for scoring')
    save_json(output/'returns.json',dict(protocol=SCORE_PROTOCOL,checkpoint=plan['checkpoint'],
              primary_coordinates='fixed_effort',manifest=plan['manifest'],rows=rows))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    main(parser.parse_args().output)
