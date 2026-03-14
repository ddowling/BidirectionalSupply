# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Sweep the OWON SPM6103 PSU from a minimum to maximum input voltage while
# recording the BQ25758 VIN ADC readings against the PSU measured voltage.
# Results are saved to a CSV for offline analysis and a linear calibration
# (gain + offset) is fitted and uploaded to the board.
#
import sys
sys.path.insert(0, '.')
import argparse
import time
import csv
from pathlib import Path
import numpy as np
import pandas as pd
from owon import Owon
from remote_repl import RemoteRepl, find_rp2350_port

parser = argparse.ArgumentParser(description='BQ25758 VIN ADC sweep (PSU voltage reference)')
parser.add_argument('--min-voltage', type=float, default=5.0,
                    help='Minimum input voltage in volts (default: 5.0)')
parser.add_argument('--max-voltage', type=float, default=50.0,
                    help='Maximum input voltage in volts (default: 50.0)')
parser.add_argument('--points', type=int, default=46,
                    help='Number of sweep points (default: 46, ignored if --step is set)')
parser.add_argument('--step', type=float, default=None,
                    help='Fixed step size in volts, e.g. 1.0 (overrides --points)')
parser.add_argument('--samples', type=int, default=5,
                    help='ADC samples to average at each point (default: 5)')
parser.add_argument('--settle', type=float, default=0.5,
                    help='Seconds to wait after setting voltage before sampling (default: 0.5)')
parser.add_argument('--current-limit', type=float, default=0.5,
                    help='PSU current limit in amps (default: 0.5)')
parser.add_argument('--psu-port', default='/dev/spm6103',
                    help='OWON PSU serial port (default: /dev/spm6103)')
parser.add_argument('--board-port', default=None,
                    help='Board serial port (default: auto-detect)')
parser.add_argument('--output', default=None,
                    help='Output CSV filename (default: auto-generated in calibration_results/)')
args = parser.parse_args()

# Generate sweep points
if args.step is not None:
    voltages = np.arange(args.min_voltage, args.max_voltage + args.step * 0.5, args.step)
else:
    voltages = np.linspace(args.min_voltage, args.max_voltage, args.points)

# Output file
Path('calibration_results').mkdir(exist_ok=True)
if args.output:
    outfile = args.output
else:
    timestamp = int(time.time())
    outfile = f'calibration_results/vin_sweep_{timestamp}.csv'

fieldnames = ['set_voltage', 'psu_voltage', 'psu_voltage_std',
              'vin_adc', 'vin_adc_std', 'vin_error_mv']

print(f'Connecting to OWON PSU on {args.psu_port}...')
port = args.board_port or find_rp2350_port() or '/dev/ttyACM0'
print(f'Connecting to board on {port}...')

