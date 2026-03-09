# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
import sys
sys.path.insert(0, '.')
from automated_calibration import AutomatedCalibration
import numpy as np
import time
import pandas as pd

cal = AutomatedCalibration('/dev/it8511', '/dev/ttyACM0')

if not cal.setup_board():
    print('FAILED to setup board')
    sys.exit(1)

if not cal.setup_electronic_load():
    print('FAILED to setup electronic load')
    sys.exit(1)

cal.set_load_current(0.1)
cal.enable_load()
time.sleep(5)

voltages = np.arange(3.5, 50.5, 0.5)
print(f'Sweeping {len(voltages)} points from {voltages[0]}V to {voltages[-1]}V')

data = []
for i, sv in enumerate(voltages):
    cal.board.exec(f'board.bq.set_output_voltage_limit({sv})')
    time.sleep(2)

    adc_vals = []
    ref_vals = []
    for _ in range(5):
        br = cal.get_board_readings()
        ir = cal.get_it8511_measurements()
        if br and ir:
            adc_vals.append(br['vout_raw'])
            ref_vals.append(ir['voltage'])
        time.sleep(0.3)

    if adc_vals and ref_vals:
        adc_v = np.mean(adc_vals)
        ref_v = np.mean(ref_vals)
        err_mv = (adc_v - ref_v) * 1000
        print(f'{i+1:3d}/{len(voltages)}: Set={sv:.1f}V  IT8511={ref_v:.4f}V  ADC={adc_v:.6f}V  err={err_mv:.1f}mV')
        data.append({
            'set_voltage': sv,
            'it8511_voltage': ref_v,
            'adc_voltage': adc_v,
            'adc_vs_it8511_mv': err_mv,
            'board_number': cal.board_number,
            'hardware_id': cal.board.hardware_id
        })

cal.disable_load()

df = pd.DataFrame(data)
fname = f'calibration_results/board{cal.board_number}_voltage_sweep_fine_20260218.csv'
df.to_csv(fname, index=False)
print(f'\nSaved {len(data)} points to {fname}')

adc = df['adc_voltage'].values
ref = df['it8511_voltage'].values
err = (adc - ref) * 1000
coeffs = np.polyfit(adc, err, 2)
a, b, c = float(coeffs[0]), float(coeffs[1]), float(coeffs[2])
fitted = np.polyval(coeffs, adc)
residual = err - fitted
rms = float(np.sqrt(np.mean(residual**2)))
print(f'\nQuadratic fit: {a:.6f}*V^2 + {b:.4f}*V + {c:.2f} mV')
print(f'RMS residual: {rms:.1f}mV, Max: {np.abs(residual).max():.1f}mV')

print('Uploading calibration to board...')
cal.board.exec('import calibration as _cal')
cal.board.exec('_c = _cal.Calibration()')
cal.board.exec(f'_c.set_vout_calibration(quad_a={a}, quad_b={b}, quad_c={c}, rms_error_mv={rms})')
cal.board.exec(f'''_c.set_calibration_date('{time.strftime("%Y-%m-%d")}')''')
cal.board.exec('_c.set_board_id()')
cal.board.exec('_c.save()')
resp = cal.board.exec('print(_c.get_calibration_summary())')
print(f'Board calibration:\\n{resp}')

cal.board.close()
print('Done!')

