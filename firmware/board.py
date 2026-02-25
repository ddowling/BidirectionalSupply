# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
from machine import Pin, ADC, PWM, I2C, Timer
from BQ25758 import BQ25758
from calibration import Calibration

bq_sda = Pin(0)
bq_scl = Pin(1)
bq_int = Pin(2, Pin.IN)
bq_ce = Pin(3, Pin.OUT)

# AUX header
aux_spi_rx = Pin(4)
aux_spi_cs = Pin(5)
aux_spi_sck = Pin(6)
aux_spi_tx = Pin(7)
aux_sda = Pin(10)
aux_scl = Pin(11)

# LED on Pin(8), active-low. PWM: duty 0 = full on, 65535 = off.
_led_pwm = PWM(Pin(8, Pin.OUT), freq=1000, duty_u16=65535)

# Ideal Diode switches
sw0_en = Pin(12, Pin.OUT)
sw1_en = Pin(13, Pin.OUT)
sw2_en = Pin(14, Pin.OUT)
sw3_en = Pin(15, Pin.OUT)
sw0_vsense = ADC(Pin(26))
sw1_vsense = ADC(Pin(27))
sw2_vsense = ADC(Pin(28))
sw3_vsense = ADC(Pin(29))

bq_i2c = I2C(0, sda=bq_sda, scl=bq_scl)
aux_i2c = I2C(1, sda=aux_sda, scl=aux_scl)

bq = BQ25758(i2c_bus=bq_i2c, chip_enable_pin=bq_ce)

# Load calibration data
calibration = Calibration()

# ADC scaling
R35 = 97.6
R36 = 3.1
R37 = 2.1
ADC_SCALE = (3.3 / 65535) * (R35 + R36 + R37) / (R36 + R37)

def setup():
    _led_pwm.duty_u16(0)  # LED on during setup
    
    # Display board identification
    print(f"=== BidirectionalSupply Board ===")
    print(f"Board ID: {calibration.get_board_id()}")
    print(f"Hardware ID: {calibration.get_hardware_id()}")
    if calibration.is_calibrated():
        print(f"Calibrated: {calibration.get_calibration_date()}")
    else:
        print("Calibrated: No calibration data")
    print()

    # Look for devices on the bq_i2c bus
    devices = bq_i2c.scan()

    print(f"Found {len(devices)} devices on bq_i2c bus")
    if len(devices) == 0:
        raise RuntimeError("No I2C devices on convertor bus")

    for d in devices:
        print(f"Device at address {d:02x}")

    # Will throw an exception if setup fails
    bq.setup()

    print("Initialised BQ25758")

    bq.setup_adc()

    # Look for devices on the aux_i2c bus
    devices = aux_i2c.scan()

    print(f"Found {len(devices)} devices on aux_i2c bus")
    for d in devices:
        print(f"Device at address {d:02x}")

    _led_pwm.duty_u16(65535)  # LED off after setup

def _switch_to_enable_pin(switch_num):
    if switch_num == 0:
        return sw0_en
    elif switch_num == 1:
        return sw1_en
    elif switch_num == 2:
        return sw2_en
    elif switch_num == 3:
        return sw3_en
    else:
        raise ValueError("Bad switch_num")

def _switch_to_adc(switch_num):
    if switch_num == 0:
        return sw0_vsense
    elif switch_num == 1:
        return sw1_vsense
    elif switch_num == 2:
        return sw2_vsense
    elif switch_num == 3:
        return sw3_vsense
    else:
        raise ValueError("Bad switch_num")

def set_switch(switch_num, state):
    p = _switch_to_enable_pin(switch_num)
    p.value(state)

def get_switch(switch_num):
    p = _switch_to_enable_pin(switch_num)
    return p.value()

def get_switch_vsense(switch_num):
    adc = _switch_to_adc(switch_num)
    raw = adc.read_u16()
    return raw * ADC_SCALE

poll_timer = Timer()

# Breathing LED state: triangle wave, 100 steps per half-cycle × 20ms = 4s full breath
_BREATH_STEPS = 100
_breath_step = 0
_breath_dir = 1

