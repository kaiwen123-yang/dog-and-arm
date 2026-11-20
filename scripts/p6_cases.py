#!/usr/bin/env python3
"""Display simultaneous independent P6 trials in one live desktop window."""
import argparse
import csv
from datetime import datetime, timezone
from functools import partial
import json
import multiprocessing as mp
from pathlib import Path
import queue
import shutil
import time

import glfw
import imageio.v2 as imageio
import mujoco as mj
import numpy as np

from p6_scene import ROOT, build, settings
from p6_single_door import run


class LiveFrames:
    """Send only solved robot poses and HUD measurements to the desktop renderer."""
    def __init__(self, control, model, data, handle, cfg, out, video):
        self.frames = 0
        self.data, self.case = data, cfg['case']
        self.packets, self.start, self.play, self.stop = control
        self.send('READY', '', '')
        while not self.start.wait(.1):
            if self.stop.is_set():
                raise KeyboardInterrupt

    def send(self, status, left, right):
        self.packets.put((self.case, self.data.qpos.copy(), status, left, right))

    def draw(self, left, right):
        self.frames += 1
        self.send('RUNNING', left, right)

    @property
    def paused(self):
        return not self.play.is_set()

    def handle_pause(self):
        begin = time.monotonic()
        while not self.play.wait(.1) and self.running():
            pass
        return time.monotonic()-begin

    def running(self):
        return not self.stop.is_set()

    def finish_video(self):
        pass

    def close(self, hold, result):
        self.send('DONE', '', result)


def worker(case, control, raw):
    out = raw/f'C{case:02}'
    out.mkdir(parents=True, exist_ok=False)
    run(settings('mobile',case),out,True,False,False,partial(LiveFrames,control))


