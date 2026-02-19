# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
"""
Board calibration script for BidirectionalSupply

This script performs systematic calibration of ADC channels and generates
calibration constants that are saved to calibration.dat.

Features:
- Automatic voltage calibration (sweeps output voltage settings)
- Manual current calibration with IT8511 electronic load  
- Automatic board ID detection from RP2350 hardware
- Robust data protection with atomic writes and backups

Usage:
    import calibrate_board
    
    # Full calibration (voltage + current):
    calibrate_board.full_cal()
    
    # Voltage only (quick):
    calibrate_board.quick_cal() 
    
    # Current only (with IT8511 load):
    calibrate_board.calibrate_current_only()
    
    # Test current readings:
    calibrate_board.test_current_readings()

Future Automation:
    The IT8511 electronic load can be controlled via SCPI commands over USB/Serial.
    Future versions could automate current calibration by:
    1. Sending SCPI commands to set load currents
    2. Automatically stepping through test points
    3. Full hands-off calibration of all 10 boards
    
    Example SCPI commands for IT8511:
    - *IDN? (identify)
    - :INP ON (enable input)
    - :CURR 1.5 (set 1.5A load)
    - :MEAS:CURR? (read actual current)
"""

import board
import time
from calibration import Calibration

def calibrate_vout_adc(bq, test_voltages=None):
    """
    Calibrate output voltage ADC by sweeping through set voltages
    
    Returns: (gain, offset, rms_error_mv)
    """
    if test_voltages is None:
        test_voltages = [4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 18.0, 20.0]
    
    print("=== Output Voltage ADC Calibration ===")
    print("Set V    ADC V    Error mV")
    print("----------------------------")
    
    results = []
    for set_voltage in test_voltages:
        try:
            # Set the output voltage
            bq.set_output_voltage_limit(set_voltage)
            
            # Wait for settling
            time.sleep(1.5)
            
            # Read back the ADC value
            adc_voltage = bq.get_vout_adc()
            
            # Calculate error
            error_mv = (adc_voltage - set_voltage) * 1000
            
            print(f"{set_voltage:5.1f}   {adc_voltage:6.3f}   {error_mv:7.1f}")
            results.append((set_voltage, adc_voltage))
            
        except Exception as e:
            print(f"Error at {set_voltage}V: {e}")
    
    # Calculate linear regression
    if len(results) < 3:
        print("Not enough valid data points for calibration")
        return 1.0, 0.0, 999.9
    
    n = len(results)
    sum_x = sum(d[0] for d in results)  # set voltages
    sum_y = sum(d[1] for d in results)  # adc readings
    sum_xy = sum(d[0] * d[1] for d in results)
    sum_x2 = sum(d[0] ** 2 for d in results)
    
    # Linear regression: y = mx + b (ADC = gain * Set + offset)
    gain = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
    offset = (sum_y - gain * sum_x) / n
    
    # Calculate RMS error after correction
    rms_error_mv = 0
    for set_v, adc_v in results:
        corrected_v = (adc_v - offset) / gain
        error = (corrected_v - set_v) * 1000
        rms_error_mv += error ** 2
    rms_error_mv = (rms_error_mv / len(results)) ** 0.5
    
    print(f"\\nCalibration results:")
    print(f"  Gain: {gain:.6f}")
    print(f"  Offset: {offset:.6f} V")
    print(f"  RMS Error: {rms_error_mv:.1f} mV")
    
    return gain, offset, rms_error_mv

