#!/usr/bin/env python3
# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
"""
Automated calibration system integrating IT8511 DC load control
with BidirectionalSupply ADC calibration.

Requires: pip install itech_serial pyserial
"""

import sys
import time
import pandas as pd
import numpy as np
import json
import serial
from pathlib import Path
from itech_serial import IT8500

REGISTRY_PATH = Path(__file__).parent / 'board_registry.json'


class BoardConnection:
    """Persistent connection to RP2350 board via MicroPython raw REPL"""

    def __init__(self, port='/dev/ttyACM0', baudrate=115200, timeout=3):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    def connect(self):
        """Open serial port and enter MicroPython raw REPL"""
        self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        time.sleep(0.1)
        # Interrupt any running code
        self.ser.write(b'\x03\x03')
        time.sleep(0.2)
        self.ser.read(self.ser.in_waiting)
        # Enter raw REPL (Ctrl-A)
        self.ser.write(b'\x01')
        time.sleep(0.2)
        resp = self.ser.read(self.ser.in_waiting)
        if b'raw REPL' not in resp:
            raise ConnectionError(f"Failed to enter raw REPL: {resp}")
        print(f"Connected to RP2350 on {self.port}")

    def exec(self, cmd, timeout=10):
        """Execute command in raw REPL, return stdout string"""
        self.ser.write(cmd.encode() + b'\x04')
        buf = b''
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                buf += chunk
                if b'\x04>' in buf:
                    break
        # Parse: OK<stdout>\x04<stderr>\x04>
        if buf.startswith(b'OK'):
            buf = buf[2:]
        parts = buf.split(b'\x04')
        stdout = parts[0].decode().strip() if parts else ''
        stderr = parts[1].decode().strip() if len(parts) > 1 else ''
        if stderr:
            print(f"  [RP2350 error: {stderr}]")
        return stdout

    def setup_board(self):
        """Initialize board hardware and ADC"""
        self.exec("import board", timeout=5)
        resp = self.exec("board.setup()", timeout=15)
        if resp:
            print(resp)
        self.exec("board.bq.setup_adc()")
        time.sleep(0.5)
        self.hardware_id = self.get_hardware_id()
        print(f"Board initialized with ADC enabled (HW ID: {self.hardware_id})")

    def get_hardware_id(self):
        """Read the unique hardware ID from the RP2350"""
        resp = self.exec("import ubinascii, machine; print('RP2350_' + ubinascii.hexlify(machine.unique_id()).decode('ascii')[-8:].upper())")
        return resp.strip()

    def close(self):
        """Exit raw REPL and close serial port"""
        if self.ser and self.ser.is_open:
            self.ser.write(b'\x02')  # Ctrl-B to exit raw REPL
            time.sleep(0.1)
            self.ser.close()
            print(f"Disconnected from RP2350")


