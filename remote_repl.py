# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# RemoteRepl — lightweight raw-REPL client for MicroPython boards.
#
# Designed for the RP2350 running MicroPython, but should work with any
# MicroPython board that supports raw REPL (Ctrl-A / Ctrl-D protocol).
#
# Serial reading uses a short timeout on ser.read() rather than
# in_waiting, because in_waiting calls fcntl.ioctl(TIOCINQ) which raises
# OSError on some Linux/VMware setups.

import serial
import time

# USB identifiers for the RP2350 running MicroPython.
# VID 0x2E8A = Raspberry Pi Foundation
# PID 0x0005 = MicroPython CDC REPL device
RP2350_USB_VID = 0x2E8A
RP2350_USB_PID = 0x0005

DEFAULT_PORT    = '/dev/ttyACM0'
DEFAULT_BAUD    = 115200
# Short read timeout so ser.read(N) returns promptly when the buffer is
# drained rather than blocking for the full timeout waiting to fill N bytes.
_READ_TIMEOUT   = 0.02


def find_rp2350_port(vid=RP2350_USB_VID, pid=RP2350_USB_PID):
    """Scan serial ports and return the device path of the first RP2350 found.

    Matches on USB VID and PID. Returns None if no matching port is found.

    Example:
        port = find_rp2350_port()
        if port is None:
            raise RuntimeError('RP2350 not found')
    """
    from serial.tools import list_ports
    for port in list_ports.comports():
        if port.vid == vid and port.pid == pid:
            return port.device
    return None


class RemoteRepl:
    """Raw-REPL client for a MicroPython board connected via USB serial.

    Usage — explicit open/close:
        repl = RemoteRepl('/dev/ttyACM0')
        repl.connect()
        repl.exec('import board; board.setup()')
        print(repl.exec('print(board.get_switch_vsense(2))'))
        repl.close()

    Usage — context manager:
        with RemoteRepl('/dev/ttyACM0') as repl:
            repl.exec('import board; board.setup()')
            print(repl.exec('print(42)'))
    """

    def __init__(self, port=DEFAULT_PORT, baudrate=DEFAULT_BAUD):
        self.port = port
        self.baudrate = baudrate
        self._ser = None

    # --- Connection management ---

    def connect(self):
        """Open the serial port and enter MicroPython raw REPL."""
        self._ser = serial.Serial(self.port, self.baudrate, timeout=_READ_TIMEOUT)
        time.sleep(0.1)
        # Interrupt any running code
        self._ser.write(b'\x03\x03')
        time.sleep(0.1)
        # Drain any pending output
        self._drain()
        # Enter raw REPL (Ctrl-A)
        self._ser.write(b'\x01')
        time.sleep(0.1)
        resp = self._drain()
        if b'raw REPL' not in resp:
            raise ConnectionError(f'Failed to enter raw REPL on {self.port}: {resp!r}')

    def close(self):
        """Exit raw REPL and close the serial port."""
        if self._ser and self._ser.is_open:
            self._ser.write(b'\x02')  # Ctrl-B: exit raw REPL
            time.sleep(0.1)
            self._ser.close()
        self._ser = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    # --- Command execution ---

    def exec(self, cmd, timeout=10):
        """Execute a Python statement/expression in raw REPL.

        Returns stdout as a string. Prints any stderr to the console.
        Raises RuntimeError on timeout.
        """
        self._ser.write(cmd.encode('utf-8') + b'\x04')
        buf = b''
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = self._ser.read(256)
            if chunk:
                buf += chunk
                if buf.endswith(b'\x04>'):
                    break
        else:
            raise RuntimeError(f'Timeout waiting for response to: {cmd!r}')

        # Response format: OK<stdout>\x04<stderr>\x04>
        if buf.startswith(b'OK'):
            buf = buf[2:]
        parts = buf.split(b'\x04')
        stdout = parts[0].decode('utf-8', errors='replace').strip() if parts else ''
        stderr = parts[1].decode('utf-8', errors='replace').strip() if len(parts) > 1 else ''
        if stderr:
            print(f'[RemoteRepl stderr: {stderr}]')
        return stdout

    # --- Board helpers ---

    def get_hardware_id(self):
        """Return the RP2350 unique hardware ID string (e.g. 'RP2350_1E017096')."""
        return self.exec(
            "import ubinascii, machine; "
            "print('RP2350_' + ubinascii.hexlify(machine.unique_id()).decode()[-8:].upper())"
        )

    def setup_board(self):
        """Import board module, run setup() and setup_adc()."""
        self.exec('import board', timeout=5)
        out = self.exec('board.setup()', timeout=15)
        if out:
            print(out)
        self.exec('board.bq.setup_adc()')
        time.sleep(0.5)

    # --- Internal ---

    def _drain(self):
        """Read and return all bytes currently in the buffer."""
        buf = b''
        while True:
            chunk = self._ser.read(256)
            if not chunk:
                break
            buf += chunk
        return buf
