#!/usr/bin/env python3
# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Battery capacity measurement and OCV characterisation using the IT8511 DC load.
#
# The IT8511 should be connected directly to the battery with Kelvin sense leads
# for accurate voltage and current readings independent of the board.  Start with
# a fully-charged battery (charger in STATE_DONE) for accurate capacity figures.
#
# Test procedure
# --------------
#   1. Discharge at a configurable C-rate (default 1C) in CC mode.
#   2. Every --rest-interval-pct % of nominal capacity discharged, pause the load for
#      --rest-time seconds and record the OCV recovery curve.
#   3. Stop when battery voltage drops below --cutoff-voltage.
#   4. Calculate actual capacity from total Ah discharged.
#   5. Output a measured OCV-SOC table, discharge plot, and Python snippet to
#      update _LIFEPO4_2S_OCV (or equivalent) in charger.py.
#
# Outputs (written to --output-dir, default: capacity_results/)
# -------------------------------------------------------------
#   capacity_test_<ts>.csv        discharge log (elapsed, voltage, current, Ah, SOC)
#   capacity_test_<ts>_ocv.csv    OCV recovery samples (target_soc, rest_elapsed, voltage)
#   capacity_test_<ts>.png        discharge + OCV plot
#   capacity_test_<ts>_results.txt summary and Python OCV table snippet
#
# Usage example
# -------------
#   python battery_capacity_test.py \
#       --capacity-ah 5.0 --c-rate 0.5 \
#       --cutoff-voltage 5.2 --rest-interval-pct 10 --rest-time 300
#
import sys
sys.path.insert(0, '.')
import argparse
import csv
import signal
import time
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from itech_serial import IT8500
from remote_repl import RemoteRepl, find_rp2350_port

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description='Battery capacity and OCV characterisation test',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument('--capacity-ah', type=float, default=5.0,
                    help='Nominal battery capacity (Ah) — used for SOC%% during test')
parser.add_argument('--c-rate', type=float, default=1.0,
                    help='Discharge rate as a fraction of capacity (1.0 = 1C)')
parser.add_argument('--cutoff-voltage', type=float, default=5.2,
                    help='Stop discharge when battery voltage drops below this (V)')
parser.add_argument('--rest-interval-pct', type=float, default=5.0,
                    help='Pause for OCV measurement every this many %% of capacity discharged')
parser.add_argument('--rest-time', type=float, default=60.0,
                    help='Seconds to rest the battery at each OCV measurement point')
parser.add_argument('--rest-sample-interval', type=float, default=0.1,
                    help='Seconds between voltage samples during rest period')
parser.add_argument('--poll-interval', type=float, default=10.0,
                    help='Seconds between load measurements during discharge')
parser.add_argument('--load-port', default='/dev/it8511',
                    help='Serial port for IT8511 DC load')
parser.add_argument('--board-port', default=None,
                    help='Board serial port (auto-detect if not specified)')
parser.add_argument('--no-board', action='store_true',
                    help='Skip board connection (manually ensure charger is disabled)')
parser.add_argument('--output-dir', default='capacity_results',
                    help='Directory for output files')
args = parser.parse_args()

discharge_current_a = args.capacity_ah * args.c_rate
rest_interval_ah    = args.capacity_ah * args.rest_interval_pct / 100.0

print('Battery capacity test')
print(f'  Nominal capacity : {args.capacity_ah:.2f} Ah')
print(f'  Discharge rate   : {args.c_rate:.2f}C = {discharge_current_a:.2f} A')
print(f'  Cutoff voltage   : {args.cutoff_voltage:.2f} V')
print(f'  Rest interval    : every {args.rest_interval_pct:.0f}% = {rest_interval_ah:.3f} Ah')
print(f'  Rest time        : {args.rest_time:.0f} s per point')
print()

# ---------------------------------------------------------------------------
# Output files
# ---------------------------------------------------------------------------
Path(args.output_dir).mkdir(parents=True, exist_ok=True)
ts = int(time.time())
base        = f'{args.output_dir}/capacity_test_{ts}'
csv_file    = f'{base}.csv'
ocv_file    = f'{base}_ocv.csv'
plot_file   = f'{base}.png'
result_file = f'{base}_results.txt'

