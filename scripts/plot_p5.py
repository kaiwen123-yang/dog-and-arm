#!/usr/bin/env python3
"""Plot P5 motion, heading and wheel slip from a saved run."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    with (args.run/'timeseries.csv').open() as f:
        rows = list(csv.DictReader(f))

    def series(name):
        return np.array([float(row[name]) for row in rows])

    t = series('time_s')
    fig, axes = plt.subplots(4, 1, figsize=(10, 8), sharex=True, layout='constrained')
    fig.suptitle('M1 + Piper H on four wheels | free-base dynamics')
    axes[0].plot(t, series('x_m'), label='World X')
    axes[0].plot(t, series('y_m'), label='World Y')
    axes[0].set_ylabel('Position (m)')
    axes[1].plot(t, series('yaw_deg'), label='Measured yaw')
    if 'yaw_target_deg' in rows[0] and np.isfinite(series('yaw_target_deg')).any():
        axes[1].plot(t, series('yaw_target_deg'), '--', label='Turn target')
    else:
        axes[1].plot(t, np.rad2deg(np.cumsum(series('yaw_ref_rad_s')*np.diff(t,prepend=t[0]))),
                     '--', label='Integral of rate command')
    axes[1].set_ylabel('Heading (deg)')
    axes[2].plot(t, series('roll_deg'), label='Roll')
    axes[2].plot(t, series('pitch_deg'), label='Pitch')
    axes[2].set_ylabel('Body tilt (deg)')
    for leg in ('FAR', 'FBL', 'RAR', 'RBL'):
        axes[3].plot(t, series(f'slip_{leg}_m_s'), label=leg, linewidth=.8)
    axes[3].set_ylabel('Contact slip (m/s)')
    axes[3].set_xlabel('Simulation time (s)')
    for ax in axes:
        ax.grid(axis='y', alpha=.3)
        ax.legend(loc='upper left', ncol=4)
    for i, row in enumerate(rows):
        if i and row['phase'] == rows[i-1]['phase']:
            continue
        for ax in axes:
            ax.axvline(t[i], color='.8', lw=.6)
        axes[0].text(t[i],1.02,row['phase'],transform=axes[0].get_xaxis_transform(),fontsize=8,rotation=25)
    fig.savefig(args.run/'motion.png', dpi=145)
    plt.close(fig)


if __name__ == '__main__':
    main()
