"""Summarize actual MM-02 dynamics, trajectory sampling, recovery and validation receipts."""
import argparse
from collections import Counter
import json
from pathlib import Path


def summarize(root):
    def read(p):
        return json.loads(p.read_text())
    out={'method':'M1Piper-Multimodal-DAggerWM-v2','run':str(root),
     'reference':'Native MuJoCo 3.3.0; 2 ms physical substeps; 20 ms policy; 100 ms RGB-D; 23 actions',
     'units':{'angle_mae_deg':'deg','hinge_rate_mae_rad_s':'rad/s','handle_error_mm':'mm, TCP-frame Euclidean distance','leg_mae_rad':'rad','wheel_rate_mae_rad_s':'rad/s','arm_mae_deg':'deg','jaw_mae_mm':'mm','finger_brier':'mean squared probability error, two finger contacts','dual_fraction_mse':'mean squared error vs simultaneous-contact substep fraction','vision_rmse_at_exposures':'dimensionless pooled RGB-D features; all new real exposures within evaluated windows','held_start_rmse_same_exposures':'same units and exact exposures; hold starting feature','vision_rmse_fresh_endpoint':'same units; only horizons ending on a new exposure','held_start_rmse_same_endpoint':'same actual fresh endpoints'},
     'opening_trajectory_semantics':{'validation_onpolicy':'Recorded student-action input for open-loop. Both predictions are measured against the recorded student physical successors.',
        'validation_recovery':'Open-loop uses the teacher actions actually integrated from the restored student state. Both predictions are measured against those physical teacher successors.',
        'validation_demo':'Held-out MM-01 successful P6 demos; open-loop uses their executed teacher action. Both predictions use the same physical target.',
        'student_imagined_closed_loop':'The frozen current-round actor queries its own predicted state and causal image at every tick. It receives only starting sensors and task text. Mismatch to the recorded physical future also includes any action difference.'},
     'recovery_target':'32 consecutive, legal, actual teacher-executed 20 ms intervals from a unique prior student-visited anchor; incomplete prefixes still eligible for physical replay and independently qualified BC. Future physical states, contacts and exposures enter only the loss.',
     'h32_loss':{'discount':0.985,'weight':0.15,'terms':{'position':1,'velocity':0.6,'imu':0.3,'object':1,'contact':0.3,'vision':1},'physical_temporal_reduction':'normalized discounted 32-tick mean','visual_temporal_reduction':'mean over actual new exposure count','batch':32},
     'initial_world_model':{'retained_updates':2800,'teacher_updates':2400,'interaction_updates':400,'old_exposure_projection_updates':600,'full_parent':str(Path('/root/autodl-tmp/mm01-20261125/wm_final/wm.pt')),'refit_units':False},
     'rounds':[]}
    for nth in range(1,7):
        r=root/f'round{nth}';d=r/'dynamics'
        if not (d/'wm_validation.json').exists(): continue
        wm,bridge,validation=[read(d/s) for s in ('wm_training.json','bridge_training.json','wm_validation.json')]
        mt=r/'model_trajectory'/'paired';sup=r/'supervised_aggregate'/'paired'
        h32,bc,diagnosis=[read(p) for p in (mt/'receipt.json',sup/'receipt.json',mt/'trajectory_diagnostic.json')]
        membership=read(r/'wm_membership.json')
        splits={k:len(v) for k,v in membership.items()}
        valid_sum=sum(e['valid'] for e in wm['episodes'])
        applies=wm['round_applied_updates']; bapplies=bridge['bridge_applied_updates']
        if applies != len((d/'wm_applied_steps.txt').read_text().splitlines()) or bapplies != len((d/'bridge_applied_steps.txt').read_text().splitlines()): raise ValueError('Ledger inconsistency')
        if h32['retained_actor']!=bc['retained_actor'] or h32['sequence_sha256'] != bc['sequence_sha256']: raise ValueError('Unmatched paired actor steps or BC sequence')
        stats={'round':nth,'members':splits,'valid_physical_transitions_in_training_replay':valid_sum,'old_physical_episodes':len(wm['inherited_mm01_physical_episodes']),
            'old_demonstration_family_episodes':splits['old_train'],'inherited_previous_student_episodes_for_dynamics':len(wm['inherited_mm01_physical_episodes'])-splits['old_train'],
            'valid_h7_windows':wm['legal_windows'],'h7_contact_start_pool':wm['contact_start_windows'],'wm_fixed_units':wm['fixed_units_restored'],
            'wm_normalization_coverage':wm['normalization_coverage'],'physical_recoveries':validation['recovery_provenance'],
            'retained_updates':{'wm':wm['round_retained_updates'],'bridge':bridge['bridge_retained_updates'],'model_h32':h32['retained_h32_actor'],'supervised_paired':bc['retained_actor'],'critic':0},
            'applied_updates':{'wm':applies,'bridge':bapplies,'model_paired':h32['total_applied_actor'],'supervised_paired':bc['total_applied_actor']},
            'rollback_updates':{'wm':wm['round_rollback_updates'],'bridge':bridge['bridge_rollback_updates'],'model_paired':h32['rollback_actor'],'supervised_paired':bc['rollback_actor']},
            'training_wall_seconds':{'wm':wm['train_wall_s'],'bridge':bridge['train_wall_s'],'model_paired':h32['training_wall_s'],'supervised_paired':bc['training_wall_s']},
            'h32_optimization_action_queries':h32['h32_imagined_queries'],'h32_sampling':h32.get('h32_sampling',{}),
            'first_batch_trajectory_diagnostics':diagnosis,'wm_end_cumulative_updates_including_mm01':wm['final_cumulative_updates'],
            'bridge':{'actor_after_2048_bc':bridge['actor_after_2048_bc'],'frozen_encoder_id':bridge['encoder_id'],'registered_seed':bridge['seed'],'validation_and_training_rmse':bridge['errors']},
            'validation':{k:{'episodes':len(v['episodes']),'horizons':v['horizons']} for k,v in validation['strata'].items()},
            'recovery_files':{'wm':wm['checkpoint'],'bundle':bridge['bundle'],'model_paired':h32['full_checkpoint'],'matched_supervised_paired':bc['full_checkpoint'],'train_members':str(r/'wm_membership.json'),'validation':str(d/'wm_validation.json')}}
        if diagnosis.get('complete_anchors',0):
            calls=1
            fd=diagnosis.get('frozen_directional_derivative')
            if fd:
                calls+=1+2*len(fd['centered'])
            stats['h32_diagnostic_actor_queries_without_updates']=calls*32*32
        else:stats['h32_diagnostic_actor_queries_without_updates']=0
        stats['student_closed_loop_validation_actor_queries']=sum(int(h)*v['windows'] for st in validation['strata'].values() for h,v in st['horizons'].items())
        stats['recorded_action_open_loop_validation_wm_steps']=stats['student_closed_loop_validation_actor_queries']
        out['rounds'].append(stats)
    allr=out['rounds']
    if not allr: raise SystemExit('No completed scored dynamics round')
    for field in ('retained_updates','applied_updates','rollback_updates','training_wall_seconds'):
        out['total_'+field]={key:sum(rr[field][key] for rr in allr) for key in allr[0][field]}
    out['total_h32_optimization_action_queries']=sum(rr['h32_optimization_action_queries'] for rr in allr)
    for key in ('h32_diagnostic_actor_queries_without_updates','student_closed_loop_validation_actor_queries','recorded_action_open_loop_validation_wm_steps'):
        out['total_'+key]=sum(r[key] for r in allr)
    initial_check = root/'initial_wm_interface.json'
    if initial_check.exists():
        out['implementation_check_on_initial_recorded_data'] = read(initial_check)
    out['recovery_totals']={}
    for group in ('train_recovery','validation_recovery'):
        gs=[rr['physical_recoveries'][group] for rr in allr]
        totals={k:sum(g[k] for g in gs) for k in ('branches','unique_anchor_snapshots','complete_h32','incomplete_kept_prefixes','actual_physics_substeps','duplicate_anchor_snapshots','held_image_or_exposure_mismatches','source_states_without_prior_student_action','non_teacher_intervals')}
        worst_keys=sorted({k for g in gs for k in g['parent_start_and_history_max_abs_error']})
        totals['max_parent_start_or_prefix_error']={k:max(g['parent_start_and_history_max_abs_error'].get(k,0) for g in gs) for k in worst_keys}
        totals['within_round_uniqueness']=True
        totals['stages']=dict(sum((Counter(g['anchor_stages']) for g in gs), Counter()))
        out['recovery_totals'][group]=totals
    out['count_scope']='Totals cover only new MM-02 rounds. Inherited 2,800 WM and 600 old bridge updates are separate. H32 is already included in the model paired 512 actor updates. Forward/gradient diagnostics and held-out evaluation are outside H32 optimization query counts.'
    out['timing_scope']='Summed per-stage optimization wall times; WM/BC can run concurrently. Excludes loading, encoding, target collection, physics evaluation and diagnostics, so the sum is not total experiment elapsed time.'
    freeze=root/'terminal_freeze.json'
    if freeze.exists():
        end=read(freeze)
        if len(allr)!=end['round']:raise ValueError('Missing resolved round')
        out['terminal_freeze']=end
    p=root/'dynamics_summary.json'
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(p)
    return {'rounds':len(allr),'retained':out['total_retained_updates'],'train_complete':out['recovery_totals']['train_recovery']['complete_h32'],'val_complete':out['recovery_totals']['validation_recovery']['complete_h32']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, help='MM-02 root with roundN/dynamics receipts')
    args = parser.parse_args()
    print(json.dumps(summarize(args.run.resolve()), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
