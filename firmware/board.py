# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
from machine import Pin, ADC, PWM, I2C, Timer
from BQ25758 import BQ25758
from calibration import Calibration
from display import display_convertor_info, display_blank, display_error

bq_sda = Pin(0)
bq_scl = Pin(1)
bq_int = Pin(2, Pin.IN)

# Inverted logic on this pin. Want output to stay high until explicitly enabled
bq_ce = Pin(3, Pin.OUT, True)

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

def _bq_connect():
    '''Initialise the BQ25758 and enable its ADC.

    Called on first boot and again whenever the chip loses power and
    is_detected() returns False. bq.setup() issues REG_RST which clears
    all BQ25758 registers, so load_startup() must be called afterwards
    to restore any saved limits.
    '''
    bq.setup()
    bq.setup_adc()

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

    _bq_connect()

    print("Initialised BQ25758")

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

_die_temp_adc = ADC(4)  # RP2350 internal temperature sensor

def get_die_temp():
    '''Return RP2350 die temperature in Celsius.
    Uses the internal ADC channel 4 and conversion constants from the
    RP2350 datasheet. Accuracy is typically ±a few degrees.
    '''
    reading = _die_temp_adc.read_u16() * 3.3 / 65535
    return 27 - (reading - 0.706) / 0.001721

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
        if key == 'switch0':
            set_switch(0, value != 0)
        elif key == 'switch1':
            set_switch(1, value != 0)
        elif key == 'switch2':
            set_switch(2, value != 0)
        elif key == 'switch3':
            set_switch(3, value != 0)
        elif key == 'enabled':
            bq.set_enabled(value != 0)
        elif key == 'output_current_limit':
            bq.set_output_current_limit(value)
        elif key == 'output_voltage_limit':
            bq.set_output_voltage_limit(value)
        elif key == 'input_current_limit':
            bq.set_input_current_dpm_limit(value)
        elif key == 'input_voltage_limit':
            bq.set_input_voltage_dpm_limit(value)
        elif key == 'reverse_current':
            bq.set_reverse_current(value)
        elif key == 'reverse_voltage':
            bq.set_reverse_voltage(value)
        elif key == 'forward_enable':
            bq.set_forward_enable(value != 0)
        elif key == 'reverse_enable':
            bq.set_reverse_enable(value != 0)
        elif key == 'auto_reverse':
            bq.set_auto_reverse(value != 0)
        elif key == 'watchdog_timeout':
            bq.set_watchdog_timeout(value)
        elif key == 'ups_restore_margin':
            global _ups_restore_margin
            _ups_restore_margin = float(value)
        elif key == 'ups_restore_delay':
            global _ups_restore_ticks
            # delay in seconds; checked every 200ms (every 10th breath step)
            _ups_restore_ticks = max(1, int(float(value) / 0.2))
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

        # Enabled state of DC/DC convertor
        elif key == 'enabled':
            return bq.is_enabled()
        elif key == 'regulation_mode':
            return bq.output_regulation_mode()
        elif key == 'charger_state':
            return _charger.state_name if _charger is not None else ''
        elif key == 'soc':
            return _charger.get_soc_str() if _charger is not None else ''

        # Ideal diode switch state and voltage sense
        elif key == 'switch0':
            return get_switch(0)
        elif key == 'switch1':
            return get_switch(1)
        elif key == 'switch2':
            return get_switch(2)
        elif key == 'switch3':
            return get_switch(3)
        elif key == 'switch_vsense0':
            return get_switch_vsense(0)
        elif key == 'switch_vsense1':
            return get_switch_vsense(1)
        elif key == 'switch_vsense2':
            return get_switch_vsense(2)
        elif key == 'switch_vsense3':
            return get_switch_vsense(3)

        # Temperature
        elif key == 'die_temp':
            return get_die_temp()
        elif key == 'ts_celsius':
            return bq.get_ts_celsius()
        elif key == 'ts_adc':
            return bq.get_ts_adc()

        # BQ25758 limits
        elif key == 'output_current_limit':
            return bq.get_output_current_limit()
        elif key == 'output_voltage_limit':
            return bq.get_output_voltage_limit()
        elif key == 'input_current_limit':
            return bq.get_input_current_dpm_limit()
        elif key == 'input_voltage_limit':
            return bq.get_input_voltage_dpm_limit()
        elif key == 'reverse_current':
            return bq.get_reverse_current()
        elif key == 'reverse_voltage':
            return bq.get_reverse_voltage()
        elif key == 'forward_enable':
            return bq.get_forward_enable()
        elif key == 'reverse_enable':
            return bq.get_reverse_enable()
        elif key == 'auto_reverse':
            return bq.get_auto_reverse()
        elif key == 'watchdog_timeout':
            return bq.get_watchdog_timeout()
        elif key == 'ups_restore_margin':
            return _ups_restore_margin
        elif key == 'ups_restore_delay':
            return _ups_restore_ticks * 0.2
        else:
            raise KeyError(key)