def compact_case(out, compact):
    compact.mkdir()
    for name in ['config.json','summary.json']:
        shutil.copyfile(out/name, compact/name)
    with (out/'timeseries.csv').open() as src, (compact/'trace.csv').open('w') as dest:
        reader = csv.DictReader(src)
        fields = ['time_s','phase','door_deg','effective_deg','tilt_deg','planar_error_m','heading_error_deg',
                  'tracking_m','grip_error_m','actual_width_m','both','door_F_x','door_F_y','door_F_z',
                  'door_norm_sum_N','finger_N_1','finger_N_2','root_x','root_y','root_z']
        fields.extend(k for k in reader.fieldnames if k.startswith(('normal_N_', 'lat_slip_', 'long_slip_')))
        writer = csv.DictWriter(dest, fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        for i,row in enumerate(reader):
            if i%5 == 0:
                writer.writerow(row)
    with (out/'contacts.csv').open() as src:
        friction = {}
        for row in csv.DictReader(src):
            category = row['category']
            friction.setdefault(category,set()).add(float(row['friction_tangent1']))
    (compact/'contact_friction.json').write_text(json.dumps({k:sorted(v) for k,v in friction.items()}, indent=2)+'\n')


def display(cases, destination, raw):
    if not glfw.init():
        raise RuntimeError('GLFW failed on the Linux desktop')
    window = glfw.create_window(1500,900,'P6 / FREE_BASE / mj_step  |  live condition trials',None,None)
    if not window:
        raise RuntimeError('Cannot open condition viewer')
    glfw.make_context_current(window)
    glfw.swap_interval(0)
    m = build(settings('mobile',1))
    visual = mj.MjData(m)
    opt = mj.MjvOption()
    opt.geomgroup[3:5] = 0
    cam = mj.MjvCamera()
    cam.type = mj.mjtCamera.mjCAMERA_FIXED
    cam.fixedcamid = m.camera('p6_overview').id
    scene = mj.MjvScene(m,maxgeom=2000)
    ctx = mj.MjrContext(m, mj.mjtFontScale.mjFONTSCALE_100)
    context = mp.get_context('spawn')
    packets, start, play, stop = context.Queue(), context.Event(), context.Event(), context.Event()
    play.set()
    def keyboard(window, key, scancode, action, mods):
        if action == glfw.PRESS and key == glfw.KEY_SPACE:
            play.clear() if play.is_set() else play.set()
        if action == glfw.PRESS and key == glfw.KEY_ESCAPE:
            glfw.set_window_should_close(window, True)
    glfw.set_key_callback(window, keyboard)
    configs = {case:settings('mobile',case)['perturbation'] for case in cases}
    processes = {case:context.Process(target=worker,args=(case,(packets,start,play,stop),raw)) for case in cases}
    for process in processes.values():
        process.start()
    latest = {}
    first_ready = None
    columns = 2 if len(cases)<=4 else 3
    rows = (len(cases)+columns-1)//columns
    w,h = glfw.get_framebuffer_size(window)
    full = mj.MjrRect(0,0,w,h)
    pixels = np.empty((h,w,3),dtype=np.uint8)
    writer = imageio.get_writer(destination/'live_grid.mp4',fps=8,codec='libx264',quality=5,macro_block_size=2)
    last_frame = 0.
    try:
        while True:
            glfw.poll_events()
            if glfw.window_should_close(window):
                stop.set()
                play.set()
                start.set()
            while True:
                try:
                    case,q,status,left,right = packets.get_nowait()
                except queue.Empty:
                    break
                old = latest.get(case, (None,'','',''))
                # The last live overlay stays visible after that experiment ends.
                if status == 'DONE':
                    left, right = old[2]+'\nEnd', old[3]+'\n'+right
                latest[case] = q,status,left,right
            if all(c in latest for c in cases) and first_ready is None:
                first_ready = time.monotonic()
            if first_ready and time.monotonic()-first_ready>2:
                start.set()
            mj.mjr_rectangle(full,.04,.055,.07,1.)
            for index,case in enumerate(cases):
                rect = mj.MjrRect((index%columns)*w//columns,(rows-1-index//columns)*h//rows,w//columns,h//rows)
                heading = f'C{case:02}  |  '+(', '.join(f'{k}={v:+g}' for k,v in configs[case].items()) or 'nominal')
                if case in latest:
                    q,status,left,right = latest[case]
                    visual.qpos[:] = q
                    mj.mj_forward(m,visual)  # rendering mirror only; workers own the physical state
                    mj.mjv_updateScene(m,visual,opt,None,cam,mj.mjtCatBit.mjCAT_ALL,scene)
                    mj.mjr_render(rect,scene,ctx)
                    fields = right.splitlines()
                    if len(fields)>=6:
                        info = f'{fields[0]}    {fields[1]}\nDoor {fields[2]}   Base {fields[3]}\nWheel N: {fields[4]}    Finger N: {fields[5]}'
                    else:
                        info = status
                    if status == 'DONE':
                        info += '\n'+fields[-1]
                else:
                    info = 'Loading model'
                mj.mjr_overlay(mj.mjtFont.mjFONT_NORMAL,mj.mjtGridPos.mjGRID_TOPLEFT,rect,heading+'\n'+info,'',ctx)
            now = time.monotonic()
            if start.is_set() and now-last_frame>=.125:
                mj.mjr_readPixels(pixels,None,full,ctx)
                writer.append_data(pixels[::-1])
                last_frame=now
            glfw.swap_buffers(window)
            if all(not p.is_alive() for p in processes.values()):
                break
            if any(p.exitcode not in (0,None) for p in processes.values()):
                stop.set()
                start.set()
                play.set()
            time.sleep(.02)
    finally:
        stop.set()
        start.set()
        play.set()
        for process in processes.values():
            process.join()
        writer.close()
        ctx.free()
        glfw.destroy_window(window)
        glfw.terminate()
    for case in cases:
        compact_case(raw/f'C{case:02}',destination/f'C{case:02}')
    return all(json.loads((destination/f'C{case:02}/summary.json').read_text())['task_success'] for case in cases)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases', type=int, choices=range(1,21), nargs='+')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if len(set(args.cases))!=len(args.cases) or len(args.cases)>6:
        parser.error('Use one to six distinct conditions per live window')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out=args.output or ROOT/'results/p6'/f'conditions_{stamp}'
    out.mkdir(parents=True,exist_ok=False)
    raw=ROOT/'results/raw_large/p6'/out.name
    raw.mkdir(parents=True,exist_ok=False)
    raise SystemExit(0 if display(args.cases,out,raw) else 1)
