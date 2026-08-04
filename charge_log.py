# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Poll the RP2350 board during a charge cycle and log vout, iout, vin, iin,
# regulation mode, and charger state to a timestamped CSV.  A plot is saved
# at the end (or on Ctrl+C).
#
# The charger must already be running on the board before this script starts.
# This script is read-only — it never writes to any board registers.
#
import sys
sys.path.insert(0, '.')
import argparse
import time
import csv
import signal
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from remote_repl import RemoteRepl, find_rp2350_port

parser = argparse.ArgumentParser(description='Log a charge cycle from the board')
parser.add_argument('--interval', type=float, default=5.0,
                    help='Poll interval in seconds (default: 5)')
parser.add_argument('--board-port', default=None,
                    help='Board serial port (default: auto-detect)')
parser.add_argument('--output', default=None,
                    help='Output CSV filename (default: auto-generated)')
parser.add_argument('--no-plot', action='store_true',
                    help='Skip plot on exit')
args = parser.parse_args()

Path('charge_logs').mkdir(exist_ok=True)
if args.output:
    outfile = args.output
else:
    outfile = 'charge_logs/charge_{}.csv'.format(int(time.time()))
plotfile = outfile.replace('.csv', '.png')

fieldnames = ['elapsed_s', 'timestamp',
              'vout', 'iout', 'vin', 'iin',
              'regulation_mode', 'charger_state']

_READ_CMD = (
    'board.context.clear(); '
    'print('
    'board.context.get("vout"), '
    'board.context.get("iout"), '
    'board.context.get("vin"), '
    'board.context.get("iin"), '
    'board.context.get("regulation_mode"), '
    'board.context.get("charger_state")'
    ')'
)

rows = []
start_time = None
stop = False

def _handle_sigint(sig, frame):
    global stop
    print('\nInterrupted — saving data...')
    stop = True

signal.signal(signal.SIGINT, _handle_sigint)

port = args.board_port or find_rp2350_port() or '/dev/ttyACM0'
print('Connecting to board on {}...'.format(port))

with RemoteRepl(port) as repl, open(outfile, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()

    print('Logging to {}'.format(outfile))
    print('{:>10}  {:>8}  {:>8}  {:>8}  {:>8}  {:>6}  {:>8}'.format(
        'Elapsed(s)', 'Vout(V)', 'Iout(A)', 'Vin(V)', 'Iin(A)', 'Mode', 'Stage'))
    print('-' * 72)

    start_time = time.time()

    while not stop:
        raw = repl.exec(_READ_CMD)
        ts = time.time()
        elapsed = ts - start_time

        # Take the last non-empty line — charger state transitions may print
        # diagnostic messages that get prepended to the REPL response.
        # Also strip a leading OK that RemoteRepl misses when output precedes it.
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        raw = lines[-1] if lines else ''
        if raw.startswith('OK'):
            raw = raw[2:]
        try:
            parts = raw.split()
            vout  = float(parts[0])
            iout  = float(parts[1])
            vin   = float(parts[2])
            iin   = float(parts[3])
            mode  = parts[4]
            stage = parts[5] if len(parts) > 5 else ''
        except (ValueError, IndexError):
            print('WARNING: bad reading: {!r}'.format(raw))
            time.sleep(args.interval)
            continue

        print('{:>10.1f}  {:>8.3f}  {:>8.3f}  {:>8.3f}  {:>8.3f}  {:>6}  {:>8}'.format(
            elapsed, vout, iout, vin, iin, mode, stage))

        row = {
            'elapsed_s':       elapsed,
            'timestamp':       ts,
            'vout':            vout,
            'iout':            iout,
            'vin':             vin,
            'iin':             iin,
            'regulation_mode': mode,
            'charger_state':   stage,
        }
        writer.writerow(row)
        rows.append(row)
        f.flush()

        if stage == 'Done':
            print('Charger reports Done — stopping log.')
            break

        time.sleep(args.interval)

print('\n{} points saved to {}'.format(len(rows), outfile))

if args.no_plot or len(rows) < 2:
    sys.exit(0)

# --- Plot ------------------------------------------------------------------
df = pd.DataFrame(rows)
t  = df['elapsed_s'] / 60.0  # minutes

fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
fig.suptitle('Charge cycle log', fontsize=13)

# Shade regions by charger stage
stage_colors = {'Pre': '#ffe0b2', 'Fast': '#e3f2fd', 'Taper': '#e8f5e9', 'Done': '#f3e5f5'}
for stage, color in stage_colors.items():
    mask = df['charger_state'] == stage
    if not mask.any():
        continue
    # Find contiguous spans
    in_span = False
    for i, (idx, val) in enumerate(mask.items()):
        if val and not in_span:
            x0 = t.iloc[i]
            in_span = True
        elif not val and in_span:
            for ax in axes:
                ax.axvspan(x0, t.iloc[i], color=color, alpha=0.4, label=stage)
            in_span = False
    if in_span:
        for ax in axes:
            ax.axvspan(x0, t.iloc[-1], color=color, alpha=0.4, label=stage)

# Top: voltages
axes[0].plot(t, df['vout'], label='Vout', color='tab:blue')
axes[0].plot(t, df['vin'],  label='Vin',  color='tab:orange', linestyle='--', alpha=0.7)
axes[0].set_ylabel('Voltage (V)')
axes[0].legend(loc='lower right')
axes[0].grid(True, alpha=0.3)

# Bottom: currents
axes[1].plot(t, df['iout'], label='Iout', color='tab:green')
axes[1].plot(t, df['iin'],  label='Iin',  color='tab:red', linestyle='--', alpha=0.7)
axes[1].set_ylabel('Current (A)')
axes[1].set_xlabel('Elapsed time (min)')
axes[1].legend(loc='upper right')
axes[1].grid(True, alpha=0.3)

# Deduplicate legend entries from axvspan
for ax in axes:
    handles, labels = ax.get_legend_handles_labels()
    seen = {}
    for h, l in zip(handles, labels):
        if l not in seen:
            seen[l] = h
    ax.legend(seen.values(), seen.keys(), loc='lower right' if ax is axes[0] else 'upper right')

plt.tight_layout()
plt.savefig(plotfile, dpi=150)
print('Plot saved to {}'.format(plotfile))
