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

class BoardContext:
    '''Lazy-evaluated cache of board measurements and derived quantities.

    Values are computed on first access via get() and cached for subsequent
    reads. Call clear() to invalidate the cache and force fresh ADC reads.
    Use set() to inject override values.
    '''

    def __init__(self):
        self._cache = {}

    def get(self, key):
        if key not in self._cache:
            self._cache[key] = self._compute(key)
        return self._cache[key]

    def set(self, key, value):
        if key == 'output_current_limit':
            bq.set_output_current_limit(value)
        elif key == 'output_voltage_limit':
            bq.set_output_voltage_limit(value)
        elif key == 'input_current_limit':
            bq.set_input_current_dpm_limit(value)
        elif key == 'input_voltage_limit':
            bq.set_input_voltage_dpm_limit(value)
        elif key == 'reverse_current_limit':
            bq.set_reverse_mode_input_current_limit(value)
        elif key == 'reverse_voltage_limit':
            bq.set_reverse_mode_input_voltage_limit(value)
        # Invalidate cache so next get() re-reads from hardware
        self._cache.pop(key, None)

    def clear(self):
        self._cache.clear()

    def _compute(self, key):
        # Voltages
        if key == 'vin':
            return calibration.calibrate_vin_adc(self.get('vin_raw'))
        elif key == 'vin_raw':
            return _ema.get('vin_raw', bq.get_vin_adc())
        elif key == 'vout':
            return calibration.calibrate_vout_adc(self.get('vout_raw'))
        elif key == 'vout_raw':
            return _ema.get('vout_raw', bq.get_vout_adc())

        # Currents
        elif key == 'iin':
            return calibration.calibrate_iin_adc(self.get('iin_raw'))
        elif key == 'iin_raw':
            return _ema.get('iin_raw', bq.get_iin_adc())
        elif key == 'iout':
            return calibration.calibrate_iout_adc(self.get('iout_raw'))
        elif key == 'iout_raw':
            return _ema.get('iout_raw', bq.get_iout_adc())

        # Power
        elif key == 'pin':
            return self.get('vin') * self.get('iin')
        elif key == 'pout':
            return self.get('vout') * self.get('iout')
        elif key == 'pin_raw':
            return self.get('vin_raw') * self.get('iin_raw')
        elif key == 'pout_raw':
            return self.get('vout_raw') * self.get('iout_raw')

        # Efficiency
        elif key == 'efficiency':
            pin = self.get('pin')
            return (self.get('pout') / pin) * 100 if pin > 0.001 else 0.0

        # BQ25758 limits
        elif key == 'output_current_limit':
            return bq.get_output_current_limit()
        elif key == 'output_voltage_limit':
            return bq.get_output_voltage_limit()
        elif key == 'input_current_limit':
            return bq.get_input_current_dpm_limit()
        elif key == 'input_voltage_limit':
            return bq.get_input_voltage_dpm_limit()
        elif key == 'reverse_current_limit':
            return bq.get_reverse_mode_input_current_limit()
        elif key == 'reverse_voltage_limit':
            return bq.get_reverse_mode_input_voltage_limit()

        else:
            raise KeyError(key)

context = BoardContext()

poll_timer = Timer()

# Breathing LED state: triangle wave, 100 steps per half-cycle × 20ms = 4s full breath
_BREATH_STEPS = 100
_breath_step = 0
_breath_dir = 1

# EMA filter for raw ADC readings, updated every poll tick (20ms).
# Alpha=0.3 gives ~3-4 sample effective window; lower = smoother, higher = more responsive.
_EMA_ALPHA = 0.095  # τ ≈ 200ms at 20ms tick; original 0.3 gave τ ≈ 56ms
_ema = {}

def _update_ema():
    for key, fn in (('vin_raw',  bq.get_vin_adc),
                    ('vout_raw', bq.get_vout_adc),
                    ('iin_raw',  bq.get_iin_adc),
                    ('iout_raw', bq.get_iout_adc)):
        raw = fn()
        _ema[key] = _EMA_ALPHA * raw + (1 - _EMA_ALPHA) * _ema.get(key, raw)

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
    _update_ema()
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

def print_power_summary():
    """Print formatted power readings"""
    context.clear()
    print("=== Power Readings ===")
    print(f"Input:  {context.get('vin'):.3f}V  {context.get('iin'):.3f}A  {context.get('pin'):.3f}W")
    print(f"Output: {context.get('vout'):.3f}V  {context.get('iout'):.3f}A  {context.get('pout'):.3f}W")
    if context.get('efficiency') > 0:
        print(f"Efficiency: {context.get('efficiency'):.1f}%")

    if calibration.is_calibrated():
        print(f"Using calibration for {calibration.get_board_id()}")
        print("Raw vs Calibrated comparison:")
        print(f"  Vin:  {context.get('vin_raw'):.3f}V -> {context.get('vin'):.3f}V")
        print(f"  Vout: {context.get('vout_raw'):.3f}V -> {context.get('vout'):.3f}V")
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
