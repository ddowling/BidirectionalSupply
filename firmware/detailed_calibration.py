"""
Detailed calibration data collection for PC analysis

This module collects high-resolution calibration data and exports it
to CSV files that can be analyzed with matplotlib on a PC.

Features:
- High-resolution voltage and current sweeps
- CSV export for matplotlib analysis
- Error analysis and statistics
- Multi-channel data collection
"""

import board
import time
import json

def export_detailed_voltage_calibration(filename="voltage_cal_data.csv", voltage_range=(3.5, 20.0), num_points=50):
    """
    Perform detailed voltage calibration sweep and export to CSV
    
    Args:
        filename: CSV filename for export
        voltage_range: (min_voltage, max_voltage) in Volts
        num_points: Number of test points
    """
    print(f"=== Detailed Voltage Calibration Export ===")
    print(f"Range: {voltage_range[0]}V to {voltage_range[1]}V")
    print(f"Points: {num_points}")
    print(f"Output file: {filename}")
    
    # Generate test voltages
    min_v, max_v = voltage_range
    test_voltages = []
    for i in range(num_points):
        voltage = min_v + (max_v - min_v) * i / (num_points - 1)
        test_voltages.append(voltage)
    
    print("\nCollecting data points...")
    results = []
    
    for i, set_voltage in enumerate(test_voltages):
        try:
            # Set the output voltage
            board.bq.set_output_voltage_limit(set_voltage)
            
            # Wait for settling
            time.sleep(1.5)
            
            # Take multiple readings for averaging
            readings = []
            for _ in range(5):
                readings.append(board.bq.get_vout_adc())
                time.sleep(0.1)
            
            # Calculate statistics
            adc_voltage = sum(readings) / len(readings)
            adc_std = (sum((x - adc_voltage)**2 for x in readings) / len(readings))**0.5
            
            # Calculate errors
            error_mv = (adc_voltage - set_voltage) * 1000
            error_percent = (error_mv / (set_voltage * 1000)) * 100
            
            # Store result
            result = {
                'set_voltage': set_voltage,
                'adc_voltage': adc_voltage,
                'adc_std': adc_std,
                'error_mv': error_mv,
                'error_percent': error_percent,
                'readings': readings
            }
            results.append(result)
            
            print(f"  {i+1:2d}/{num_points}: {set_voltage:6.2f}V → {adc_voltage:6.3f}V (±{adc_std*1000:.1f}mV) error: {error_mv:+6.1f}mV")
            
        except Exception as e:
            print(f"Error at {set_voltage}V: {e}")
            break
    
    # Export to CSV
    print(f"\nExporting {len(results)} data points to {filename}...")
    
    with open(filename, 'w') as f:
        # Write header
        f.write("set_voltage,adc_voltage,adc_std,error_mv,error_percent,reading1,reading2,reading3,reading4,reading5\n")
        
        # Write data
        for result in results:
            readings_str = ",".join(f"{r:.6f}" for r in result['readings'])
            f.write(f"{result['set_voltage']:.6f},{result['adc_voltage']:.6f},{result['adc_std']:.6f},")
            f.write(f"{result['error_mv']:.3f},{result['error_percent']:.4f},{readings_str}\n")
    
    print(f"Export complete: {filename}")
    return results