discharge_fieldnames = ['elapsed_s', 'timestamp', 'voltage', 'current', 'power',
                        'discharged_ah', 'soc_pct', 'phase']
ocv_fieldnames       = ['target_soc_pct', 'discharged_ah_at_rest',
                        'rest_elapsed_s', 'voltage']

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------
print(f'Connecting to IT8511 on {args.load_port}...')
load = IT8500(args.load_port, baudrate=4800)
info = load.identify()
print(f'  {info}')
load.control_set_remote()
load.disable()
load.mode_set('cc')
load.constant_current_set(discharge_current_a)
load.max_voltage_set(max(args.cutoff_voltage * 1.5, 20.0))
print(f'  Configured: CC {discharge_current_a:.2f} A, cutoff {args.cutoff_voltage:.2f} V')

repl = None
if not args.no_board:
    port = args.board_port or find_rp2350_port() or '/dev/ttyACM0'
    print(f'Connecting to board on {port}...')
    try:
        repl = RemoteRepl(port)
        repl.connect()
        repl.exec('import board; board.setup()')
        repl.exec('board.set_charger(None)')
        repl.exec('board.context.set("forward_enable", 0)')
        print('  Charger disabled for test duration')
    except Exception as e:
        print(f'  WARNING: Board connection failed ({e}) — continuing without board')
        try:
            repl.close()
        except Exception:
            pass
        repl = None

# ---------------------------------------------------------------------------
# Graceful interrupt
# ---------------------------------------------------------------------------
_stop = False

def _handle_sigint(sig, frame):
    global _stop
    print('\nInterrupted — stopping after this sample...')
    _stop = True

signal.signal(signal.SIGINT, _handle_sigint)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_load():
    '''Read IT8511 and return (voltage, current, power) or None on error.'''
    try:
        m = load.measure()
        return m['voltage'], m['current'], m['power']
    except Exception as e:
        print(f'  WARNING: load read error: {e}')
        return None


def _fit_ocv_recovery(t_samples, v_samples):
    '''Fit V(t) = OCV - A*exp(-t/tau) to recovery samples.

    Returns (ocv_fitted, A, tau) or None if fit fails.
    The model asymptote (t→∞) gives the true settled OCV.
    '''
    t = np.array(t_samples, dtype=float)
    v = np.array(v_samples, dtype=float)
    if len(t) < 4:
        return None
    # Initial guesses: OCV ≈ last sample, A ≈ first drop, tau ≈ quarter of range
    v0 = v[0]
    v_last = v[-1]
    ocv0  = v_last + (v_last - v0) * 0.05  # slightly above last point
    a0    = max(v_last - v0, 0.001)
    tau0  = t[-1] / 3.0
    try:
        def model(t_, ocv, a, tau):
            return ocv - a * np.exp(-t_ / tau)
        popt, _ = curve_fit(
            model, t, v,
            p0=[ocv0, a0, tau0],
            bounds=([v_last - 0.5, 0, 0.1], [v_last + 2.0, 2.0, 3600.0]),
            maxfev=5000,
        )
        return tuple(popt)  # (ocv, A, tau)
    except Exception:
        return None


