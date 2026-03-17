# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Sweep the BQ25758 output current limit from a minimum to maximum value,
# recording VOUT and IOUT ADC readings at each step.  No external load
# controller is required — intended for use with a passive load (e.g. lamp).
#
import sys
sys.path.insert(0, '.')
import argparse
import time
import csv
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from remote_repl import RemoteRepl, find_rp2350_port

parser = argparse.ArgumentParser(description='BQ25758 load sweep: VOUT and IOUT vs current limit')
parser.add_argument('--voltage', type=float, default=12.0,
                    help='Output voltage setpoint in volts (default: 12.0)')
parser.add_argument('--min-current', type=float, default=0.1,
                    help='Minimum current limit in amps (default: 0.1)')
parser.add_argument('--max-current', type=float, default=5.0,
                    help='Maximum current limit in amps (default: 5.0)')
parser.add_argument('--points', type=int, default=50,
                    help='Number of sweep points (default: 50, ignored if --step is set)')
parser.add_argument('--step', type=float, default=None,
                    help='Fixed step size in amps, e.g. 0.1 (overrides --points)')
parser.add_argument('--samples', type=int, default=5,
                    help='ADC samples to average at each point (default: 5)')
parser.add_argument('--settle', type=float, default=0.5,
                    help='Seconds to wait after setting current limit before sampling (default: 0.5)')
parser.add_argument('--board-port', default=None,
                    help='Board serial port (default: auto-detect)')
parser.add_argument('--output', default=None,
                    help='Output CSV filename (default: auto-generated in calibration_results/)')
parser.add_argument('--no-plot', action='store_true',
                    help='Skip plotting (just save CSV)')
args = parser.parse_args()

# Generate sweep points
if args.step is not None:
    currents = np.arange(args.min_current, args.max_current + args.step * 0.5, args.step)
else:
    currents = np.linspace(args.min_current, args.max_current, args.points)

# Output file
Path('calibration_results').mkdir(exist_ok=True)
if args.output:
    outfile = args.output
else:
    timestamp = int(time.time())
    outfile = f'calibration_results/load_sweep_{timestamp}.csv'

plotfile = outfile.replace('.csv', '.png')

port = args.board_port or find_rp2350_port() or '/dev/ttyACM0'
print(f'Connecting to board on {port}...')

fieldnames = [
    'set_current', 'vout_adc', 'vout_adc_std',
    'iout_adc', 'iout_adc_std', 'regulation_mode',
]

rows = []

with RemoteRepl(port) as repl:
    repl.setup_board()

    print(f'Setting output voltage={args.voltage}V')
    repl.exec(f'board.bq.set_output_voltage_limit({args.voltage})')
    repl.exec(f'board.bq.set_output_current_limit({args.max_current})')
    repl.exec('board.bq.set_enabled(True)')
    time.sleep(1.0)

    vout_check = repl.exec('print(board.bq.get_vout_adc())')
    print(f'VOUT at idle: {float(vout_check):.3f}V')

    print(f'\nSweeping current limit {args.min_current:.2f}A to {args.max_current:.2f}A '
          f'({len(currents)} points)')
    print(f'Saving to {outfile}\n')
    print(f'{"#":>4}  {"Ilimit(A)":>10}  {"VOUT(V)":>9}  {"IOUT(A)":>9}  {"Mode":>5}')

    with open(outfile, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, set_current in enumerate(currents, 1):
            repl.exec(f'board.bq.set_output_current_limit({set_current})')
            time.sleep(args.settle)

            vout_samples = []
            iout_samples = []
            modes = []

            for _ in range(args.samples):
                raw = repl.exec(
                    'print(board.bq.get_vout_adc(), board.bq.get_iout_adc(), '
                    'board.bq.output_regulation_mode())'
                )
                try:
                    parts = raw.split()
                    vout_samples.append(float(parts[0]))
                    iout_samples.append(float(parts[1]))
                    modes.append(parts[2])
                except (ValueError, IndexError, AttributeError):
                    print(f'  WARNING: bad board reading: {raw!r}')
                time.sleep(0.1)

            if not vout_samples:
                print(f'{i:>4}  {set_current:>10.4f}  -- skipped --')
                continue

            vout_mean = np.mean(vout_samples)
            vout_std  = np.std(vout_samples)
            iout_mean = np.mean(iout_samples)
            iout_std  = np.std(iout_samples)
            mode = max(set(modes), key=modes.count) if modes else ''

            print(f'{i:>4}  {set_current:>10.4f}  {vout_mean:>9.3f}  {iout_mean:>9.4f}  {mode:>5}')

            row = {
                'set_current': set_current,
                'vout_adc':    vout_mean,
                'vout_adc_std': vout_std,
                'iout_adc':    iout_mean,
                'iout_adc_std': iout_std,
                'regulation_mode': mode,
            }
            writer.writerow(row)
            rows.append(row)
            f.flush()

    # Restore max current limit
    repl.exec(f'board.bq.set_output_current_limit({args.max_current})')

print(f'\nSweep complete. {len(rows)} points saved to {outfile}')

# --- Plot ---
if args.no_plot or not rows:
    sys.exit(0)

df = pd.DataFrame(rows)
cc_mask = df['regulation_mode'] == 'CC'
cv_mask = df['regulation_mode'] == 'CV'

fig, axes = plt.subplots(2, 1, figsize=(10, 8))
fig.suptitle(f'Load sweep  —  Vset={args.voltage}V', fontsize=13)

# --- Top: VOUT vs current limit ---
ax = axes[0]
if cv_mask.any():
    ax.scatter(df.loc[cv_mask, 'set_current'], df.loc[cv_mask, 'vout_adc'],
               s=20, color='tab:green', label='CV', zorder=3)
if cc_mask.any():
    ax.scatter(df.loc[cc_mask, 'set_current'], df.loc[cc_mask, 'vout_adc'],
               s=20, color='tab:orange', label='CC', zorder=3)
ax.plot(df['set_current'], df['vout_adc'], color='tab:blue', linewidth=1, alpha=0.4)
ax.set_ylabel('VOUT ADC (V)')
ax.set_xlabel('Current limit (A)')
ax.set_title('Output voltage vs current limit')
ax.legend()
ax.grid(True, alpha=0.3)

# --- Bottom: IOUT vs current limit ---
ax = axes[1]
ax.plot(df['set_current'], df['set_current'],
        'k--', linewidth=0.8, label='Ideal (y=x)')
if cv_mask.any():
    ax.scatter(df.loc[cv_mask, 'set_current'], df.loc[cv_mask, 'iout_adc'],
               s=20, color='tab:green', label='CV', zorder=3)
if cc_mask.any():
    ax.scatter(df.loc[cc_mask, 'set_current'], df.loc[cc_mask, 'iout_adc'],
               s=20, color='tab:orange', label='CC', zorder=3)
ax.plot(df['set_current'], df['iout_adc'], color='tab:blue', linewidth=1, alpha=0.4)
ax.set_ylabel('IOUT ADC (A)')
ax.set_xlabel('Current limit (A)')
ax.set_title('IOUT ADC vs current limit')
ax.legend()
ax.grid(True, alpha=0.3)
ax.set_xlim(left=0)
ax.set_ylim(bottom=0)

plt.tight_layout()
plt.savefig(plotfile, dpi=150)
print(f'Plot saved to {plotfile}')
