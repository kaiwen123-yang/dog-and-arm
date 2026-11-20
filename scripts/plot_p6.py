#!/usr/bin/env python3
"""Plot aligned measured door, gripper, base and support time series for a P6 run."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(directory):
    with (directory/'timeseries.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    s = json.loads((directory/'summary.json').read_text())
    def col(name):
        return np.array([float(row[name]) for row in rows])
    t = col('time_s')
    fig, axes = plt.subplots(5, 1, sharex=True, figsize=(10, 9), layout='constrained')
    axes[0].plot(t,col('raw_deg'),color='.65',label='Task reference')
    axes[0].plot(t,col('effective_deg'),'--',label='Limited reference')
    axes[0].plot(t,col('door_deg'),label='Measured door')
    axes[0].set_ylabel('Door (deg)')
    axes[1].plot(t,1000*col('planar_error_m'),label='Base to current target')
    axes[1].plot(t,1000*col('tracking_m'),label='Grasp site to effective reference')
    grip = np.isin([r['phase'] for r in rows], ['open','hold'])
    axes[1].plot(t,np.where(grip,1000*col('grip_error_m'),np.nan),label='Grasp site to bar')
    axes[1].set_ylabel('Error (mm)')
    for wheel in ('FAR','FBL','RAR','RBL'):
        axes[2].plot(t,col('normal_N_'+wheel),label=wheel)
    axes[2].set_ylabel('Wheel loads (N)')
    axes[3].plot(t,col('finger_N_1'),label='Finger 1 normal')
    axes[3].plot(t,col('finger_N_2'),label='Finger 2 normal')
    axes[3].plot(t,np.linalg.norm([col('door_F_'+a) for a in 'xyz'],axis=0),label='Door force on robot, magnitude')
    axes[3].set_ylabel('Force (N)')
    for kind,pretty in [('long','Longitudinal'), ('lat','Lateral')]:
        velocities = np.stack([col(kind+'_slip_'+w) for w in ('FAR','FBL','RAR','RBL')])
        axes[4].plot(t,np.max(np.abs(np.nan_to_num(velocities)),axis=0)*1000,label=pretty)
    axes[4].set_ylabel('Max slip (mm/s)')
    axes[4].set_xlabel('Physics time (s)')
    for ax in axes:
        ax.legend(loc='upper right',fontsize=8,ncol=3)
        ax.grid(alpha=.18)
        for event in s['events'][:-1]:
            ax.axvline(event['time_s'], lw=.6, color='.72')
    fig.suptitle(f"P6  {s['stage']}  C{s['case']:02}   |   Final door {s['final_deg']:.2f}°")
    fig.savefig(directory/'signals.png',dpi=140)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    plot(parser.parse_args().directory)
