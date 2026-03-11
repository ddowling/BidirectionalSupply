# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Stress test for ideal diode switches.
# Cycles a switch on/off N times while monitoring voltage and current
# via the IT8511 DC load, verifying clean switching behaviour.
#
import sys
sys.path.insert(0, '.')
import argparse
import time
from itech_serial import IT8500
from remote_repl import RemoteRepl, find_rp2350_port

parser = argparse.ArgumentParser(description='Ideal diode switch stress test')
parser.add_argument('switch', type=int, default=2, nargs='?',
                    help='Switch number to test (0-3, default: 2)')
parser.add_argument('cycles', type=int, default=100, nargs='?',
                    help='Number of on/off cycles (default: 100)')
parser.add_argument('--current', '-c', type=float, default=5.0,
                    help='DC load current in amps (default: 5.0)')
parser.add_argument('--v-on-min', type=float, default=5.0,
                    help='Minimum acceptable V_on in volts (default: 5.0)')
parser.add_argument('--v-off-max', type=float, default=0.5,
                    help='Maximum acceptable V_off in volts (default: 0.5)')
parser.add_argument('--load-port', default='/dev/it8511',
                    help='IT8511 serial port (default: /dev/it8511)')
parser.add_argument('--board-port', default=None,
                    help='Board serial port (default: auto-detect by USB ID)')
args = parser.parse_args()

print(f'Connecting to IT8511 on {args.load_port}...')
load = IT8500(args.load_port)

port = args.board_port or find_rp2350_port() or '/dev/ttyACM0'
print(f'Connecting to board on {port}...')

passes = 0
fails = 0

with RemoteRepl(port) as repl:
    repl.setup_board()
    repl.exec(f'board.set_switch({args.switch}, False)')
    time.sleep(0.5)

    load.control_set_remote()
    load.mode_set('CC')
    load.constant_current_set(args.current)
    load.enable()
    time.sleep(0.5)

    print(f'Starting {args.cycles}-cycle test on switch {args.switch} at {args.current}A load...')
    print(f'Pass criteria: V_on >= {args.v_on_min}V, V_off <= {args.v_off_max}V')
    print(f'{"Cycle":>6}  {"V_on":>7}  {"I_on":>6}  {"V_off":>7}  {"I_off":>6}  Result')

    try:
        for cycle in range(1, args.cycles + 1):
            repl.exec(f'board.set_switch({args.switch}, True)')
            time.sleep(0.5)
            m_on = load.measure()
            v_on, i_on = m_on['voltage'], m_on['current']

            repl.exec(f'board.set_switch({args.switch}, False)')
            time.sleep(0.5)
            m_off = load.measure()
            v_off, i_off = m_off['voltage'], m_off['current']

            ok = v_on >= args.v_on_min and v_off <= args.v_off_max
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
        load.control_set_local()
        repl.exec(f'board.set_switch({args.switch}, False)')

print(f'\nTest complete: {passes}/{args.cycles} passed, {fails} failed')
print('OVERALL: PASS' if fails == 0 else f'OVERALL: FAIL ({fails} failures)')
sys.exit(0 if fails == 0 else 1)