def calibrate_vin_adc(bq, external_voltmeter_readings=None):
    """
    Calibrate input voltage ADC
    
    If external_voltmeter_readings is provided as [(adc_reading, true_voltage), ...],
    performs calibration. Otherwise just reports current reading.
    
    Returns: (gain, offset, rms_error_mv)
    """
    print("\\n=== Input Voltage ADC Calibration ===")
    
    if external_voltmeter_readings is None:
        # Just report current reading - user needs external voltmeter
        vin_adc = bq.get_vin_adc()
        print(f"Current Vin ADC reading: {vin_adc:.3f} V")
        print("For calibration, measure input voltage with external voltmeter")
        print("and call: calibrate_vin_adc(bq, [(adc_reading, true_voltage), ...])")
        return 1.0, 0.0, 0.0
    
    print("ADC V    True V   Error mV")
    print("---------------------------")
    
    results = []
    for adc_reading, true_voltage in external_voltmeter_readings:
        error_mv = (adc_reading - true_voltage) * 1000
        print(f"{adc_reading:6.3f}   {true_voltage:6.3f}   {error_mv:7.1f}")
        results.append((true_voltage, adc_reading))
    
    if len(results) < 2:
        print("Need at least 2 data points for calibration")
        return 1.0, 0.0, 999.9
    
    # Calculate linear regression
    n = len(results)
    sum_x = sum(d[0] for d in results)  # true voltages
    sum_y = sum(d[1] for d in results)  # adc readings
    sum_xy = sum(d[0] * d[1] for d in results)
    sum_x2 = sum(d[0] ** 2 for d in results)
    
    gain = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
    offset = (sum_y - gain * sum_x) / n
    
    # Calculate RMS error
    rms_error_mv = 0
    for true_v, adc_v in results:
        corrected_v = (adc_v - offset) / gain
        error = (corrected_v - true_v) * 1000
        rms_error_mv += error ** 2
    rms_error_mv = (rms_error_mv / len(results)) ** 0.5
    
    print(f"\\nCalibration results:")
    print(f"  Gain: {gain:.6f}")
    print(f"  Offset: {offset:.6f} V") 
    print(f"  RMS Error: {rms_error_mv:.1f} mV")
    
    return gain, offset, rms_error_mv