def _do_rest(target_soc_pct, discharged_ah, ocv_writer):
    '''Stop load, record OCV recovery, restart load.

    Fits an exponential to the recovery curve to extrapolate the true settled
    OCV.  Returns fitted OCV if the fit succeeds, otherwise last measured value.
    '''
    print(f'\n  --- OCV rest at ~{target_soc_pct:.0f}% SOC  '
          f'({discharged_ah:.3f} Ah discharged) ---')
    load.disable()
    time.sleep(0.5)  # brief transient settle before first sample

    rest_start  = time.time()
    next_sample = rest_start
    t_samples   = []
    v_samples   = []

    while time.time() - rest_start < args.rest_time and not _stop:
        now = time.time()
        if now >= next_sample:
            m = _read_load()
            if m:
                v, _, _ = m
                rest_elapsed = now - rest_start
                t_samples.append(rest_elapsed)
                v_samples.append(v)
                ocv_writer.writerow({
                    'target_soc_pct':        target_soc_pct,
                    'discharged_ah_at_rest': discharged_ah,
                    'rest_elapsed_s':        round(rest_elapsed, 2),
                    'voltage':               v,
                })
                print(f'    t+{rest_elapsed:5.1f}s  {v:.4f} V')
            next_sample += args.rest_sample_interval
        time.sleep(min(0.2, args.rest_sample_interval / 4))

    # Fit exponential to extrapolate settled OCV
    fit = _fit_ocv_recovery(t_samples, v_samples)
    last_v = v_samples[-1] if v_samples else None

    if fit is not None:
        ocv_fit, a_fit, tau_fit = fit
        print(f'  Fit:  OCV={ocv_fit:.4f} V  A={a_fit:.4f} V  τ={tau_fit:.1f} s')
        if last_v is not None:
            print(f'  Last measured: {last_v:.4f} V  '
                  f'(fit adds {(ocv_fit - last_v)*1000:.1f} mV)')
        settled_ocv = ocv_fit
    else:
        print(f'  Fit failed — using last measured value')
        settled_ocv = last_v
        if settled_ocv is not None:
            print(f'  Last measured OCV: {settled_ocv:.4f} V')

    if not _stop:
        load.enable()
        time.sleep(0.5)

    return settled_ocv, t_samples, v_samples, fit

# ---------------------------------------------------------------------------
# Main discharge loop
# ---------------------------------------------------------------------------
print(f'\nStarting discharge...')
print(f'Saving to {csv_file}')
print()
print(f'{"Elapsed":>10}  {"Vbat(V)":>9}  {"I(A)":>7}  {"Ah":>8}  {"SOC%":>6}')
print('-' * 52)

discharge_rows = []

# List of (discharged_ah_at_rest, settled_ocv, t_samples, v_samples, fit)
# After the test, SOC is rescaled using actual_capacity_ah.
rest_ocv_data  = []

discharged_ah         = 0.0
next_rest_ah          = rest_interval_ah
next_rest_target_pct  = 100.0 - args.rest_interval_pct  # first rest at ~90% if 10% interval
phase                 = 'discharge'

with open(csv_file, 'w', newline='') as df_out, \
     open(ocv_file, 'w', newline='') as ocv_out:

    d_writer   = csv.DictWriter(df_out,  fieldnames=discharge_fieldnames)
    ocv_writer = csv.DictWriter(ocv_out, fieldnames=ocv_fieldnames)
    d_writer.writeheader()
    ocv_writer.writeheader()

    load.enable()
    start_t = time.time()
    last_t  = start_t

    while not _stop:
        time.sleep(args.poll_interval)
        now = time.time()
        m = _read_load()
        if m is None:
            continue

        voltage, current, power = m
        dt             = now - last_t
        last_t         = now
        discharged_ah += abs(current) * dt / 3600.0
        elapsed        = now - start_t
        soc_pct        = max(0.0, 100.0 - discharged_ah / args.capacity_ah * 100.0)

        print(f'{elapsed:>10.1f}  {voltage:>9.4f}  {current:>7.3f}  '
              f'{discharged_ah:>8.4f}  {soc_pct:>6.1f}')

        row = {
            'elapsed_s':     round(elapsed, 2),
            'timestamp':     round(now, 2),
            'voltage':       voltage,
            'current':       current,
            'power':         power,
            'discharged_ah': round(discharged_ah, 5),
            'soc_pct':       round(soc_pct, 2),
            'phase':         phase,
        }
        d_writer.writerow(row)
        discharge_rows.append(row)
        df_out.flush()

        # Check cutoff
        if voltage <= args.cutoff_voltage:
            print(f'\nCutoff {args.cutoff_voltage:.2f} V reached — stopping.')
            break

        # Check rest interval
        if discharged_ah >= next_rest_ah:
            phase = 'rest'
            settled, t_samp, v_samp, fit = _do_rest(
                next_rest_target_pct, discharged_ah, ocv_writer)
            ocv_out.flush()
            if settled is not None:
                rest_ocv_data.append((discharged_ah, settled, t_samp, v_samp, fit))
            next_rest_ah         += rest_interval_ah
            next_rest_target_pct -= args.rest_interval_pct
            phase  = 'discharge'
            last_t = time.time()  # reset dt so rest time is not counted as Ah

