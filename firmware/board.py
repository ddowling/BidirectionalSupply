import machine
import BQ25758

bq_sda = machine.Pin(0)
bq_scl = machine.Pin(1)
bq_int = machine.Pin(2, machine.Pin.IN)
bq_ce = machine.Pin(3, machine.Pin.OUT)

# AUX header
aux_spi_rx = machine.Pin(4)
aux_spi_cs = machine.Pin(5)
aux_spi_sck = machine.Pin(6)
aux_spi_tx = machine.Pin(7)
aux_sda = machine.Pin(10)
aux_scl = machine.Pin(11)

# Invert led levels sol led.on() and led.off() work as expected
led = machine.Signal(machine.Pin(8, machine.Pin.OUT), invert=True)

# Ideal Diode switches
sw0_en = machine.Pin(12, machine.Pin.OUT)
sw1_en = machine.Pin(13, machine.Pin.OUT)
sw2_en = machine.Pin(14, machine.Pin.OUT)
sw3_en = machine.Pin(15, machine.Pin.OUT)
sw0_vsense = machine.ADC(machine.Pin(26))
sw1_vsense = machine.ADC(machine.Pin(27))
sw2_vsense = machine.ADC(machine.Pin(28))
sw3_vsense = machine.ADC(machine.Pin(29))

bq_i2c = machine.I2C(0, sda=bq_sda, scl=bq_scl)
aux_i2c = machine.I2C(1, sda=aux_sda, scl=aux_scl)

bq = BQ25758.BQ25758(i2c_bus=bq_i2c, chip_enable_pin=bq_ce)

# ADC scaling
R35 = 97.6
R36 = 3.1
R37 = 2.1
ADC_SCALE = (3.3 / 65535) * (R35 + R36 + R37) / (R36 + R37)

def setup():
    led.on()

    # Look for devices on the bq_i2c bus
    devices = bq_i2c.scan()

    print(f"Found {len(devices)} devices on bq_i2c bus")
    if len(devices) == 0:
        raise RuntimeError("No I2C devices")

    for d in devices:
        print(f"Device at address {d:02x}")

    res = bq.setup()
    print(f"bq.setup() returned {res}")

    # Look for devices on the aux_i2c bus
    devices = aux_i2c.scan()

    print(f"Found {len(devices)} devices on aux_i2c bus")
    for d in devices:
        print(f"Device at address {d:02x}")

    led.off()

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