class AutomatedCalibration:
    def __init__(self, it8511_port='/dev/ttyUSB0', board_port='/dev/ttyACM0', baudrate=4800):
        """
        Initialize automated calibration system

        Args:
            it8511_port: Serial port for IT8511 electronic load
            board_port: Serial port for RP2350 board
            baudrate: Baud rate for IT8511 communication (default 4800)
        """
        self.it8511_port = it8511_port
        self.board_port = board_port
        self.baudrate = baudrate
        self.load = None
        self.board = None

    def load_board_registry(self):
        """Load board registry and look up the connected board"""
        try:
            with open(REGISTRY_PATH) as f:
                registry = json.load(f)
        except FileNotFoundError:
            print(f"Board registry not found at {REGISTRY_PATH}")
            registry = {"boards": {}}

        hw_id = self.board.hardware_id
        if hw_id in registry['boards']:
            info = registry['boards'][hw_id]
            self.board_number = info['board_number']
            print(f"Identified as Board #{self.board_number} ({info.get('description', '')})")
        else:
            print(f"Unknown board {hw_id} - not in registry")
            self.board_number = self._register_new_board(registry, hw_id)

    def _register_new_board(self, registry, hw_id):
        """Prompt user to register a new board"""
        existing = [b['board_number'] for b in registry['boards'].values()]
        next_num = max(existing, default=0) + 1
        resp = input(f"Register as Board #{next_num}? (y/N or enter number): ").strip()
        if resp.lower() == 'y':
            board_num = next_num
        elif resp.isdigit():
            board_num = int(resp)
        else:
            print("Board not registered, using 0")
            return 0

        registry['boards'][hw_id] = {
            "board_number": board_num,
            "description": f"Board #{board_num}",
            "calibrated": False,
            "calibration_date": None,
            "notes": ""
        }
        with open(REGISTRY_PATH, 'w') as f:
            json.dump(registry, f, indent=4)
        print(f"Registered {hw_id} as Board #{board_num}")
        return board_num

    def setup_board(self):
        """Initialize persistent connection to RP2350 board"""
        try:
            self.board = BoardConnection(self.board_port)
            self.board.connect()
            self.board.setup_board()
            self.load_board_registry()
            return True
        except Exception as e:
            print(f"Error setting up board: {e}")
            return False

    def setup_electronic_load(self):
        """Initialize and configure IT8511 electronic load"""
        try:
            self.load = IT8500(self.it8511_port, baudrate=self.baudrate)
            self.load.control_set_remote()

            info = self.load.identify()
            print(f"Connected to: {info}")

            self.load.mode_set('cc')
            self.load.max_voltage_set(50.0)
            self.load.max_current_set(5.0)
            self.load.max_power_set(100.0)

            print("IT8511 setup complete")
            return True

        except Exception as e:
            print(f"Error setting up IT8511: {e}")
            return False

    def set_load_current(self, current_a):
        """Set electronic load current"""
        try:
            self.load.constant_current_set(current_a)
            print(f"Set load current: {current_a}A")
        except Exception as e:
            print(f"Error setting load current: {e}")

    def enable_load(self):
        """Enable electronic load"""
        try:
            self.load.enable()
            print("Electronic load enabled")
        except Exception as e:
            print(f"Error enabling load: {e}")

    def disable_load(self):
        """Disable electronic load (safety)"""
        try:
            self.load.disable()
            print("Electronic load disabled")
        except Exception as e:
            print(f"Error disabling load: {e}")

    def get_board_readings(self):
        """Get voltage and current readings from RP2350 board"""
        resp = self.board.exec(
            "print(f'{board.bq.get_vout_adc():.6f},{board.bq.get_iout_adc():.6f}')"
        )
        try:
            parts = resp.split(',')
            return {
                'vout_raw': float(parts[0]),
                'iout_raw': float(parts[1]),
            }
        except (ValueError, IndexError):
            print(f"  Failed to parse board readings: {resp}")
            return None

    def get_it8511_measurements(self):
        """Get calibrated voltage/current measurements from IT8511"""
        try:
            measurements = self.load.measure()
            return {
                'voltage': measurements['voltage'],
                'current': measurements['current'],
                'power': measurements['power'],
            }
        except Exception as e:
            print(f"Error reading IT8511 measurements: {e}")
            return None

    def automated_voltage_calibration(self, voltage_range=(3.5, 48.0), num_points=45, load_current=0.1):
        """
        Run automated voltage calibration using IT8511 as calibrated reference

        Args:
            voltage_range: (min_v, max_v) tuple
            num_points: Number of voltage points to test
            load_current: Constant load current in Amps
        """

        print("=" * 60)
        print("Starting Automated Voltage Calibration")
        print("=" * 60)

        # Safety check
        response = input(f"This will set {load_current}A load and sweep {voltage_range[0]}V to {voltage_range[1]}V. Continue? (y/N): ")
        if response.lower() != 'y':
            print("Calibration cancelled")
            return

        # Setup instruments
        if not self.setup_board():
            print("Failed to setup board connection")
            return
        if not self.setup_electronic_load():
            print("Failed to setup electronic load")
            return

        try:
            # Set constant load current
            self.set_load_current(load_current)
            self.enable_load()

            print(f"Load enabled at {load_current}A")
            print("Waiting 5 seconds for system to stabilize...")
            time.sleep(5)

            # Generate voltage points
            voltages = np.linspace(voltage_range[0], voltage_range[1], num_points)

            calibration_data = []

            for i, set_voltage in enumerate(voltages):
                print(f"Point {i+1}/{num_points}: Setting {set_voltage:.3f}V")

                # Set output voltage on RP2350
                self.board.exec(f"board.bq.set_output_voltage_limit({set_voltage})")

                # Wait for settling
                time.sleep(2)

                # Take multiple readings for statistics
                board_readings = []
                it8511_readings = []

                for _ in range(5):
                    board_data = self.get_board_readings()
                    it8511_data = self.get_it8511_measurements()

                    if board_data and it8511_data:
                        board_readings.append(board_data['vout_raw'])
                        it8511_readings.append(it8511_data['voltage'])
                    time.sleep(0.5)

                if board_readings and it8511_readings:
                    adc_voltage = np.mean(board_readings)
                    adc_std = np.std(board_readings)
                    reference_voltage = np.mean(it8511_readings)  # IT8511 calibrated measurement
                    reference_std = np.std(it8511_readings)

                    error_mv = (adc_voltage - reference_voltage) * 1000
                    error_percent = (error_mv / (reference_voltage * 1000)) * 100

                    # Calculate setpoint error (command vs actual delivery)
                    setpoint_error_mv = (reference_voltage - set_voltage) * 1000
                    setpoint_error_percent = (setpoint_error_mv / (set_voltage * 1000)) * 100

                    calibration_data.append({
                        'set_voltage': set_voltage,
                        'adc_voltage': adc_voltage,
                        'adc_std': adc_std,
                        'reference_voltage': reference_voltage,
                        'reference_std': reference_std,
                        'adc_error_mv': error_mv,
                        'adc_error_percent': error_percent,
                        'setpoint_error_mv': setpoint_error_mv,
                        'setpoint_error_percent': setpoint_error_percent,
                        'board_readings': board_readings,
                        'it8511_readings': it8511_readings
                    })

                    print(f"  Set: {set_voltage:.3f}V → Actual: {reference_voltage:.6f}V (SP_err: {setpoint_error_mv:.1f}mV)")
                    print(f"  ADC: {adc_voltage:.6f}V → Error: {error_mv:.1f}mV ({error_percent:.2f}%)")
                else:
                    print(f"  Failed to get readings for {set_voltage:.3f}V")

            # Save results
            df = pd.DataFrame(calibration_data)
            df['board_number'] = self.board_number
            df['hardware_id'] = self.board.hardware_id
            timestamp = int(time.time())
            filename = f"calibration_results/board{self.board_number}_voltage_cal_{timestamp}.csv"
            df.to_csv(filename, index=False)

            print(f"\nCalibration complete! Results saved to {filename}")
            print(f"Board #{self.board_number} ({self.board.hardware_id})")
            print(f"Collected {len(calibration_data)} data points")

            # Fit quadratic correction and upload to board
            if len(calibration_data) >= 3:
                self.apply_vout_calibration(df)

            # Generate analysis plots
            self.generate_analysis_plots(df, timestamp)

        finally:
            # Always disable load and close board for safety
            print("\nDisabling electronic load...")
            self.disable_load()
            self.board.close()
            print("Calibration finished safely")

    def apply_vout_calibration(self, df):
        """Fit quadratic correction from calibration data and upload to board"""
        adc_values = df['adc_voltage'].values
        ref_values = df['reference_voltage'].values
        error_mv = (adc_values - ref_values) * 1000

        # Fit quadratic: error_mv = a*v^2 + b*v + c
        coeffs = np.polyfit(adc_values, error_mv, 2)
        a, b, c = float(coeffs[0]), float(coeffs[1]), float(coeffs[2])

        # Calculate residual
        fitted = np.polyval(coeffs, adc_values)
        residual = error_mv - fitted
        rms_error = float(np.sqrt(np.mean(residual**2)))

        print(f"\nQuadratic fit: {a:.6f}*V^2 + {b:.4f}*V + {c:.2f} mV")
        print(f"RMS residual: {rms_error:.1f}mV, Max: {np.abs(residual).max():.1f}mV")

        # Upload calibration to board
        print("Uploading calibration to board...")
        self.board.exec(f"import calibration as _cal")
        self.board.exec(f"_c = _cal.Calibration()")
        self.board.exec(f"_c.set_vout_calibration(quad_a={a}, quad_b={b}, quad_c={c}, rms_error_mv={rms_error})")
        self.board.exec(f"_c.set_calibration_date('{time.strftime('%Y-%m-%d')}')")
        self.board.exec(f"_c.set_board_id()")
        self.board.exec(f"_c.save()")

        # Verify
        resp = self.board.exec("print(_c.get_calibration_summary())")
        print(f"Board calibration:\n{resp}")

        # Update registry
        try:
            with open(REGISTRY_PATH) as f:
                registry = json.load(f)
            hw_id = self.board.hardware_id
            if hw_id in registry['boards']:
                registry['boards'][hw_id]['calibrated'] = True
                registry['boards'][hw_id]['calibration_date'] = time.strftime('%Y-%m-%d')
                registry['boards'][hw_id]['notes'] = f"quad_a={a:.6f}, quad_b={b:.4f}, quad_c={c:.2f}"
                with open(REGISTRY_PATH, 'w') as f:
                    json.dump(registry, f, indent=4)
        except Exception as e:
            print(f"Warning: could not update registry: {e}")

    def generate_analysis_plots(self, df, timestamp):
        """Generate matplotlib analysis plots"""
        try:
            # Import your existing analysis functions
            sys.path.append('calibration_results')
            # You can adapt your existing analyze_calibration.py functions here
            print(f"Analysis plots would be generated for dataset {timestamp}")

        except Exception as e:
            print(f"Error generating plots: {e}")

    def automated_current_calibration(self, current_range=(0.1, 5.0), num_points=25, test_voltage=12.0):
        """
        Run automated current calibration using IT8511 as calibrated reference

        Args:
            current_range: (min_a, max_a) tuple for current sweep
            num_points: Number of current points to test
            test_voltage: Fixed voltage for current testing
        """

        print("=" * 60)
        print("Starting Automated Current Calibration")
        print("=" * 60)

        # Safety check
        response = input(f"This will sweep current from {current_range[0]}A to {current_range[1]}A at {test_voltage}V. Continue? (y/N): ")
        if response.lower() != 'y':
            print("Calibration cancelled")
            return

        # Setup instruments
        if not self.setup_board():
            print("Failed to setup board connection")
            return
        if not self.setup_electronic_load():
            print("Failed to setup electronic load")
            return

        try:
            # Set fixed test voltage
            print(f"Setting output voltage to {test_voltage}V")
            self.board.exec(f"board.bq.set_output_voltage_limit({test_voltage})")
            time.sleep(3)  # Allow voltage to settle

            # Generate current points
            currents = np.linspace(current_range[0], current_range[1], num_points)

            calibration_data = []

            for i, set_current in enumerate(currents):
                print(f"Point {i+1}/{num_points}: Setting {set_current:.3f}A load")

                # Set load current
                self.set_load_current(set_current)
                self.enable_load()

                # Wait for settling
                time.sleep(3)

                # Take multiple readings for statistics
                board_readings = []
                it8511_readings = []
                it8511_voltage_readings = []

                for _ in range(5):
                    board_data = self.get_board_readings()
                    it8511_data = self.get_it8511_measurements()

                    if board_data and it8511_data:
                        board_readings.append(board_data['iout_raw'])
                        it8511_readings.append(it8511_data['current'])
                        it8511_voltage_readings.append(it8511_data['voltage'])
                    time.sleep(0.5)

                if board_readings and it8511_readings:
                    adc_current = np.mean(board_readings)
                    adc_std = np.std(board_readings)
                    reference_current = np.mean(it8511_readings)  # IT8511 calibrated measurement
                    reference_std = np.std(it8511_readings)
                    reference_voltage = np.mean(it8511_voltage_readings)

                    error_ma = (adc_current - reference_current) * 1000
                    error_percent = (error_ma / (reference_current * 1000)) * 100

                    calibration_data.append({
                        'set_current': set_current,
                        'adc_current': adc_current,
                        'adc_std': adc_std,
                        'reference_current': reference_current,
                        'reference_std': reference_std,
                        'reference_voltage': reference_voltage,
                        'error_ma': error_ma,
                        'error_percent': error_percent,
                        'board_readings': board_readings,
                        'it8511_readings': it8511_readings,
                        'test_voltage': test_voltage
                    })

                    print(f"  ADC: {adc_current:.6f}A, Ref: {reference_current:.6f}A, Error: {error_ma:.1f}mA ({error_percent:.2f}%)")
                    print(f"  IT8511 voltage: {reference_voltage:.3f}V")
                else:
                    print(f"  Failed to get readings for {set_current:.3f}A")

            # Save results
            df = pd.DataFrame(calibration_data)
            df['board_number'] = self.board_number
            df['hardware_id'] = self.board.hardware_id
            timestamp = int(time.time())
            filename = f"calibration_results/board{self.board_number}_current_cal_{timestamp}.csv"
            df.to_csv(filename, index=False)

            print(f"\nCurrent calibration complete! Results saved to {filename}")
            print(f"Board #{self.board_number} ({self.board.hardware_id})")
            print(f"Collected {len(calibration_data)} data points")

            # Generate analysis plots
            self.generate_current_analysis_plots(df, timestamp)

        finally:
            # Always disable load and close board for safety
            print("\nDisabling electronic load...")
            self.disable_load()
            self.board.close()
            print("Current calibration finished safely")

    def generate_current_analysis_plots(self, df, timestamp):
        """Generate matplotlib analysis plots for current calibration"""
        try:
            print(f"Current analysis plots would be generated for dataset {timestamp}")
            # Similar to voltage analysis but for current data

        except Exception as e:
            print(f"Error generating current plots: {e}")

