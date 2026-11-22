"""No CAN. Run the real H0 CLI with a deterministic transport replay from the 22 Nov a01 hold.
The recorded stationary interval is extended for the three-second timeout.
ACK after the measured hold is a simulated branch. 22 Nov hardware corroboration is separate.
"""
import argparse, contextlib, csv, importlib.util, io, json, math, os, struct, sys, tempfile, time, types
from pathlib import Path
from unittest.mock import patch

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sender',type=Path,default=Path(__file__).resolve().parents[1]/'scripts/h0_operator_motion.py')
parser.add_argument('--case',choices=['unconfirmed','fault','moving','stale_motor','hold_nack','manual','normal','no_new_status','out_of_bounds','motor_motion','ack_jitter','gap','send_error','manual_during_hold','posthold_drift','disabled_start'],default='unconfirmed')
args=parser.parse_args()
spec=importlib.util.spec_from_file_location('h0_replay',args.sender)
h0=importlib.util.module_from_spec(spec);spec.loader.exec_module(h0)
fixture_path=Path(__file__).with_name('h0_arrival_feedback.json')
record=json.loads(fixture_path.read_text())['t18' if args.case=='ack_jitter' else 'a01']
qrows=[record['q_unique'][index] for index in record['q_order']]
q=qrows[-1][:]
endstatus=record['status']
motors=[struct.unpack('>hhi',bytes.fromhex(packet)) for packet in record['motor_packets']]
flags=record['flags']
goal=[-24.9,13.,-15.4,.1,9.2,21.8]
if args.case=='ack_jitter':goal=[4.7,32.9,-31.1,6.3,14.9,.3]
class Clock:
    def __init__(self): self.t=0.;self.start=time.time()
    def monotonic(self):return self.t
    def time(self):return self.start+self.t
    def monotonic_ns(self):return round(self.t*1e9)
    def time_ns(self):return round(self.time()*1e9)
    def sleep(self,v):self.t+=v
ts=Clock()
calls=[];phase_at_tx=[];fake_comm=types.SimpleNamespace(send=lambda *a:None,send_bus=types.SimpleNamespace(send=lambda *a:None))
class ReplayDevice:
    def __init__(self):
        self.phase='observe';self.robot=self;self.feedback=[];self.anchor_sent=False;self.sequence=0;self.started=False
    def connect(self):pass
    def disconnect(self):pass
    def get_config(self):return {'joint_limits':{f'joint{i}':([0,math.pi] if i==2 else [-math.pi,0] if i==3 else [-math.pi,math.pi]) for i in range(1,7)}}
    def get_context(self):return types.SimpleNamespace(get_comm=lambda:fake_comm)
    def get_driver_states(self,i):
        state=dict(flags[i-1])
        if args.case=='disabled_start':state['driver_enable_status']=False
        if args.case=='fault' and ts.t>1.0:state['collision_status']=True
        return types.SimpleNamespace(timestamp=ts.time(),msg=types.SimpleNamespace(foc_status=types.SimpleNamespace(to_dict=lambda:state)))
    def get_arm_status(self):
        stamp=ts.time()- (10 if self.anchor_sent and args.case=='no_new_status' else 0)
        return types.SimpleNamespace(timestamp=stamp,msg=types.SimpleNamespace(motion_status=1 if args.case=='hold_nack' else 0))
    def set_auto_set_motion_mode_enabled(self,value):pass
    def set_speed_percent(self,p):pass
    def electronic_emergency_stop(self):calls.append('damping_estop')
    def move_j(self,angles):
        self.started=True
        if 'hold' in self.phase and self.phase!='initial_hold':
            self.anchor_sent=True;calls.append('measured_hold')
            if args.case=='send_error':raise OSError('transport send failed')
            if args.case=='manual_during_hold':raise KeyboardInterrupt('operator stop during hold')
            if max(abs(a-b) for a,b in zip(angles,q))>1e-8:raise AssertionError('hold did not use measured position')
        phase_at_tx.append(self.phase)
    def state(self,after=None,enabled=True):
        if self.started and args.case=='manual' and ts.t>1:raise KeyboardInterrupt('operator')
        self.sequence+=1
        s=dict(endstatus)
        s['motion_status']=0 if (not self.started or args.case in ('normal','ack_jitter') or self.anchor_sent and args.case!='hold_nack') else 1
        vals=q.copy()
        if args.case=='disabled_start':vals[1:3]=list(map(math.radians,[-3.172,.207]))
        if args.case=='ack_jitter' and self.started:
            real=qrows[int(ts.t*200)%len(qrows)]
            vals=real[:]
        if args.case=='gap' and after is not None:ts.sleep(.15)
        if self.started and args.case=='moving':vals[5]+=math.radians(.15*math.sin(18*ts.t))
        if self.started and args.case=='out_of_bounds':vals[1]=-.01
        row={'sequence':self.sequence,'monotonic_s':ts.t,'can_timestamp_s':ts.time()}
        for i,v in enumerate(vals,1):
            row[f'q{i}_rad']=v
            row[f'motor{i}_timestamp_s']=ts.time()-(1 if args.case=='stale_motor' else 0)
            row[f'motor{i}_position_rad']=motors[i-1][2]*.001 + (.004*math.sin(18*ts.t) if self.started and args.case=='motor_motion' and i==1 else .01 if self.anchor_sent and args.case=='posthold_drift' and i==1 else 0)
            row[f'motor{i}_velocity_rad_s']=motors[i-1][0]*.001
        self.feedback.append(row)
        return row,s
    @staticmethod
    def angles(row):return [row[f'q{i}_rad'] for i in range(1,7)]
    def enable_at(self,*a):raise AssertionError('must never enable')
    def reset(self,*a):raise AssertionError('must never reset')
module=types.ModuleType('piper_oscbf.device');module.PiperDevice=ReplayDevice
with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules,{'piper_oscbf.device':module}),patch.object(h0,'time',ts):
    path=Path(tmp)
    h0.open=lambda name,*a,**kw: open(path/'isolated_sender.lock',*a,**kw)
    for name in ['camera_live.json','arm_live.json']:(path/name).touch()
    argv=['h0',tmp,'--calibration-target-deg',*map(str,goal),'--execute']
    code=0
    with patch.object(sys,'argv',argv),contextlib.redirect_stdout(io.StringIO()):
        try:h0.main()
        except SystemExit as e:code=e.code
    report=json.loads((path/'calibration_pose_summary.json').read_text())
    print(json.dumps(dict(case=args.case,exit_code=code,completed=report['command_sequence_completed'],calls=calls,error=report['error'],final_status=report.get('final_status')),default=str))
    if args.case=='unconfirmed':assert code==1 and not report['command_sequence_completed'] and calls==['measured_hold']
    elif args.case=='ack_jitter':assert code==1 and not report['command_sequence_completed'] and not calls and report.get('stop_action')=='original_target_acknowledged'
    elif args.case=='disabled_start':assert code==1 and not report['command_sequence_completed'] and not calls and not phase_at_tx
    elif args.case=='normal':assert code==0 and report['command_sequence_completed'] and not calls
    else:assert code==1 and not report['command_sequence_completed'] and calls[-1]=='damping_estop'
