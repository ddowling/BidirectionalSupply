# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Stress test for ideal diode switches.
# Cycles a switch on/off N times while monitoring voltage and current
# via the IT8511 DC load, verifying clean switching behaviour.
#
# Usage:
#   python3 test_switch_stress.py [switch_num] [cycles]
#   Default: switch 2, 100 cycles
#
import sys
sys.path.insert(0, '.')
import time
import serial
from itech_serial import IT8500

SWITCH_NUM = int(sys.argv[1]) if len(sys.argv) > 1 else 2
CYCLES = int(sys.argv[2]) if len(sys.argv) > 2 else 100

LOAD_CURRENT = 1.0   # Amps
V_ON_MIN = 5.0       # Volts — minimum acceptable voltage when switch is closed
V_OFF_MAX = 0.5      # Volts — maximum acceptable voltage when switch is open


def board_exec(ser, cmd):
    ser.write(b'\x03\x03')
    time.sleep(0.1)
    ser.write(b'\x01')
    time.sleep(0.1)
    ser.read_all()
    ser.write(cmd.encode('ascii') + b'\x04')
    out = b''
    deadline = time.time() + 3
    while time.time() < deadline:
        chunk = ser.read(256)
        if chunk:
            out += chunk
            if out.endswith(b'\x04>'):
                break
    if out.startswith(b'OK'):
        out = out[2:]
    parts = out.split(b'\x04')
    return parts[0].decode('ascii', errors='replace').strip() if parts else ''


print(f'Connecting to IT8511 on /dev/it8511...')
load = IT8500('/dev/it8511')

print(f'Connecting to board on /dev/ttyACM0...')
board_ser = serial.Serial('/dev/ttyACM0', 115200, timeout=2)
time.sleep(0.5)

board_exec(board_ser, 'import board; board.setup(); board.bq.setup_adc()')
time.sleep(0.5)

board_exec(board_ser, f'board.set_switch({SWITCH_NUM}, False)')
time.sleep(0.5)

load.mode_set('CC')
load.constant_current_set(LOAD_CURRENT)
load.enable()
time.sleep(0.5)

passes = 0
fails = 0

print(f'Starting {CYCLES}-cycle test on switch {SWITCH_NUM} at {LOAD_CURRENT}A load...')
print(f'Pass criteria: V_on >= {V_ON_MIN}V, V_off <= {V_OFF_MAX}V')
print(f'{"Cycle":>6}  {"V_on":>7}  {"I_on":>6}  {"V_off":>7}  {"I_off":>6}  Result')

try:
    for cycle in range(1, CYCLES + 1):
        board_exec(board_ser, f'board.set_switch({SWITCH_NUM}, True)')
        time.sleep(0.5)
        m_on = load.measure()
        v_on, i_on = m_on['voltage'], m_on['current']

        board_exec(board_ser, f'board.set_switch({SWITCH_NUM}, False)')
        time.sleep(0.5)
        m_off = load.measure()
        v_off, i_off = m_off['voltage'], m_off['current']

        ok = v_on >= V_ON_MIN and v_off <= V_OFF_MAX
        result = 'PASS' if ok else 'FAIL'
        if ok:
            passes += 1
        else:
            fails += 1

        print(f'{cycle:>6}  {v_on:>7.3f}  {i_on:>6.3f}  {v_off:>7.3f}  {i_off:>6.3f}  {result}')
        if not ok:
            print(f'  *** FAIL: V_on={v_on:.3f}V V_off={v_off:.3f}V ***')

finally:
    load.disable()
    board_exec(board_ser, f'board.set_switch({SWITCH_NUM}, False)')
    board_ser.close()

print(f'\nTest complete: {passes}/{CYCLES} passed, {fails} failed')
print('OVERALL: PASS' if fails == 0 else f'OVERALL: FAIL ({fails} failures)')
sys.exit(0 if fails == 0 else 1)
