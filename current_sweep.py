# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Sweep the IT8511 DC load from a minimum to maximum current while the
# BQ25758 is in bypass mode, recording IIN and IOUT ADC readings against
# the IT8511 reference current.  Results are saved to a CSV for offline
# analysis and curve fitting.
#
import sys
sys.path.insert(0, '.')
import argparse
import time
import csv
from pathlib import Path
import numpy as np
import pandas as pd
from itech_serial import IT8500
from remote_repl import RemoteRepl, find_rp2350_port

parser = argparse.ArgumentParser(description='BQ25758 current ADC sweep (bypass mode)')
parser.add_argument('--min-current', type=float, default=0.01,
                    help='Minimum load current in amps (default: 0.01)')
parser.add_argument('--max-current', type=float, default=10.0,
                    help='Maximum load current in amps (default: 10.0)')
parser.add_argument('--max-power', type=float, default=150.0,
                    help='IT8511 power limit in watts (default: 150.0)')
parser.add_argument('--points', type=int, default=50,
                    help='Number of sweep points (default: 50, ignored if --step is set)')
parser.add_argument('--step', type=float, default=None,
                    help='Fixed step size in amps, e.g. 0.1 for 100mA steps (overrides --points)')
parser.add_argument('--samples', type=int, default=5,
                    help='ADC samples to average at each point (default: 5)')
parser.add_argument('--settle', type=float, default=0.5,
                    help='Seconds to wait after setting current before sampling (default: 0.5)')
parser.add_argument('--log-spaced', action='store_true',
                    help='Use logarithmic spacing (better coverage at low currents)')
parser.add_argument('--load-port', default='/dev/it8511',
                    help='IT8511 serial port (default: /dev/it8511)')
parser.add_argument('--board-port', default=None,
                    help='Board serial port (default: auto-detect)')
parser.add_argument('--output', default=None,
                    help='Output CSV filename (default: auto-generated in calibration_results/)')
args = parser.parse_args()

# Generate sweep points
if args.step is not None:
    currents = np.arange(args.min_current, args.max_current + args.step * 0.5, args.step)
elif args.log_spaced:
    currents = np.logspace(
        np.log10(args.min_current),
        np.log10(args.max_current),
        args.points
    )
else:
    currents = np.linspace(args.min_current, args.max_current, args.points)

# Output file
Path('calibration_results').mkdir(exist_ok=True)
if args.output:
    outfile = args.output
else:
    timestamp = int(time.time())
    outfile = f'calibration_results/current_sweep_{timestamp}.csv'

print(f'Connecting to IT8511 on {args.load_port}...')
load = IT8500(args.load_port)
load.control_set_remote()
load.mode_set('CC')
load.max_current_set(args.max_current)
load.max_power_set(args.max_power)
load.max_voltage_set(60.0)
print(f'IT8511 limits: {args.max_current}A / {args.max_power}W')

port = args.board_port or find_rp2350_port() or '/dev/ttyACM0'
print(f'Connecting to board on {port}...')

fieldnames = ['set_current', 'it8511_current', 'it8511_current_std',
              'iin_adc', 'iin_adc_std', 'iout_adc', 'iout_adc_std',
              'iin_error_ma', 'iout_error_ma']