def main():
    # Configuration
    IT8511_PORT = '/dev/ttyUSB0'
    BOARD_PORT = '/dev/ttyACM0'

    print("BidirectionalSupply Automated Calibration System")
    print("=" * 50)
    print("1. Voltage Calibration (sweep voltage, constant current)")
    print("2. Current Calibration (sweep current, constant voltage)")
    print("3. Full Calibration (both voltage and current)")
    print("4. Exit")

    choice = input("\nSelect calibration type (1-4): ").strip()

    if choice not in ['1', '2', '3', '4']:
        print("Invalid choice. Exiting.")
        return

    if choice == '4':
        print("Exiting...")
        return

    cal = AutomatedCalibration(IT8511_PORT, BOARD_PORT)

    if choice == '1':
        # Voltage calibration only
        cal.automated_voltage_calibration(
            voltage_range=(3.5, 48.0),
            num_points=45,
            load_current=0.1  # 100mA constant load
        )

    elif choice == '2':
        # Current calibration only
        cal.automated_current_calibration(
            current_range=(0.1, 5.0),
            num_points=25,
            test_voltage=12.0  # Fixed 12V for current testing
        )

    elif choice == '3':
        # Full calibration - both voltage and current
        print("\n" + "=" * 50)
        print("FULL CALIBRATION - PHASE 1: VOLTAGE")
        print("=" * 50)

        cal.automated_voltage_calibration(
            voltage_range=(3.5, 48.0),
            num_points=45,
            load_current=0.1
        )

        print("\n" + "=" * 50)
        print("FULL CALIBRATION - PHASE 2: CURRENT")
        print("=" * 50)

        cal.automated_current_calibration(
            current_range=(0.1, 5.0),
            num_points=25,
            test_voltage=12.0
        )

        print("\n" + "=" * 50)
        print("FULL CALIBRATION COMPLETE")
        print("=" * 50)

if __name__ == "__main__":
    main()
