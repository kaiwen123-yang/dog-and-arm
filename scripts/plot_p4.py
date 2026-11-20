#!/usr/bin/env python3
"""Plot recorded P4 physical-simulation data, without rerunning simulation."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('run', type=Path)
args = parser.parse_args()
rows = list(csv.DictReader((args.run/'timeseries.csv').open()))
summary = json.loads((args.run/'summary.json').read_text())
def values(key):
    return np.asarray([float(row[key]) for row in rows])
t = values('time_s')
fig, axes = plt.subplots(4, 1, figsize=(11, 10), sharex=True, layout='constrained')
action = summary['mode'].split('_')[-1].lower()
fig.suptitle(f'P4 fixed-base contact {action} — physical mj_step data', fontsize=15)
axes[0].plot(t, values('planned_angle_deg'), '--', color='#7f8c8d', label='Planned hand arc')
axes[0].plot(t, values('door_angle_deg'), color='#166caa', label='Passive door')
axes[0].set_ylabel('Door angle (deg)'); axes[0].legend(loc='upper left')
axes[1].plot(t, values('width_m')*1000, color='#20815e')
axes[1].set_ylabel('Finger opening (mm)')
axes[2].plot(t, values('contact_force_norm_sum_n'), color='#c46c1c', label='Robot–door contact norm sum')
axes[2].plot(t, np.abs(values('gripper_force_n')), color='#924ca5', label='Gripper actuator |force|')
axes[2].set_ylabel('Force (N)'); axes[2].legend(loc='upper right')
for i in range(1, 7):
    axes[3].plot(t, values(f'piper_joint{i}_torque_nm'), label=f'J{i}')
axes[3].set_ylabel('Arm torque (Nm)'); axes[3].set_xlabel('Simulation time (s)')
axes[3].legend(ncol=6, loc='upper right')
previous = None
for row in rows:
    phase = row['phase']
    if phase != previous:
        time = float(row['time_s'])
        for ax in axes:
            ax.axvline(time, color='#d5d8dc', linewidth=.6)
        axes[0].text(time+.1, 1.01, phase, transform=axes[0].get_xaxis_transform(), fontsize=8, rotation=35)
        previous = phase
for ax in axes:
    ax.grid(axis='y', color='#e5e7e9'); ax.spines[['top','right']].set_visible(False)
    ax.set_xlim(0, summary['simulation_time_s'])
axes[0].set_title(f"Final door angle {summary['door_final_angle_deg']:.3f}°; base fixed; no door actuator or handle weld", fontsize=10, pad=35)
fig.savefig(args.run/'contact_timeseries.png', dpi=160)
svg_path = args.run/'contact_timeseries.svg'
fig.savefig(svg_path)
svg_path.write_text('\n'.join(line.rstrip() for line in svg_path.read_text().splitlines())+'\n')
print(args.run/'contact_timeseries.png')