def export_detailed_current_calibration(filename="current_cal_data.csv", current_range=(0.1, 3.0), num_points=20):
    """
    Perform detailed current calibration with IT8511 and export to CSV
    
    Args:
        filename: CSV filename for export
        current_range: (min_current, max_current) in Amps
        num_points: Number of test points
        
    Note: Requires manual operation of IT8511 electronic load
    """
    print(f"=== Detailed Current Calibration Export ===")
    print(f"Range: {current_range[0]}A to {current_range[1]}A")
    print(f"Points: {num_points}")
    print(f"Output file: {filename}")
    
    # Set stable voltage for current testing
    test_voltage = 12.0
    board.bq.set_output_voltage_limit(test_voltage)
    print(f"Set output voltage to {test_voltage}V for current testing")
    
    # Generate test currents
    min_i, max_i = current_range
    test_currents = []
    for i in range(num_points):
        current = min_i + (max_i - min_i) * i / (num_points - 1)
        test_currents.append(current)
    
    print("\nInstructions:")
    print("1. Connect IT8511 electronic load to converter output")
    print("2. For each test current, set IT8511 to that value")
    print("3. Press Enter when current is stable")
    print("4. System will take multiple readings for statistics")
    print()
    
    results = []
    
    for i, set_current in enumerate(test_currents):
        try:
            # Prompt user to set the load
            input(f"[{i+1}/{num_points}] Set IT8511 to {set_current:.2f}A, then press Enter...")
            
            # Take multiple readings for statistics
            voltage_readings = []
            current_readings = []
            
            for j in range(10):  # More readings for better statistics
                voltage_readings.append(board.bq.get_vout_adc())
                current_readings.append(abs(board.bq.get_iout_adc()))
                time.sleep(0.2)
            
            # Calculate statistics
            avg_voltage = sum(voltage_readings) / len(voltage_readings)
            avg_current = sum(current_readings) / len(current_readings)
            voltage_std = (sum((x - avg_voltage)**2 for x in voltage_readings) / len(voltage_readings))**0.5
            current_std = (sum((x - avg_current)**2 for x in current_readings) / len(current_readings))**0.5
            
            # Calculate errors
            current_error_ma = (avg_current - set_current) * 1000
            current_error_percent = (current_error_ma / (set_current * 1000)) * 100
            
            # Calculate power
            power = avg_voltage * avg_current
            
            # Store result
            result = {
                'set_current': set_current,
                'adc_current': avg_current,
                'current_std': current_std,
                'avg_voltage': avg_voltage,
                'voltage_std': voltage_std,
                'current_error_ma': current_error_ma,
                'current_error_percent': current_error_percent,
                'power': power,
                'current_readings': current_readings,
                'voltage_readings': voltage_readings
            }
            results.append(result)
            
            print(f"  Result: {avg_current:.3f}A (±{current_std*1000:.1f}mA) @ {avg_voltage:.2f}V = {power:.1f}W, error: {current_error_ma:+5.1f}mA")
            
        except KeyboardInterrupt:
            print("\nCalibration interrupted by user")
            break
        except Exception as e:
            print(f"Error at {set_current}A: {e}")
    
    if results:
        # Export to CSV
        print(f"\nExporting {len(results)} data points to {filename}...")
        
        with open(filename, 'w') as f:
            # Write header
            f.write("set_current,adc_current,current_std,avg_voltage,voltage_std,")
            f.write("current_error_ma,current_error_percent,power,")
            f.write("i_readings,v_readings\n")
            
            # Write data
            for result in results:
                i_readings = ";".join(f"{r:.6f}" for r in result['current_readings'])
                v_readings = ";".join(f"{r:.6f}" for r in result['voltage_readings'])
                
                f.write(f"{result['set_current']:.6f},{result['adc_current']:.6f},{result['current_std']:.6f},")
                f.write(f"{result['avg_voltage']:.6f},{result['voltage_std']:.6f},")
                f.write(f"{result['current_error_ma']:.3f},{result['current_error_percent']:.4f},{result['power']:.3f},")
                f.write(f'"{i_readings}","{v_readings}"\n')
        
        print(f"Export complete: {filename}")
        
        # Safety reminder
        print("\n" + "="*60)
        print("SAFETY: Please disable the IT8511 electronic load now!")
        print("="*60)
    
    return results

def export_calibration_metadata(board_id=None, filename="calibration_metadata.json"):
    """Export calibration metadata and system information"""
    from calibration import Calibration
    import machine
    import ubinascii
    
    cal = Calibration()
    if board_id:
        cal.set_board_id(board_id)
    
    metadata = {
        'board_id': cal.get_board_id(),
        'hardware_id': cal.get_hardware_id(),
        'calibration_date': cal.get_calibration_date(),
        'system_info': {
            'unique_id': ubinascii.hexlify(machine.unique_id()).decode('ascii'),
            'freq': machine.freq(),
        },
        'bq25758_status': board.bq.get_status_str(),
        'calibration_summary': cal.get_calibration_summary(),
        'current_settings': {
            'output_voltage_limit': board.bq.get_output_voltage_limit(),
            'output_current_limit': board.bq.get_output_current_limit()
        }
    }
    
    with open(filename, 'w') as f:
        json.dump(metadata, f)
    
    print(f"Metadata exported to {filename}")
    return metadata

def run_comprehensive_calibration_export(board_id=None):
    """
    Run comprehensive calibration data export for PC analysis
    
    This function:
    1. Exports detailed voltage calibration data
    2. Prompts for current calibration with IT8511
    3. Exports system metadata
    4. Creates all files needed for PC analysis
    """
    print("=== Comprehensive Calibration Data Export ===")
    
    # Initialize hardware
    board.setup()
    
    # Export metadata
    export_calibration_metadata(board_id, "calibration_metadata.json")
    
    # Voltage calibration
    print("\n1. Starting detailed voltage calibration...")
    voltage_results = export_detailed_voltage_calibration("voltage_cal_data.csv")
    
    # Current calibration (optional)
    do_current = input("\n2. Perform detailed current calibration with IT8511? (y/n): ").lower().startswith('y')
    if do_current:
        current_results = export_detailed_current_calibration("current_cal_data.csv")
    
    print("\n=== Export Complete ===")
    print("Files created:")
    print("- calibration_metadata.json (system info)")
    print("- voltage_cal_data.csv (voltage calibration data)")
    if do_current:
        print("- current_cal_data.csv (current calibration data)")
    
    print("\nTransfer these files to PC for matplotlib analysis!")
    print("Use: mpremote fs cp :filename ./filename")

# Convenience functions
def quick_voltage_export(points=30):
    """Quick voltage calibration export with default settings"""
    return export_detailed_voltage_calibration("voltage_cal_data.csv", num_points=points)

def quick_current_export(points=15):
    """Quick current calibration export with default settings"""  
    return export_detailed_current_calibration("current_cal_data.csv", num_points=points)