def _breath_poll(t):
    global _breath_step, _breath_dir
    # Gamma-correct for perceptual linearity (gamma=2)
    frac = _breath_step / _BREATH_STEPS
    duty = 65535 - int((frac * frac) * 65535)  # active-low: 0=full on, 65535=off
    _led_pwm.duty_u16(duty)
    _breath_step += _breath_dir
    if _breath_step >= _BREATH_STEPS:
        _breath_dir = -1
    elif _breath_step <= 0:
        _breath_dir = 1

def monitor(active=True):
    if active:
        poll_timer.init(mode=Timer.PERIODIC, period=20, callback=_breath_poll)
    else:
        poll_timer.deinit()
        _led_pwm.duty_u16(65535)  # LED off

# Calibrated ADC reading functions
def get_vout_calibrated():
    """Get calibrated output voltage reading"""
    raw = bq.get_vout_adc()
    return calibration.calibrate_vout_adc(raw)

def get_vin_calibrated():
    """Get calibrated input voltage reading"""
    raw = bq.get_vin_adc()
    return calibration.calibrate_vin_adc(raw)

def get_iout_calibrated():
    """Get calibrated output current reading"""
    raw = bq.get_iout_adc()
    return calibration.calibrate_iout_adc(raw)

def get_iin_calibrated():
    """Get calibrated input current reading"""
    raw = bq.get_iin_adc()
    return calibration.calibrate_iin_adc(raw)

def get_switch_vsense_calibrated(switch_num):
    """Get calibrated ideal diode switch voltage sense reading"""
    raw = get_switch_vsense(switch_num)
    return calibration.calibrate_switch_vsense(raw)

def get_power_readings():
    """Get comprehensive power readings with calibration"""
    readings = {
        'vin_raw': bq.get_vin_adc(),
        'vout_raw': bq.get_vout_adc(), 
        'iin_raw': bq.get_iin_adc(),
        'iout_raw': bq.get_iout_adc(),
        'vin_cal': get_vin_calibrated(),
        'vout_cal': get_vout_calibrated(),
        'iin_cal': get_iin_calibrated(), 
        'iout_cal': get_iout_calibrated()
    }
    
    # Calculate power
    readings['pin_raw'] = readings['vin_raw'] * abs(readings['iin_raw'])
    readings['pout_raw'] = readings['vout_raw'] * abs(readings['iout_raw'])
    readings['pin_cal'] = readings['vin_cal'] * abs(readings['iin_cal'])
    readings['pout_cal'] = readings['vout_cal'] * abs(readings['iout_cal'])
    
    # Calculate efficiency
    if readings['pin_cal'] > 0.001:
        readings['efficiency'] = (readings['pout_cal'] / readings['pin_cal']) * 100
    else:
        readings['efficiency'] = 0.0
        
    return readings

def print_power_summary():
    """Print formatted power readings"""
    readings = get_power_readings()
    
    print("=== Power Readings ===")
    print(f"Input:  {readings['vin_cal']:.3f}V  {readings['iin_cal']:.3f}A  {readings['pin_cal']:.3f}W")
    print(f"Output: {readings['vout_cal']:.3f}V  {readings['iout_cal']:.3f}A  {readings['pout_cal']:.3f}W") 
    if readings['efficiency'] > 0:
        print(f"Efficiency: {readings['efficiency']:.1f}%")
    
    if calibration.is_calibrated():
        print(f"\\nUsing calibration for {calibration.get_board_id()}")
        print("Raw vs Calibrated comparison:")
        print(f"  Vin:  {readings['vin_raw']:.3f}V -> {readings['vin_cal']:.3f}V")
        print(f"  Vout: {readings['vout_raw']:.3f}V -> {readings['vout_cal']:.3f}V")
    else:
        print("\\nNo calibration applied (using raw ADC values)")

def get_calibration_info():
    """Get calibration status and summary"""
    if calibration.is_calibrated():
        print(calibration.get_calibration_summary())
    else:
        print("No calibration data found")
        print("Run: import calibrate_board; calibrate_board.quick_cal('board_id')")
        
def reload_calibration():
    """Reload calibration data from file"""
    global calibration
    calibration = Calibration()
    print("Calibration data reloaded")

def diagnose_calibration():
    """Diagnose calibration file issues"""
    calibration.diagnose_files()
    
def repair_calibration():
    """Attempt to repair calibration from backup"""
    return calibration.repair_from_backup()
