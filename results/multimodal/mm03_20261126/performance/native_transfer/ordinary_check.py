import os,sys,json,time,importlib.util,subprocess,hashlib,tempfile,statistics
from pathlib import Path
import numpy as np
from scripts.multimodal.mm03_launch import read,write,now
p=Path(__file__).resolve().parent;r=Path('/root/autodl-tmp/mm03-20261126')
def load(name,file):
 s=importlib.util.spec_from_file_location(name,file);mod=importlib.util.module_from_spec(s);sys.modules[name]=mod;s.loader.exec_module(mod);return mod
newteacher=load('scripts.multimodal.correction_teacher',p/'candidate_teacher.py')
import scripts.multimodal.mm03_adapter
mod=load('scripts.multimodal.mm03_trial_episode',p/'candidate_b_physics.py')
import scripts.multimodal.mm03_inference as client
paths=[r/'B/teachers/teacher_26112600_tr_nominal_pull15',r/'B/teachers/teacher_26112600_tr_nominal_push25',
 r/'B/rounds/r21/development/rounds_r21_development_H9_1701_tr_nominal_pull15_pure']
paths.append(next(q.parent for q in sorted((r/'B/rounds/r21/collect').glob('*H9-WM*prefix*/result.json')) if read(q).get('prefix_reached') and read(q).get('success')))
def execute(source,enabled,tmp):
 record=read(source/'result.json')
 keys=['id','partition','scene','side','goal','method','mode','use','seed','round','checkpoint','group','switch_phase','train_perturbation']
 job={k:record[k] for k in keys if k in record}
 ep=source/'episode'
 if job['mode']!='teacher':
  outputs={n:np.load(ep/(key+'.npy'),mmap_mode='r') for n,key in [('raw','action_raw'),('estimate','student_estimated_vx_wz'),('high','student_high_request')]}
  class Recorder:
   def __init__(self,*a,**kw):self.tick=0
   def reset(self,*a,**kw):self.tick=0
   def step(self,*a,**kw):
    result={n:v[self.tick] for n,v in outputs.items()};self.tick+=1;return result
   def close(self):pass
  client.PolicyClient=Recorder
 root=Path(tmp);(root/'resources').mkdir();(root/'B').mkdir()
 (root/'resources/native_models').symlink_to(r/'resources/native_models',target_is_directory=True)
 if enabled:(root/'resources/ordinary_contact_reader.json').write_text('{}')
 for side in ('pull','push'):
  f=r/f'B/prefix_p6_parity_{side}.json'
  if f.is_file():(root/'B'/f.name).write_bytes(f.read_bytes())
 t=time.monotonic();row=mod.episode((str(root),job));wall=time.monotonic()-t
 dest=Path(row['raw_episode'])
 arrays={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in dest.glob('*.npy')}
 return row,arrays,wall
items=[]
for source in paths:
 group=[];ref=None
 for enabled in ((False,True,True,False) if 'development' in str(source) else (False,True)):
  with tempfile.TemporaryDirectory(dir=p) as tmp:row,arr,wall=execute(source,enabled,tmp)
  if ref is None:ref=(row,arr)
  else:
   assert ref[1]==arr,[k for k in arr if ref[1].get(k)!=arr[k]]
   for k in ('events','first_failure','physics_steps','success','ordered_event_count','teacher_steps','student_steps','unexpected_contact_steps','peak_net_door_n','max_motor_margin_violation'):
    if k in row:assert ref[0][k]==row[k],k
  group.append(dict(accelerated=enabled,wall_s=wall,substeps=row['physics_steps']));print(source.name,enabled,wall,row['physics_steps'],flush=True)
 items.append(dict(case=source.name,events=row['ordered_event_count'],success=row['success'],mode=row['mode'],arrays=len(arr),all_npy_sha256_equal=True,identical_events_and_failure=True,runs=group))
 write(p/'ordinary_partial.json',dict(cases=items,diagnostic_native_substeps=sum(x['substeps'] for c in items for x in c['runs'])))
old=sum(x['wall_s'] for c in items for x in c['runs'] if not x['accelerated'])
new=sum(x['wall_s'] for c in items for x in c['runs'] if x['accelerated'])
write(p/'ordinary_comparison.json',dict(at=now(),cases=items,reference_s=old,candidate_s=new,speedup=old/new,diagnostic_native_substeps=sum(x['substeps'] for c in items for x in c['runs']),optimizer_updates=0,scope='normal B episode entry; same recorded student commands and live teacher labels, independent integrations, all recorded arrays including RGB-D, original events and terminal/failure identity'))
