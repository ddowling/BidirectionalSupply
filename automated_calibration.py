#!/usr/bin/env python3
"""
Automated calibration system integrating IT8511 DC load control
with BidirectionalSupply ADC calibration
"""

import sys
import time
import pandas as pd
import numpy as np
import json
import subprocess
from pathlib import Path

# You'll need to install the IT8512 library:
# git clone https://github.com/mattvenn/it8512.git
# sys.path.append('path/to/it8512')
# from dcload import DCLoad

class AutomatedCalibration:
    def __init__(self, it8511_port='COM3', mpremote_port=None):
        """
        Initialize automated calibration system
        
        Args:
            it8511_port: Serial port for IT8511 electronic load
            mpremote_port: Port for RP2350 (None for auto-detect)
        """
        self.it8511_port = it8511_port
        self.mpremote_port = mpremote_port
        self.load = None
        
    def setup_electronic_load(self):
        """Initialize and configure IT8511 electronic load"""
        try:
            # Uncomment when library is available:
            # from dcload import DCLoad
            # self.load = DCLoad()
            # self.load.Initialize(self.it8511_port, 9600)
            # 
            # # Get load information
            # info = self.load.GetProductInformation()
            # print(f"Connected to: {info}")
            # 
            # # Set to constant current mode with safety limits
            # self.load.SetMode('cc')
            # self.load.SetMaxVoltage(50.0)  # 50V safety limit
            # self.load.SetMaxCurrent(5.0)   # 5A safety limit
            # self.load.SetMaxPower(100.0)   # 100W safety limit
            
            print("IT8511 setup complete (simulated)")
            return True
            
        except Exception as e:
            print(f"Error setting up IT8511: {e}")
            return False
    
    def set_load_current(self, current_a):
        """Set electronic load current"""
        try:
            if self.load:
                # self.load.SetCCCurrent(current_a)
                pass
            print(f"Set load current: {current_a}A")
            
        except Exception as e:
            print(f"Error setting load current: {e}")
    
    def enable_load(self):
        """Enable electronic load"""
        try:
            if self.load:
                # self.load.TurnLoadOn()
                pass
            print("Electronic load enabled")
            
        except Exception as e:
            print(f"Error enabling load: {e}")
    
    def disable_load(self):
        """Disable electronic load (safety)"""
        try:
            if self.load:
                # self.load.TurnLoadOff()
                pass
            print("Electronic load disabled")
            
        except Exception as e:
            print(f"Error disabling load: {e}")
    
    def run_mpremote_command(self, command):
        """Execute mpremote command and return output"""
        try:
            if self.mpremote_port:
                cmd = f"mpremote connect {self.mpremote_port} exec \"{command}\""
            else:
                cmd = f"mpremote exec \"{command}\""
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                print(f"mpremote error: {result.stderr}")
                return None
                
        except Exception as e:
            print(f"Error running mpremote command: {e}")
            return None
    
    def get_board_readings(self):
        """Get voltage and current readings from RP2350 board"""
        command = """
import board
print(f"vout_raw:{board.bq.get_vout_adc():.6f}")
print(f"iout_raw:{board.bq.get_iout_adc():.6f}")
print(f"vout_cal:{board.get_vout_calibrated():.6f}")
print(f"iout_cal:{board.get_iout_calibrated():.6f}")
"""
        output = self.run_mpremote_command(command)
        if output:
            readings = {}
            for line in output.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    readings[key] = float(value)
            return readings
        return None
    
    def get_it8511_measurements(self):
        """Get calibrated voltage/current measurements from IT8511"""
        try:
            if self.load:
                # measurements = self.load.GetInputValues()
                # return {
                #     'voltage': measurements[0],  # Measured voltage
                #     'current': measurements[1],  # Measured current
                #     'power': measurements[2],    # Measured power
                #     'load_state': measurements[3] # Load on/off state
                # }
                pass
            
            # Simulation for now - replace with actual measurements
            return {
                'voltage': 12.345,
                'current': 0.098,
                'power': 1.210,
                'load_state': True
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
        
        # Setup electronic load
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
                voltage_cmd = f"board.bq.set_output_voltage({set_voltage})"
                self.run_mpremote_command(voltage_cmd)
                
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
            timestamp = int(time.time())
            filename = f"calibration_results/automated_cal_{timestamp}.csv"
            df.to_csv(filename, index=False)
            
            print(f"\nCalibration complete! Results saved to {filename}")
            print(f"Collected {len(calibration_data)} data points")
            
            # Generate analysis plots
            self.generate_analysis_plots(df, timestamp)
            
        finally:
            # Always disable load for safety
            print("\nDisabling electronic load...")
            self.disable_load()
            print("Calibration finished safely")
    
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
        
        # Setup electronic load
        if not self.setup_electronic_load():
            print("Failed to setup electronic load")
            return
        
        try:
            # Set fixed test voltage
            print(f"Setting output voltage to {test_voltage}V")
            voltage_cmd = f"board.bq.set_output_voltage({test_voltage})"
            self.run_mpremote_command(voltage_cmd)
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
                
                for _ in range(5):
                    board_data = self.get_board_readings()
                    it8511_data = self.get_it8511_measurements()
                    
                    if board_data and it8511_data:
                        board_readings.append(board_data['iout_raw'])
                        it8511_readings.append(it8511_data['current'])
                    time.sleep(0.5)
                
                if board_readings and it8511_readings:
                    adc_current = np.mean(board_readings)
                    adc_std = np.std(board_readings)
                    reference_current = np.mean(it8511_readings)  # IT8511 calibrated measurement
                    reference_std = np.std(it8511_readings)
                    
                    error_ma = (adc_current - reference_current) * 1000
                    error_percent = (error_ma / (reference_current * 1000)) * 100
                    
                    calibration_data.append({
                        'set_current': set_current,
                        'adc_current': adc_current,
                        'adc_std': adc_std,
                        'reference_current': reference_current,
                        'reference_std': reference_std,
                        'error_ma': error_ma,
                        'error_percent': error_percent,
                        'board_readings': board_readings,
                        'it8511_readings': it8511_readings,
                        'test_voltage': test_voltage
                    })
                    
                    print(f"  ADC: {adc_current:.6f}A, Ref: {reference_current:.6f}A, Error: {error_ma:.1f}mA ({error_percent:.2f}%)")
                else:
                    print(f"  Failed to get readings for {set_current:.3f}A")
            
            # Save results
            df = pd.DataFrame(calibration_data)
            timestamp = int(time.time())
            filename = f"calibration_results/current_cal_{timestamp}.csv"
            df.to_csv(filename, index=False)
            
            print(f"\nCurrent calibration complete! Results saved to {filename}")
            print(f"Collected {len(calibration_data)} data points")
            
            # Generate analysis plots
            self.generate_current_analysis_plots(df, timestamp)
            
        finally:
            # Always disable load for safety
            print("\nDisabling electronic load...")
            self.disable_load()
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
    IT8511_PORT = 'COM3'  # Adjust for your system (/dev/ttyUSB0 on Linux)
    MPREMOTE_PORT = None  # None for auto-detect, or specify port
    
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
    
    cal = AutomatedCalibration(IT8511_PORT, MPREMOTE_PORT)
    
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