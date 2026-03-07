# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
from machine import Pin, ADC, PWM, I2C, Timer
from BQ25758 import BQ25758
from calibration import Calibration
from display import display_convertor_info, display_blank

bq_sda = Pin(0)
bq_scl = Pin(1)
bq_int = Pin(2, Pin.IN)
bq_ce = Pin(3, Pin.OUT)

# LED on Pin(8), active-low. PWM: duty 0 = full on, 65535 = off.
_led_pwm = PWM(Pin(8, Pin.OUT), freq=100_000, duty_u16=65535)


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

bq = BQ25758(i2c_bus=bq_i2c, chip_enable_pin=bq_ce)

# Load calibration data
calibration = Calibration()

# RP2350 ADC scaling for the ideal diode switches
R35 = 97.6
R36 = 3.1
R37 = 2.1
ADC_SCALE = (3.3 / 65535) * (R35 + R36 + R37) / (R36 + R37)

def setup():
    _led_pwm.duty_u16(0)  # LED on during setup

    display_blank()

    # Display board identification
    print(f"=== BidirectionalSupply Board ===")
    print(f"Board ID: {calibration.get_board_id()}")
    print(f"Hardware ID: {calibration.get_hardware_id()}")
    if calibration.is_calibrated():
        print(f"Calibrated: {calibration.get_calibration_date()}")
    else:
        print("Calibrated: No calibration data")

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

class BoardContext(dict):
    '''Lazy-evaluated cache of board measurements and derived quantities.

    Values are computed on first access and cached for subsequent reads.
    Call clear() to invalidate the cache and force fresh ADC reads.

    IMPORTANT: Access values with context['key'], NOT context.get('key').
    dict.get() bypasses __missing__ and will return None instead of
    computing the value.
    '''
    def __getitem__(self, key):
        '''MicroPython's dict does not call __missing__, so we do it here.'''
        try:
            return super().__getitem__(key)
        except KeyError:
            return self.__missing__(key)

    def __missing__(self, key):
        '''Compute and cache a value on first access via context['key'].'''
        # Voltages
        if key == 'vin':
            v = calibration.calibrate_vin_adc(self['vin_raw'])
        elif key == 'vin_raw':
            v = bq.get_vin_adc()
        elif key == 'vout':
            v = calibration.calibrate_vout_adc(self['vout_raw'])
        elif key == 'vout_raw':
            v = bq.get_vout_adc()

        # Currents
        elif key == 'iin':
            v = calibration.calibrate_iin_adc(self['iin_raw'])
        elif key == 'iin_raw':
            v = bq.get_iin_adc()
        elif key == 'iout':
            v = calibration.calibrate_iout_adc(self['iout_raw'])
        elif key == 'iout_raw':
            v = bq.get_iout_adc()

        # Calculate power
        elif key == 'pin':
            v = self['vin'] * self['iin']
        elif key == 'pout':
            v = self['vout'] * self['iout']
        elif key == 'pin_raw':
            v = self['vin_raw'] * self['iin_raw']
        elif key == 'pout_raw':
            v = self['vout_raw'] * self['iout_raw']

        # Calculate efficiency
        elif key == 'efficiency':
            pin = self['pin']
            v = (self['pout'] / pin) * 100 if pin > 0.001 else 0.0

        # Illegal key for the context
        else:
            raise KeyError(key)

        # Update cache and return value
        self[key] = v
        return v

context = BoardContext()

poll_timer = Timer()

# Breathing LED state: triangle wave, 100 steps per half-cycle × 20ms = 4s full breath
_BREATH_STEPS = 100
_breath_step = 0
_breath_dir = 1

def _do_breath_step():
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

def _poll(t):
    _do_breath_step()

    if _breath_step % 10 == 0:
        context.clear()
        display_convertor_info(context)

def monitor(active=True):
    if active:
        poll_timer.init(mode=Timer.PERIODIC, period=20, callback=_poll)
    else:
        poll_timer.deinit()
        _led_pwm.duty_u16(65535)  # LED off

def get_switch_vsense_calibrated(switch_num):
    """Get calibrated ideal diode switch voltage sense reading"""
    raw = get_switch_vsense(switch_num)
    return calibration.calibrate_switch_vsense(raw)

def print_power_summary():
    """Print formatted power readings"""
    context.clear()
    print("=== Power Readings ===")
    print(f"Input:  {context['vin']:.3f}V  {context['iin']:.3f}A  {context['pin']:.3f}W")
    print(f"Output: {context['vout']:.3f}V  {context['iout']:.3f}A  {context['pout']:.3f}W")
    if context['efficiency'] > 0:
        print(f"Efficiency: {context['efficiency']:.1f}%")

    if calibration.is_calibrated():
        print(f"Using calibration for {calibration.get_board_id()}")
        print("Raw vs Calibrated comparison:")
        print(f"  Vin:  {context['vin_raw']:.3f}V -> {context['vin']:.3f}V")
        print(f"  Vout: {context['vout_raw']:.3f}V -> {context['vout']:.3f}V")
    else:
        print("No calibration applied (using raw ADC values)")

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