with RemoteRepl(port) as repl:
    repl.setup_board()

    print('Enabling bypass mode...')
    repl.exec('board.bq.set_bypass_enable(True)')
    time.sleep(0.5)
    bypass_on = repl.exec('print(board.bq.get_bypass_enable())')
    if bypass_on.strip() != 'True':
        print(f'ERROR: bypass did not enable (got {bypass_on!r})')
        sys.exit(1)
    print('Bypass mode active.')

    load.constant_current_set(currents[0])
    load.enable()
    time.sleep(1.0)

    print(f'\nSweeping {args.min_current*1000:.0f}mA to {args.max_current*1000:.0f}mA '
          f'({args.points} points, {"log" if args.log_spaced else "linear"} spacing)')
    print(f'Saving to {outfile}\n')
    print(f'{"#":>4}  {"Set(A)":>8}  {"IT8511(A)":>10}  {"IIN_ADC(A)":>11}  '
          f'{"IOUT_ADC(A)":>12}  {"IIN_err(mA)":>12}  {"IOUT_err(mA)":>12}')

    try:
        with open(outfile, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for i, set_current in enumerate(currents, 1):
                load.constant_current_set(set_current)
                time.sleep(args.settle)

                it8511_samples = []
                iin_samples = []
                iout_samples = []

                for _ in range(args.samples):
                    m = load.measure()
                    it8511_samples.append(m['current'])

                    raw = repl.exec(
                        'print(board.bq.get_iin_adc(), board.bq.get_iout_adc())'
                    )
                    try:
                        iin_v, iout_v = raw.split()
                        iin_samples.append(float(iin_v))
                        iout_samples.append(float(iout_v))
                    except (ValueError, AttributeError):
                        print(f'  WARNING: bad board reading: {raw!r}')
                    time.sleep(0.1)

                if not it8511_samples or not iin_samples:
                    print(f'{i:>4}  {set_current:>8.4f}  -- skipped --')
                    continue

                it8511_mean = np.mean(it8511_samples)
                it8511_std  = np.std(it8511_samples)
                iin_mean    = np.mean(iin_samples)
                iin_std     = np.std(iin_samples)
                iout_mean   = np.mean(iout_samples)
                iout_std    = np.std(iout_samples)
                iin_err_ma  = (iin_mean  - it8511_mean) * 1000
                iout_err_ma = (iout_mean - it8511_mean) * 1000

                print(f'{i:>4}  {set_current:>8.4f}  {it8511_mean:>10.4f}  '
                      f'{iin_mean:>11.4f}  {iout_mean:>12.4f}  '
                      f'{iin_err_ma:>+12.1f}  {iout_err_ma:>+12.1f}')

                writer.writerow({
                    'set_current':        set_current,
                    'it8511_current':     it8511_mean,
                    'it8511_current_std': it8511_std,
                    'iin_adc':            iin_mean,
                    'iin_adc_std':        iin_std,
                    'iout_adc':           iout_mean,
                    'iout_adc_std':       iout_std,
                    'iin_error_ma':       iin_err_ma,
                    'iout_error_ma':      iout_err_ma,
                })
                f.flush()

    finally:
        load.disable()
        load.control_set_local()
        repl.exec('board.bq.set_bypass_enable(False)')
        print(f'\nLoad disabled, bypass off.')

print(f'\nSweep complete. Results saved to {outfile}')

# --- Fit and upload calibration ---
df = pd.read_csv(outfile)
df = df[df['it8511_current'] > 0.0].copy()
ref  = df['it8511_current'].values
iin  = df['iin_adc'].values
iout = df['iout_adc'].values

def fit_linear(ref, adc):
    coeffs = np.polyfit(ref, adc, 1)
    gain, offset = float(coeffs[0]), float(coeffs[1])
    corrected = (adc - offset) / gain
    rms = float(np.sqrt(np.mean(((corrected - ref) * 1000) ** 2)))
    return gain, offset, rms

iin_gain,  iin_offset,  iin_rms  = fit_linear(ref, iin)
iout_gain, iout_offset, iout_rms = fit_linear(ref, iout)

print(f'\nCalibration fit results:')
print(f'  IIN:  gain={iin_gain:.6f}  offset={iin_offset*1000:+.2f}mA  rms={iin_rms:.1f}mA')
print(f'  IOUT: gain={iout_gain:.6f}  offset={iout_offset*1000:+.2f}mA  rms={iout_rms:.1f}mA')

print(f'\nUploading calibration to board...')
port = args.board_port or find_rp2350_port() or '/dev/ttyACM0'
with RemoteRepl(port) as repl:
    repl.setup_board()
    repl.exec('import calibration as _cal')
    repl.exec('_c = _cal.Calibration()')
    repl.exec(f'_c.set_iin_calibration(gain={iin_gain}, offset={iin_offset}, rms_error_ma={iin_rms})')
    repl.exec(f'_c.set_iout_calibration(gain={iout_gain}, offset={iout_offset}, rms_error_ma={iout_rms})')
    import time as _time
    repl.exec(f'_c.set_calibration_date("{_time.strftime("%Y-%m-%d")}")')
    die_temp = repl.exec('print(board.get_die_temp())')
    repl.exec(f'_c.set_die_temp_celsius({die_temp})')
    print(f'Die temperature at calibration: {float(die_temp):.1f}°C')
    repl.exec('_c.save()')
    repl.exec('board.reload_calibration()')
    print(repl.exec('print(_c.get_calibration_summary())'))

    # Read calibration.dat back from the board and save a host-side copy
    # to firmware/board<N>_calibration.dat, consistent with voltage calibration.
    hw_id = repl.get_hardware_id()
    cal_json = repl.exec(
        "import json; "
        "f = open('calibration.dat'); print(f.read()); f.close()"
    )
    # Look up board number from registry
    registry_path = Path(__file__).parent / 'board_registry.json'
    try:
        import json as _json
        registry = _json.loads(registry_path.read_text())
        board_num = registry['boards'][hw_id]['board_number']
        host_cal_file = Path('firmware') / f'board{board_num}_calibration.dat'
    except (KeyError, FileNotFoundError):
        # Fall back to hardware ID if not in registry
        host_cal_file = Path('firmware') / f'{hw_id}_calibration.dat'
    host_cal_file.write_text(cal_json)
    print(f'Host-side calibration backup saved to {host_cal_file}')