def calibrate_iout_adc_with_load(bq, test_currents=None):
    """
    Calibrate output current ADC using IT8511 electronic load
    
    Args:
        bq: BQ25758 instance
        test_currents: List of currents to test (in Amps)
        
    Returns: (gain, offset, rms_error_ma)
    """
    if test_currents is None:
        test_currents = [0.1, 0.2, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    
    print("\\n=== Output Current ADC Calibration with IT8511 Load ===")
    print("This procedure requires manual operation of the IT8511 electronic load")
    print("The load should be connected to the converter output")
    print()
    
    # Set a stable output voltage for current testing
    test_voltage = 12.0
    bq.set_output_voltage_limit(test_voltage)
    print(f"Set output voltage to {test_voltage}V for current testing")
    print()
    
    print("Instructions:")
    print("1. For each test current, set the IT8511 to that current")  
    print("2. Wait for readings to stabilize")
    print("3. Press Enter when ready to take the measurement")
    print()
    print("Set Current (A)  |  ADC Reading (A)  |  Error (mA)")
    print("-" * 50)
    
    results = []
    for set_current in test_currents:
        try:
            # Prompt user to set the load
            input(f"Set IT8511 to {set_current:.1f}A, then press Enter...")
            
            # Wait a moment for stabilization
            import time
            time.sleep(2.0)
            
            # Read the ADC value
            adc_current = abs(bq.get_iout_adc())  # Use abs() since current direction varies
            
            # Calculate error
            error_ma = (adc_current - set_current) * 1000
            
            print(f"{set_current:11.1f}    |  {adc_current:13.3f}    |  {error_ma:9.1f}")
            results.append((set_current, adc_current))
            
        except KeyboardInterrupt:
            print("\\nCalibration interrupted by user")
            break
        except Exception as e:
            print(f"Error at {set_current}A: {e}")
    
    if len(results) < 3:
        print("Not enough data points for calibration")
        return 1.0, 0.0, 999.9
    
    # Calculate linear regression
    n = len(results)
    sum_x = sum(d[0] for d in results)  # set currents
    sum_y = sum(d[1] for d in results)  # adc readings
    sum_xy = sum(d[0] * d[1] for d in results)
    sum_x2 = sum(d[0] ** 2 for d in results)
    
    # Linear regression: y = mx + b (ADC = gain * Set + offset)
    gain = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
    offset = (sum_y - gain * sum_x) / n
    
    # Calculate RMS error after correction
    rms_error_ma = 0
    for set_i, adc_i in results:
        corrected_i = (adc_i - offset) / gain
        error = (corrected_i - set_i) * 1000
        rms_error_ma += error ** 2
    rms_error_ma = (rms_error_ma / len(results)) ** 0.5
    
    print(f"\\nOutput Current Calibration Results:")
    print(f"  Gain: {gain:.6f}")
    print(f"  Offset: {offset:.6f} A")
    print(f"  RMS Error: {rms_error_ma:.1f} mA")
    
    # Safety prompt to remove load
    print("\\n" + "="*60)
    print("SAFETY: Please disable or disconnect the IT8511 electronic load now!")
    print("The load is currently dissipating significant power.")
    print("Set IT8511 current to 0A or turn off the load input.")
    print("="*60)
    input("Press Enter after disabling the load...")
    
    return gain, offset, rms_error_ma

def calibrate_iin_adc_manual(bq):
    """
    Manual input current ADC calibration
    
    Returns: (gain, offset, rms_error_ma)
    """
    print("\\n=== Input Current ADC Calibration ===")
    print("Input current calibration requires external current measurement")
    print("This can be done by:")
    print("1. Using a calibrated ammeter in series with input")
    print("2. Or calculating from known power values")
    print()
    
    # For now, just return defaults - this is harder to calibrate
    iin = bq.get_iin_adc()
    print(f"Current input current reading: {iin:.3f} A")
    print("Input current calibration not implemented yet")
    print("Consider using: P_in = V_in * I_in and P_out = V_out * I_out")
    print("Then: I_in = P_out / (V_in * efficiency)")
    
    return 1.0, 0.0, 0.0

def calibrate_current_adcs(bq, use_load=False):
    """
    Calibrate current ADCs
    
    Args:
        bq: BQ25758 instance  
        use_load: If True, use IT8511 load for output current calibration
        
    Returns: ((iin_gain, iin_offset, iin_rms_ma), (iout_gain, iout_offset, iout_rms_ma))
    """
    print("\\n=== Current ADC Calibration ===")
    
    if use_load:
        # Use IT8511 for output current calibration
        iout_gain, iout_offset, iout_rms = calibrate_iout_adc_with_load(bq)
    else:
        print("Output current calibration skipped (use_load=False)")
        iout_gain, iout_offset, iout_rms = 1.0, 0.0, 0.0
    
    # Input current calibration (manual for now)
    iin_gain, iin_offset, iin_rms = calibrate_iin_adc_manual(bq)
    
    return (iin_gain, iin_offset, iin_rms), (iout_gain, iout_offset, iout_rms)

def run_vout_calibration_only(board_id=None):
    """Run only output voltage calibration - useful for quick testing"""
    # Initialize hardware
    board.setup()
    
    # Load existing calibration
    cal = Calibration()
    
    # Set board ID (auto-detect if None)
    cal.set_board_id(board_id)
    actual_board_id = cal.get_board_id()
    
    print(f"=== Calibrating Board: {actual_board_id} (Vout only) ===")
    print(f"Hardware ID: {cal.get_hardware_id()}")
    
    # Calibrate output voltage ADC
    gain, offset, rms_error = calibrate_vout_adc(board.bq)
    cal.set_vout_calibration(gain, offset, rms_error)
    
    # Set calibration date
    import time
    # Note: RTC time if available, otherwise use simple counter
    try:
        import rtc
        now = rtc.datetime()
        date_str = f"{now[0]}-{now[1]:02d}-{now[2]:02d}"
    except:
        date_str = f"session_{time.ticks_ms()}"
    
    cal.set_calibration_date(date_str)
    
    # Save calibration
    cal.save()
    
    print("\\n=== Calibration Summary ===")
    print(cal.get_calibration_summary())
    
    return cal

def run_full_calibration(board_id=None, external_vin_data=None):
    """
    Run complete board calibration sequence
    
    Args:
        board_id: Unique identifier for this board (None = auto-detect from hardware)
        external_vin_data: Optional list of (adc_reading, true_voltage) for Vin calibration
    """
    # Initialize hardware  
    board.setup()
    
    # Create calibration object
    cal = Calibration()
    cal.set_board_id(board_id)
    actual_board_id = cal.get_board_id()
    
    print(f"=== Full Calibration for Board: {actual_board_id} ===")
    print(f"Hardware ID: {cal.get_hardware_id()}")
    
    # 1. Calibrate output voltage ADC
    print("\\n1. Output Voltage ADC Calibration")
    vout_gain, vout_offset, vout_rms = calibrate_vout_adc(board.bq)
    cal.set_vout_calibration(vout_gain, vout_offset, vout_rms)
    
    # 2. Calibrate input voltage ADC  
    print("\\n2. Input Voltage ADC Calibration")
    vin_gain, vin_offset, vin_rms = calibrate_vin_adc(board.bq, external_vin_data)
    cal.set_vin_calibration(vin_gain, vin_offset, vin_rms)
    
    # 3. Calibrate current ADCs
    print("\\n3. Current ADC Calibration") 
    use_electronic_load = input("Do you have IT8511 electronic load connected? (y/n): ").lower().startswith('y')
    (iin_gain, iin_offset, iin_rms), (iout_gain, iout_offset, iout_rms) = calibrate_current_adcs(board.bq, use_load=use_electronic_load)
    cal.set_iin_calibration(iin_gain, iin_offset, iin_rms)
    cal.set_iout_calibration(iout_gain, iout_offset, iout_rms)
    
    # 4. Set calibration date
    import time
    try:
        import rtc  
        now = rtc.datetime()
        date_str = f"{now[0]}-{now[1]:02d}-{now[2]:02d}"
    except:
        date_str = f"session_{time.ticks_ms()}"
        
    cal.set_calibration_date(date_str)
    
    # 5. Save calibration
    cal.save()
    
    print("\\n=== Final Calibration Summary ===")
    print(cal.get_calibration_summary())
    
    return cal

def test_calibration():
    """Test the calibration by comparing raw vs calibrated readings"""
    print("\\n=== Testing Calibration ===")
    
    cal = Calibration()
    
    if not cal.is_calibrated():
        print("No calibration data found. Run calibration first.")
        return
    
    print(f"Testing calibration for {cal.get_board_id()}")
    
    # Test readings
    raw_vout = board.bq.get_vout_adc()
    cal_vout = cal.calibrate_vout_adc(raw_vout) 
    set_vout = board.bq.get_output_voltage_limit()
    
    raw_vin = board.bq.get_vin_adc()
    cal_vin = cal.calibrate_vin_adc(raw_vin)
    
    print(f"\\nOutput Voltage:")
    print(f"  Set:        {set_vout:.3f} V")
    print(f"  Raw ADC:    {raw_vout:.3f} V  (error: {(raw_vout-set_vout)*1000:.1f} mV)")
    print(f"  Calibrated: {cal_vout:.3f} V  (error: {(cal_vout-set_vout)*1000:.1f} mV)")
    
    print(f"\\nInput Voltage:")
    print(f"  Raw ADC:    {raw_vin:.3f} V")
    print(f"  Calibrated: {cal_vin:.3f} V")

# Example usage functions
def quick_cal(board_id=None):
    """Quick calibration - just output voltage (auto-detects board ID if None)"""
    return run_vout_calibration_only(board_id)

def full_cal(board_id=None):  
    """Full calibration - all channels (auto-detects board ID if None)"""
    return run_full_calibration(board_id)

def calibrate_current_only(board_id=None):
    """Run only current calibration with IT8511 load"""
    # Initialize hardware
    board.setup()
    
    # Load existing calibration
    cal = Calibration()
    cal.set_board_id(board_id)
    actual_board_id = cal.get_board_id()
    
    print(f"=== Current Calibration for Board: {actual_board_id} ===")
    print(f"Hardware ID: {cal.get_hardware_id()}")
    
    # Calibrate current ADCs with IT8511 load
    (iin_gain, iin_offset, iin_rms), (iout_gain, iout_offset, iout_rms) = calibrate_current_adcs(board.bq, use_load=True)
    cal.set_iin_calibration(iin_gain, iin_offset, iin_rms)
    cal.set_iout_calibration(iout_gain, iout_offset, iout_rms)
    
    # Set calibration date  
    import time
    try:
        import rtc
        now = rtc.datetime()
        date_str = f"{now[0]}-{now[1]:02d}-{now[2]:02d}"
    except:
        date_str = f"session_{time.ticks_ms()}"
        
    cal.set_calibration_date(date_str + "_current")
    
    # Save calibration
    cal.save()
    
    print("\\n=== Current Calibration Complete ===")
    print(cal.get_calibration_summary())
    
    # Final safety check
    print("\\n" + "="*60)
    print("REMINDER: Ensure IT8511 electronic load is disabled!")
    print("Check that the load current is set to 0A or input is OFF.")
    print("="*60)
    
    return cal

def test_current_readings():
    """Test current readings with current load conditions"""
    print("\\n=== Current Readings Test ===")
    print("Connect IT8511 load and set to desired current, then press Enter...")
    print("WARNING: High currents will dissipate significant power!")
    input()
    
    import board
    import time
    
    # Take several readings to show stability
    print("Taking 5 readings over 10 seconds:")
    print("Time(s)  Raw Iout(A)  Cal Iout(A)  Raw Iin(A)   Cal Iin(A)")
    print("-" * 60)
    
    start_time = time.ticks_ms()
    for i in range(5):
        current_time = time.ticks_diff(time.ticks_ms(), start_time) / 1000.0
        
        raw_iout = board.bq.get_iout_adc()
        cal_iout = board.get_iout_calibrated()
        raw_iin = board.bq.get_iin_adc()  
        cal_iin = board.get_iin_calibrated()
        
        print(f"{current_time:6.1f}   {raw_iout:9.3f}   {cal_iout:9.3f}   {raw_iin:9.3f}   {cal_iin:9.3f}")
        
        if i < 4:  # Don't sleep after last reading
            time.sleep(2.0)
    
    # Calculate power
    readings = board.get_power_readings()
    print(f"\\nPower Analysis:")
    print(f"  Input Power (calibrated):  {readings['pin_cal']:.3f} W")
    print(f"  Output Power (calibrated): {readings['pout_cal']:.3f} W")
    if readings['efficiency'] > 0:
        print(f"  Efficiency: {readings['efficiency']:.1f}%")
    
    # Power dissipation warning
    if readings['pout_cal'] > 20.0:
        print(f"\\nWARNING: High power dissipation ({readings['pout_cal']:.1f}W)!")
        print("Consider reducing load current to prevent overheating.")
    
    print("\\nRemember to disable IT8511 load when finished testing!")

def get_board_info():
    """Show board identification information"""
    from calibration import Calibration
    cal = Calibration()
    print(f"Board ID: {cal.get_board_id()}")
    print(f"Hardware ID: {cal.get_hardware_id()}")
    print(f"Calibration Status: {'Calibrated' if cal.is_calibrated() else 'Not calibrated'}")
    return cal.get_hardware_id()