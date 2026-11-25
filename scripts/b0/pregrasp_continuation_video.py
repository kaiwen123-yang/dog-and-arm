"""Render saved continuous trajectories at original speed and index the four diagnostic cases."""
import argparse
import csv
import json
from pathlib import Path
import subprocess

import mujoco as mj
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from learning.b0.physics import build, settings
from scripts.b0.pregrasp_continuation import DT, FULL_DOOR_PHASES, OUT, RAW, read, write


def render(case):
    receipt=read(OUT/'continuation'/case/'continuation.json')
    cfg=settings('mobile' if receipt['side']=='pull' else 'push',1)
    model=build(cfg)
    data=mj.MjData(model)
    directory=OUT/'continuation'/case
    video=directory/'reference_clock_1x.mp4'
    temporary=directory/'reference_clock_1x.partial.mp4'
    with np.load(receipt['trajectory']) as z:
        q=z['qpos']
        metrics=z['interval_metrics']
        formal=z['formal_phase']
        reference=z['reference_phase']
        keys=list(z['metric_names'])
        queries=z['query_start_step']
    stop, seal=receipt['physical_step'],receipt['sealed_step']
    assert len(q)==stop+1 and len(metrics)==len(formal)==len(reference)==stop
    np.testing.assert_array_equal(queries,np.arange(0,stop,10))
    # Retain the native 40 ms sampling grid and place the final off-grid state at its exact PTS.
    steps=list(range(0,stop,20))+[stop]
    pts=f"settb=1/500,setpts='if(eq(N,{len(steps)-1}),{stop},20*N)'"
    cmd=['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','640x448',
         '-framerate','500','-i','pipe:0','-an','-vf',pts,'-vsync','vfr','-enc_time_base','1:500',
         '-c:v','libx264','-threads','2','-bf','0','-preset','fast','-crf','21','-pix_fmt','yuv420p',
         '-movflags','+faststart',str(temporary)]
    font_path=Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')
    font=ImageFont.truetype(str(font_path),14) if font_path.exists() else ImageFont.load_default()
    with mj.Renderer(model,height=336,width=640) as renderer, subprocess.Popen(cmd,stdin=subprocess.PIPE) as writer:
        for k in steps:
            # Contact rows describe the interval-start solve. For the terminal image show the last solved interval.
            i=min(k,stop-1)
            row=metrics[i]
            data.qpos[:]=q[k]
            mj.mj_forward(model,data)
            renderer.update_scene(data,camera='p6_overview')
            frame=Image.new('RGB',(640,448),'#151a26')
            frame.paste(Image.fromarray(renderer.render()),(0,0))
            draw=ImageDraw.Draw(frame)
            title=f'{receipt["side"].upper()}   {receipt["backend"]} MuJoCo {receipt["mujoco"]}   u10000   {k*DT:6.3f} s   1x'
            actual=FULL_DOOR_PHASES[formal[i]] if formal[i]>=0 and k<seal else 'sealed / '+str(receipt['sealed_phase'])
            warning=k>=seal
            desc=f'Official first failure {receipt["sealed_failure"]} at {seal*DT:.3f} s'
            if warning:
                draw.rectangle((0,0,640,23),fill='#732e2b')
                draw.text((9,3),'FORMAL VERDICT SEALED   |   diagnostic observation',font=font,fill='white')
            analog=(f'Door {row[keys.index("door_deg")]:7.3f} deg   net {row[keys.index("door_net_N")]:6.3f} N   '
                    f'fingers {row[keys.index("left_N")]:6.3f} / {row[keys.index("right_N")]:6.3f} N')
            for line,(label,color) in enumerate(((title,'white'),(desc,'#ffb88c'),
                       (f'Actual: {actual}   Reference: {FULL_DOOR_PHASES[reference[i]]}','#b0e1ee'),(analog,'white'))):
                draw.text((9,341+line*24),label,font=font,fill=color)
            writer.stdin.write(np.asarray(frame).tobytes())
        writer.stdin.close()
        if writer.wait():
            raise RuntimeError('FFmpeg encode failed')
    temporary.replace(video)
    command=['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries',
             'stream=width,height,avg_frame_rate,nb_read_frames,duration,codec_name','-of','json',str(video)]
    probe=json.loads(subprocess.check_output(command))['streams'][0]
    probe_times=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames',
        '-show_entries','frame=best_effort_timestamp_time','-of','json',str(video)])
    times=[float(frame['best_effort_timestamp_time']) for frame in json.loads(probe_times)['frames']]
    np.testing.assert_allclose(times,np.asarray(steps)*DT,atol=1e-6,rtol=0)
    assert int(probe['nb_read_frames'])==len(steps)
    assert abs(float(probe['duration'])-stop*DT)<=.040001
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
    markers=[int(k) for k in steps if k>=seal]
    entry=dict(case=case,backend=receipt['backend'],mujoco=receipt['mujoco'],side=receipt['side'],
               video=str(video),trace=receipt['trajectory'],frame0=True,playback=1,nominal_fps=25,all_frame_pts_verified=True,
               simulated_duration_s=stop*DT,first_formal_failure_s=seal*DT,first_marker_source_s=markers[0]*DT if markers else None,
               terminal_source_s=steps[-1]*DT,rendering='saved integrated states; exact final PTS on 2ms grid',
               continuous_physics_step_s=DT,full_decoder_verified=True,ffprobe=probe,bytes=video.stat().st_size,
               eligible_V0=False)
    write(directory/'video_receipt.json',entry)