context = BoardContext()

_charger = None

# UPS power restoration monitor: when in reverse mode, detects external power
# returning by comparing VIN against the regulated reverse_voltage setpoint.
# The converter cannot drive VIN above its own setpoint, so VIN > reverse_voltage
# × (1 + margin) means external supply is present and overriding the converter.
# Checked every 200ms alongside the display refresh (no extra I2C overhead).
#
# startup.dat keys:
#   ups_restore_margin=0.05    fraction above reverse_voltage to confirm restoration
#   ups_restore_delay=2.0      seconds VIN must remain above threshold before switching back
_ups_restore_margin = 0.0   # 0 = disabled
_ups_restore_ticks = 10     # default 2s (10 × 200ms)
_ups_restore_count = 0

def _ups_recovery_check(ctx):
    global _ups_restore_count
    if _ups_restore_margin <= 0.0:
        return
    if not ctx.get('reverse_enable'):
        _ups_restore_count = 0
        return
    threshold = ctx.get('reverse_voltage') * (1.0 + _ups_restore_margin)
    if ctx.get('vin') > threshold:
        _ups_restore_count += 1
        if _ups_restore_count >= _ups_restore_ticks:
            _ups_restore_count = 0
            ctx.set('reverse_enable', 0)
            print('UPS: VIN {:.2f}V > {:.2f}V, power restored'.format(
                ctx.get('vin'), threshold))
            if _charger is not None:
                _charger.start(ctx)
    else:
        _ups_restore_count = 0

def set_charger(c):
    '''Register and start a BatteryCharger, or stop and remove the current one.

    set_charger(c)    — stops any existing charger, starts c, registers it.
    set_charger(None) — stops the current charger and removes it.
    '''
    global _charger
    if _charger is not None:
        _charger.stop(context)
    _charger = c
    if c is not None:
        c.start(context)

poll_timer = Timer()

# Breathing LED state: triangle wave, 100 steps per half-cycle × 20ms = 4s full breath
_BREATH_STEPS = 100
_breath_step = 0
_breath_dir = 1

# EMA filter for raw ADC readings, updated every poll tick (20ms).
# Alpha=0.3 gives ~3-4 sample effective window; lower = smoother, higher = more responsive.
_EMA_ALPHA = 0.2  # τ ≈ 90ms at 20ms polling interval. original 0.3 gave τ ≈ 56ms
_ema = {}

def _update_ema():
    for key, fn in (('vin_raw',  bq.get_vin_adc),
                    ('vout_raw', bq.get_vout_adc),
                    ('iin_raw',  bq.get_iin_adc),
                    ('iout_raw', bq.get_iout_adc)):
        raw = fn()
        if raw == 0.0:
            _ema[key] = 0.0
        else:
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
    _do_breath_step()

    # If the BQ25758 lost power (e.g. no Vin/Vout while USB powers the RP2350),
    # keep retrying until it comes back. bq.setup() issues REG_RST so all
    # registers are cleared; load_startup() restores saved limits afterwards.
    if not bq.is_detected():
        try:
            _bq_connect()
        except OSError:
            display_error("DC/DC Convertor Off")
            return
        load_startup()
        if _charger is not None:
            _charger.start(context)

    _update_ema()

    if _breath_step % 10 == 0:
        context.clear()
        display_convertor_info(context)
        _ups_recovery_check(context)

    # Drive charger state machine at ~1 Hz (every 50 × 20 ms ticks)
    if _charger is not None and _breath_step % 50 == 0:
        _charger.update(context)

def monitor(active=True):
    if active:
        poll_timer.init(mode=Timer.PERIODIC, period=20, callback=_poll)
    else:
        poll_timer.deinit()
        _led_pwm.duty_u16(65535)  # LED off
        display_blank()

def load_startup(filename='startup.dat'):
    '''Load initial hardware settings from a startup.dat file.

    Each line should be in name=value format. Lines beginning with # are
    treated as comments and ignored. Values are passed to context.set() so
    settable quantities (e.g. output_voltage_limit) are written to hardware.

    Example startup.dat:
        # Set output voltage and current limits on boot
        output_voltage_limit=12.0
        output_current_limit=5.0
    '''
    try:
        with open(filename, 'r') as f:
            lines = f.read().splitlines()
    except OSError:
        return  # No startup file — normal operation

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            print(f'startup.dat: ignored invalid line: {line}')
            continue
        name, _, value_str = line.partition('=')
        name = name.strip()
        value_str = value_str.strip()
        try:
            value = float(value_str)
        except ValueError:
            print(f'startup.dat: ignored non-numeric value: {line}')
            continue
        try:
            context.set(name, value)
            print(f'startup.dat: {name} = {value}')
        except Exception as e:
            print(f'startup.dat: failed to set {name}: {e}')


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
