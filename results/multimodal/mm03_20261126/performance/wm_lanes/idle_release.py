"""Measure project-owned GPU/host memory at a drained inference-service replacement."""
from pathlib import Path
import subprocess
import time
from scripts.multimodal.mm03_rotate import clients,rotate
from scripts.multimodal.mm03_launch import read,write,now,alive
from scripts.multimodal.mm03_b_parallel import host_memory
out=Path(__file__).resolve().parent
root=out.parents[1]
def device():
    gpu=subprocess.check_output(['nvidia-smi','-i','0','--query-compute-apps=pid,used_gpu_memory','--format=csv,noheader,nounits'],text=True)
    return {int(line.split(',')[0]):int(line.split(',')[1]) for line in gpu.splitlines() if ',' in line}
def snap():
    pid=read(root/'service/serving.json')['pid'];proc=Path('/proc')/str(pid)
    state={line.split(':')[0]:line.split(':')[1].strip() for line in (proc/'status').read_text().splitlines() if ':' in line}
    roll={line.split(':')[0]:line.split(':')[1].strip() for line in (proc/'smaps_rollup').read_text().splitlines() if ':' in line}
    gpu=device()
    return dict(at=now(),pid=pid,anonymous_bytes=int(state['RssAnon'].split()[0])*1024,
                pss_bytes=int(roll['Pss'].split()[0])*1024,private_dirty_bytes=int(roll['Private_Dirty'].split()[0])*1024,
                gpu_MiB=gpu.get(pid,0),active_clients=len(clients(pid,root)),host_available=host_memory()[1],
                other_gpu_MiB=sum(v for k,v in gpu.items() if k!=pid),
                total_gpu_free_MiB=int(subprocess.check_output(['nvidia-smi','-i','0','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip()))
def replace(label,reason,require_idle):
    output=out/(label+'.json')
    if output.exists():return read(output)
    b=read(root/'status/B.json');assert alive(b)
    before=snap()
    if require_idle:assert before['active_clients']==0
    rotate(root,reason)
    after=snap()
    rotation=read(root/'service/rotation.json')
    assert rotation['stage']=='complete' and rotation['reason']==reason
    assert rotation['original_clients_at_retirement']==rotation['interim_clients_at_retirement']==0
    assert alive(b) and read(root/'status/B.json')['pid']==b['pid']
    record=dict(before=before,after=after,reason=reason,rotation_id=rotation['id'],B_pid=b['pid'],B_attempt=b['attempt'],
                gpu_released_MiB=before['gpu_MiB']-after['gpu_MiB'],anonymous_released_MiB=(before['anonymous_bytes']-after['anonymous_bytes'])/2**20,
                private_dirty_released_MiB=(before['private_dirty_bytes']-after['private_dirty_bytes'])/2**20,
                pss_released_MiB=(before['pss_bytes']-after['pss_bytes'])/2**20,zero_clients_at_retirement=True,extra_optimizer_updates=0,extra_native_steps=0)
    write(output,record);print(now(),label,record['gpu_released_MiB'],record['anonymous_released_MiB'],flush=True);return record
if __name__=='__main__':
    replace('r49_idle_release','Measure retired idle inference cache after the R49 collecting barrier',True)