def summarize():
    videos,rows=[],[]
    for backend in ('warp','native'):
        for side in ('pull','push'):
            directory=OUT/'continuation'/f'{backend}_{side}'
            videos.append(read(directory/'video_receipt.json'))
            r=read(directory/'continuation.json')
            comp=read(directory/'archive_comparison.json')
            term=r['reference_physical_first_failure'] or {}
            tail=r['diagnostic']
            rows.append(dict(backend=backend,side=side,formal_passed=r['passed'],
                formal_reason=r['sealed_failure'],formal_step=r['sealed_step'],archive_same_step=comp['same_steps'],
                archive_same_reason=comp['same_reason'],archive_same_event_steps=comp['same_event_phase_steps'],
                archived_absorbing_score=comp['archived_fixed_effort'],measured_absorbing_score=comp['measured_fixed_effort'],
                absorbed_steps=comp['absorbed_steps'],next_actor_query_step=r['next_query_after_seal'],
                end_step=r['physical_step'],ref_end_step=r['reference_last_step'],end_reason=r['terminal'],
                ref_monitor_reason=term.get('reason'),ref_monitor_first_step=term.get('step'),
                ref_monitor_phase=term.get('reference_phase'),tail_steps=tail['elapsed_steps'],
                tail_dual_contact_ticks=tail.get('dual_ticks'),tail_longest_gripped_ticks=tail.get('longest_gripped_ticks'),
                tail_min_deg=tail.get('min_door_deg'),tail_max_deg=tail.get('peak_door_deg'),tail_peak_net_N=tail.get('max_net_N'),
                tail_target_angle_ticks=tail.get('target_angle_ticks'),tail_gripped_at_target_ticks=tail.get('gripped_at_target_ticks'),
                tail_release_after_gripped=tail.get('observed_release_after_gripped'),
                post_timeout_qualified=False,trace=r['trajectory'],seal=str(directory/'result.json')))
    with (OUT/'reference_clock_continuation_cases.csv').open('x',newline='') as stream:
        w=csv.DictWriter(stream,list(rows[0]),lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    write(OUT/'diagnostic_video_manifest.json',dict(purpose='four continuous reference-clock diagnoses; official first result frozen',
                                                    successful_full_V0=0 if not any(r['formal_passed'] for r in rows) else None,
                                                    videos=videos))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('case',choices=['native_pull','native_push','warp_pull','warp_push','index'])
    arg=p.parse_args().case
    summarize() if arg=='index' else render(arg)