with Owon(args.psu_port) as psu, RemoteRepl(port) as repl:
    psu.set_remote(True)
    psu.set_current(args.current_limit)
    psu.set_voltage(args.min_voltage)
    psu.set_output(True)
    time.sleep(1.0)
    print(f'PSU enabled: {args.min_voltage}V / {args.current_limit}A limit')

    repl.setup_board()

    print(f'\nSweeping {args.min_voltage:.1f}V to {args.max_voltage:.1f}V '
          f'({len(voltages)} points)')
    print(f'Saving to {outfile}\n')
    print(f'{"#":>4}  {"Set(V)":>8}  {"PSU(V)":>9}  {"VIN_ADC(V)":>11}  {"Error(mV)":>10}')

    try:
        with open(outfile, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for i, set_voltage in enumerate(voltages, 1):
                psu.set_voltage(set_voltage)
                time.sleep(args.settle)

                psu_samples = []
                vin_samples = []

                for _ in range(args.samples):
                    psu_samples.append(psu.measure_voltage())

                    raw = repl.exec('print(board.bq.get_vin_adc())')
                    try:
                        vin_samples.append(float(raw.strip()))
                    except (ValueError, AttributeError):
                        print(f'  WARNING: bad board reading: {raw!r}')
                    time.sleep(0.1)

                if not psu_samples or not vin_samples:
                    print(f'{i:>4}  {set_voltage:>8.3f}  -- skipped --')
                    continue

                psu_mean  = np.mean(psu_samples)
                psu_std   = np.std(psu_samples)
                vin_mean  = np.mean(vin_samples)
                vin_std   = np.std(vin_samples)
                err_mv    = (vin_mean - psu_mean) * 1000

                print(f'{i:>4}  {set_voltage:>8.3f}  {psu_mean:>9.4f}  '
                      f'{vin_mean:>11.4f}  {err_mv:>+10.1f}')

                writer.writerow({
                    'set_voltage':    set_voltage,
                    'psu_voltage':    psu_mean,
                    'psu_voltage_std': psu_std,
                    'vin_adc':        vin_mean,
                    'vin_adc_std':    vin_std,
                    'vin_error_mv':   err_mv,
                })
                f.flush()

    finally:
        psu.set_voltage(0.0)
        psu.set_output(False)
        psu.set_remote(False)
        print(f'\nPSU output off.')

print(f'\nSweep complete. Results saved to {outfile}')

# --- Fit and upload calibration ---
df = pd.read_csv(outfile)
df = df[df['psu_voltage'] > 0.0].copy()
ref = df['psu_voltage'].values
vin = df['vin_adc'].values

# Linear fit: vin = gain*ref + offset  →  corrected = (vin - offset) / gain
lin_coeffs = np.polyfit(ref, vin, 1)
gain, offset = float(lin_coeffs[0]), float(lin_coeffs[1])
lin_corrected = (vin - offset) / gain
lin_rms = float(np.sqrt(np.mean(((lin_corrected - ref) * 1000) ** 2)))

# Quadratic fit: error_mv = a*v^2 + b*v + c  (same model as vout_adc)
error_mv = (vin - ref) * 1000
quad_coeffs = np.polyfit(ref, error_mv, 2)
quad_a, quad_b, quad_c = float(quad_coeffs[0]), float(quad_coeffs[1]), float(quad_coeffs[2])
quad_fitted = np.polyval(quad_coeffs, ref)
quad_residual_mv = error_mv - quad_fitted
quad_rms = float(np.sqrt(np.mean(quad_residual_mv ** 2)))

print(f'\nCalibration fit results:')
print(f'  Linear:    gain={gain:.6f}  offset={offset*1000:+.2f}mV  rms={lin_rms:.1f}mV')
print(f'  Quadratic: {quad_a:.6f}*V^2 + {quad_b:.4f}*V + {quad_c:.2f} mV  rms={quad_rms:.1f}mV')

print(f'\nUploading quadratic calibration to board...')
port = args.board_port or find_rp2350_port() or '/dev/ttyACM0'
with RemoteRepl(port) as repl:
    repl.setup_board()
    repl.exec('import calibration as _cal')
    repl.exec('_c = _cal.Calibration()')
    repl.exec(f'_c.set_vin_calibration(quad_a={quad_a}, quad_b={quad_b}, quad_c={quad_c}, rms_error_mv={quad_rms})')
    import time as _time
    repl.exec(f'_c.set_calibration_date("{_time.strftime("%Y-%m-%d")}")')
    die_temp = repl.exec('print(board.get_die_temp())')
    repl.exec(f'_c.set_die_temp_celsius({die_temp})')
    print(f'Die temperature at calibration: {float(die_temp):.1f}°C')
    repl.exec('_c.save()')
    repl.exec('board.reload_calibration()')
    print(repl.exec('print(_c.get_calibration_summary())'))

    # Read calibration.dat back and save a host-side copy
    hw_id = repl.get_hardware_id()
    cal_json = repl.exec(
        "import json; "
        "f = open('calibration.dat'); print(f.read()); f.close()"
    )
    registry_path = Path(__file__).parent / 'board_registry.json'
    try:
        import json as _json
        registry = _json.loads(registry_path.read_text())
        board_num = registry['boards'][hw_id]['board_number']
        host_cal_file = Path('firmware') / f'board{board_num}_calibration.dat'
    except (KeyError, FileNotFoundError):
        host_cal_file = Path('firmware') / f'{hw_id}_calibration.dat'
    host_cal_file.write_text(cal_json)
    print(f'Host-side calibration backup saved to {host_cal_file}')