load.disable()
load.control_set_local()

if repl:
    try:
        repl.close()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Post-test analysis
# ---------------------------------------------------------------------------
actual_capacity_ah = discharged_ah
total_elapsed_min  = (discharge_rows[-1]['elapsed_s'] / 60.0) if discharge_rows else 0.0
final_voltage      = discharge_rows[-1]['voltage']             if discharge_rows else 0.0

print(f'\n{"=" * 52}')
print(f'Test complete')
print(f'  Actual capacity : {actual_capacity_ah:.3f} Ah  '
      f'({actual_capacity_ah / args.capacity_ah * 100:.1f}% of nominal)')
print(f'  Total time      : {total_elapsed_min:.1f} min')
print(f'  Final voltage   : {final_voltage:.4f} V')
print(f'  OCV points      : {len(rest_ocv_data)}')

# Rescale SOC using actual capacity
ocv_points_rescaled = []
for dah, v, *_ in rest_ocv_data:
    actual_soc = max(0.0, 100.0 - dah / actual_capacity_ah * 100.0) if actual_capacity_ah > 0 else 0.0
    ocv_points_rescaled.append((round(actual_soc, 1), v))

# Sort ascending by SOC for the table
ocv_points_rescaled.sort(key=lambda x: x[0])

print(f'\nSettled OCV-SOC points (rescaled to actual {actual_capacity_ah:.3f} Ah):')
print(f'  {"SOC%":>6}  {"OCV (V)":>9}')
for soc, v in reversed(ocv_points_rescaled):
    print(f'  {soc:>6.1f}  {v:>9.4f}')

# ---------------------------------------------------------------------------
# Python snippet for charger.py
# ---------------------------------------------------------------------------
snippet_lines = [
    f'# Measured OCV table for this pack',
    f'# Actual capacity: {actual_capacity_ah:.3f} Ah '
    f'({actual_capacity_ah/args.capacity_ah*100:.1f}% of {args.capacity_ah:.2f} Ah nominal)',
    f'# {args.rest_time:.0f}s rest per point — generated by battery_capacity_test.py ts={ts}',
    f'# NOTE: Add 0% and 100% endpoints manually from v_cutoff and v_reg.',
    f'_LIFEPO4_2S_OCV = (',
    f'    # ({final_voltage:.4f},   0.0),  # cutoff voltage — add if desired',
]
for soc, v in ocv_points_rescaled:
    snippet_lines.append(f'    ({v:.4f}, {soc:5.1f}),')
snippet_lines += [
    f'    # (7.3000, 100.0),  # v_reg — add if desired',
    f')',
]
snippet = '\n'.join(snippet_lines)
print(f'\n{snippet}')

# ---------------------------------------------------------------------------
# Save results file
# ---------------------------------------------------------------------------
with open(result_file, 'w') as f:
    f.write('Battery capacity test results\n')
    f.write(f'Timestamp        : {ts}\n')
    f.write(f'Nominal capacity : {args.capacity_ah:.3f} Ah\n')
    f.write(f'Actual capacity  : {actual_capacity_ah:.3f} Ah '
            f'({actual_capacity_ah / args.capacity_ah * 100:.1f}%)\n')
    f.write(f'Discharge rate   : {args.c_rate:.2f}C = {discharge_current_a:.2f} A\n')
    f.write(f'Cutoff voltage   : {args.cutoff_voltage:.2f} V\n')
    f.write(f'Rest time        : {args.rest_time:.0f} s per point\n')
    f.write(f'Total time       : {total_elapsed_min:.1f} min\n')
    f.write(f'Final voltage    : {final_voltage:.4f} V\n')
    f.write(f'\nOCV-SOC points (SOC%, OCV_V):\n')
    for soc, v in reversed(ocv_points_rescaled):
        f.write(f'  {soc:6.1f}%  {v:.4f} V\n')
    f.write(f'\n{snippet}\n')

print(f'\nResults : {result_file}')

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
if len(discharge_rows) < 2:
    sys.exit(0)

df    = pd.DataFrame(discharge_rows)
t_min = df['elapsed_s'] / 60.0

