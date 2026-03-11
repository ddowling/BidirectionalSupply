# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Restore calibration.dat to a board from the host-side backup saved by
# current_sweep.py.  Looks up the backup by the board's hardware ID.
#
import sys
sys.path.insert(0, '.')
import argparse
from pathlib import Path
from remote_repl import RemoteRepl, find_rp2350_port

parser = argparse.ArgumentParser(description='Restore calibration.dat to board from host backup')
parser.add_argument('--board-port', default=None,
                    help='Board serial port (default: auto-detect)')
parser.add_argument('--cal-dir', default='firmware',
                    help='Directory containing calibration backups (default: firmware)')
args = parser.parse_args()

port = args.board_port or find_rp2350_port() or '/dev/ttyACM0'
print(f'Connecting to board on {port}...')

with RemoteRepl(port) as repl:
    repl.setup_board()
    hw_id = repl.get_hardware_id()
    print(f'Board hardware ID: {hw_id}')

    # Look up board number from registry for firmware/board<N>_calibration.dat naming
    registry_path = Path(__file__).parent / 'board_registry.json'
    try:
        import json as _json
        registry = _json.loads(registry_path.read_text())
        board_num = registry['boards'][hw_id]['board_number']
        cal_file = Path(args.cal_dir) / f'board{board_num}_calibration.dat'
    except (KeyError, FileNotFoundError):
        cal_file = Path(args.cal_dir) / f'{hw_id}_calibration.dat'
    if not cal_file.exists():
        print(f'ERROR: No calibration backup found at {cal_file}')
        sys.exit(1)

    cal_json = cal_file.read_text().strip()
    print(f'Restoring from {cal_file} ({len(cal_json)} bytes)...')

    # Write the JSON to the board in one exec to avoid quoting issues
    repl.exec(f'_f = open("calibration.dat", "w"); _f.write({cal_json!r}); _f.close()')
    repl.exec('board.reload_calibration()')
    summary = repl.exec('print(board.calibration.get_calibration_summary())')
    print(summary)
    print('Calibration restored successfully.')