fig = plt.figure(figsize=(14, 12))
fig.suptitle(
    f'Battery capacity test  —  {actual_capacity_ah:.3f} Ah actual  '
    f'({actual_capacity_ah/args.capacity_ah*100:.1f}% of {args.capacity_ah:.2f} Ah nominal)',
    fontsize=12,
)
gs     = fig.add_gridspec(3, 2, hspace=0.38, wspace=0.3)
ax_v   = fig.add_subplot(gs[0, 0])
ax_i   = fig.add_subplot(gs[1, 0], sharex=ax_v)
ax_soc = fig.add_subplot(gs[2, 0], sharex=ax_v)
ax_ocv = fig.add_subplot(gs[:, 1])

# Shade rest periods on left panels
rest_mask = df['phase'] == 'rest'
in_rest   = False
for i in range(len(rest_mask)):
    val = rest_mask.iloc[i]
    if val and not in_rest:
        x0      = t_min.iloc[i]
        in_rest = True
    elif not val and in_rest:
        for ax in (ax_v, ax_i, ax_soc):
            ax.axvspan(x0, t_min.iloc[i], color='#e8f5e9', alpha=0.7)
        in_rest = False
if in_rest:
    for ax in (ax_v, ax_i, ax_soc):
        ax.axvspan(x0, t_min.iloc[-1], color='#e8f5e9', alpha=0.7)

# Voltage panel
ax_v.plot(t_min, df['voltage'], color='tab:blue', linewidth=1.2, label='Vbat')
ax_v.axhline(args.cutoff_voltage, color='tab:red', linestyle='--',
             linewidth=0.8, label=f'Cutoff {args.cutoff_voltage:.2f} V')
for dah, v, *_ in rest_ocv_data:
    idx = (df['discharged_ah'] - dah).abs().idxmin()
    ax_v.scatter(t_min[idx], v, color='tab:orange', zorder=5, s=50, marker='D')
if rest_ocv_data:
    ax_v.scatter([], [], color='tab:orange', s=50, marker='D', label='Fitted OCV')
ax_v.set_ylabel('Voltage (V)')
ax_v.legend(loc='upper right', fontsize=8)
ax_v.grid(True, alpha=0.3)

# Current panel
ax_i.plot(t_min, df['current'], color='tab:green', linewidth=1.2)
ax_i.set_ylabel('Current (A)')
ax_i.grid(True, alpha=0.3)

# SOC panel
ax_soc.plot(t_min, df['soc_pct'], color='tab:purple', linewidth=1.2)
ax_soc.set_ylabel('SOC % (nominal)')
ax_soc.set_xlabel('Elapsed time (min)')
ax_soc.set_ylim(-2, 107)
ax_soc.grid(True, alpha=0.3)

# OCV recovery panel — one curve per rest period
colors = plt.cm.viridis(np.linspace(0.15, 0.85, max(len(rest_ocv_data), 1)))
for i, (dah, v_settled, t_samp, v_samp, fit) in enumerate(rest_ocv_data):
    if not t_samp:
        continue
    soc_label = ocv_points_rescaled[i][0] if i < len(ocv_points_rescaled) else '?'
    col = colors[i]
    ax_ocv.scatter(t_samp, v_samp, color=col, s=12, zorder=3,
                   label=f'{soc_label:.0f}% SOC')
    if fit is not None:
        ocv_f, a_f, tau_f = fit
        t_fit = np.linspace(0, max(t_samp) * 1.5, 300)
        v_fit = ocv_f - a_f * np.exp(-t_fit / tau_f)
        ax_ocv.plot(t_fit, v_fit, color=col, linewidth=1.2, linestyle='--', alpha=0.8)
        ax_ocv.axhline(ocv_f, color=col, linewidth=0.6, linestyle=':')

ax_ocv.set_xlabel('Time since load removed (s)')
ax_ocv.set_ylabel('Voltage (V)')
ax_ocv.set_title('OCV recovery curves\n(scatter=measured, dashed=fit, dotted=fitted OCV)')
ax_ocv.legend(loc='lower right', fontsize=8)
ax_ocv.grid(True, alpha=0.3)

plt.savefig(plot_file, dpi=150, bbox_inches='tight')
print(f'Plot     : {plot_file}')
