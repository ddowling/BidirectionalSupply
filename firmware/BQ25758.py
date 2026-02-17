from micropython import const

REG0x02_Output_Current_Limit=const(0x02) # Output Current Limit
REG0x04_Output_Voltage_Limit=const(0x04) # Output Voltage Limit
REG0x06_Input_Current_DPM_Limit=const(0x06) # Input Current DPM Limit
REG0x08_Input_Voltage_DPM_Limit=const(0x08) # Input Voltage DPM Limit
REG0x0A_Reverse_Mode_Input_Current_Limit=const(0x0a) # Reverse Mode Input Current Limit
REG0x0C_Reverse_Mode_Input_Voltage_Limit=const(0x0c) # Reverse Mode Input Voltage Limit
REG0x15_Timer_Control=const(0x15) # Timer Control
REG0x17_Converter_Control=const(0x17) # Converter Control
REG0x18_Pin_Control=const(0x18) # Pin Control
REG0x19_Power_Path_and_Reverse_Mode_Control=const(0x19) # Power Path and Reverse Mode Control
REG0x1B_TS_Threshold_Control=const(0x1b) # TS Threshold Control
REG0x1C_TS_Region_Behavior_Control=const(0x1c) # TS Region Behavior Control
REG0x1D_TS_Reverse_Mode_Threshold_Control=const(0x1d) # TS Reverse Mode Threshold Control
REG0x1E_Bypass_and_Overload_Control=const(0x1e) # Bypass and Overload Control
REG0x21_Status_1=const(0x21) # Status 1
REG0x22_Status_2=const(0x22) # Status 2
REG0x23_Status_3=const(0x23) # Status 3
REG0x24_Fault_Status=const(0x24) # Fault Status
REG0x25_Flag_1=const(0x25) # Flag 1
REG0x26_Flag_2=const(0x26) # Flag 2
REG0x27_Fault_Flag=const(0x27) # Fault Flag
REG0x28_Mask_1=const(0x28) # Mask 1
REG0x29_Mask_2=const(0x29) # Mask 2
REG0x2A_Fault_Mask=const(0x2a) # Fault Mask
REG0x2B_ADC_Control=const(0x2b) # ADC Control
REG0x2C_ADC_Channel_Control=const(0x2c) # ADC Channel Control
REG0x2D_IAC_ADC=const(0x2d) # IAC ADC
REG0x2F_IOUT_ADC=const(0x2f) # IOUT ADC
REG0x31_VAC_ADC=const(0x31) # VAC ADC
REG0x33_VOUT_ADC=const(0x33) # VOUT ADC
REG0x37_TS_ADC=const(0x37) # TS ADC
REG0x3B_Gate_Driver_Strength_Control=const(0x38) # Gate Driver Strength Control
REG0x3C_Gate_Driver_Dead_Time_Control=const(0x3c) # Gate Driver Dead Time Control
REG0x3D_Part_Information=const(0x3d) # Part Information
REG0x62_Reverse_Mode_Current=const(0x62) # Reverse Mode Current

# Assumes a 5mR shunt resistor which is standard. One step is 50mA
CURRENT_SCALE=50e-3

# One step is 20mV
VOLTAGE_SCALE=20e-3

class BQ25758:
    def __init__(self,
                 i2c_bus,
                 chip_enable_pin=None,
                 i2c_address=0x6b):
        self.i2c_bus = i2c_bus
        self.chip_enable_pin = chip_enable_pin
        self.i2c_address = i2c_address

    def _read_u8(self, reg_addr):
        buf = self.i2c_bus.readfrom_mem(self.i2c_address, reg_addr, 1)
        return buf[0]

    def _read_u16(self, reg_addr):
        buf = self.i2c_bus.readfrom_mem(self.i2c_address, reg_addr, 2)
        return buf[0] + (buf[1]<<8)

    def _read_s16(self, reg_addr):
        v = self._read_u16(reg_addr)
        if v >= 0x8000:
            v = v - 0x10000
        return v

    def _write_u8(self, reg_addr, value):
        buf = bytearray(1)
        buf[0] = value
        self.i2c_bus.writeto_mem(self.i2c_address, reg_addr, buf)

    def _write_u16(self, reg_addr, value):
        buf = bytearray(2)
        buf[0] = value & 0xff
        buf[1] = (value>>8) & 0xff
        self.i2c_bus.writeto_mem(self.i2c_address, reg_addr, buf)

    def setup(self):
        id = self._read_u8(REG0x3D_Part_Information)
        if id != 0x22:
            raise RuntimeError(f"Bad part ID : {id:02x}")

        # Set REG_RST to 1 to reset all registers to defaults incase this is
        # a warm restart
        self._write_u8(REG0x19_Power_Path_and_Reverse_Mode_Control, 1<<7)

        # FIXME disable watchdog when testing
        # For battery charging we do NOT want this as the converter should
        # turn off if the micro crashes and stops ending commands
        self.set_watchdog_timeout(0)

    def is_enabled(self):
        return not self.chip_enable_pin.value()

    def set_enabled(self, b=True):
        # Inverted logic on CE pin
        self.chip_enable_pin.value(not b)

    def get_output_current_limit(self):
        '''Output voltage will be regulated to keep within this current limit'''
        raw = self._read_u16(REG0x02_Output_Current_Limit)
        raw = (raw & 0b0000011111111100) >> 2
        return raw * CURRENT_SCALE

    def set_output_current_limit(self, value):
        '''Output voltage will be regulated to keep within this current limit'''
        v = int(value / CURRENT_SCALE)
        if v > 0x190:
            v = 0x190
        elif v < 8:
            v = 8
        else:
            v = v<<2

        self._write_u16(REG0x02_Output_Current_Limit, v)

    def get_output_voltage_limit(self):
        '''Desired output voltage if current limit allows'''
        raw = self._read_u16(REG0x04_Output_Voltage_Limit)

        raw = (raw & 0b0011111111111100) >> 2
        return raw * VOLTAGE_SCALE

    def set_output_voltage_limit(self, value):
        '''Desired output voltage if current limit allows'''
        v = int(value / VOLTAGE_SCALE)
        if v > 0xbb8:
            v = 0xbb8
        elif v < 0xa5:
            v = 0xa5
        else:
            v = v<<2

        self._write_u16(REG0x04_Output_Voltage_Limit, v)

    def get_input_current_dpm_limit(self):
        '''Input Current Dynamic Power Management (DPM) limit'''
        raw = self._read_u16(REG0x06_Input_Current_DPM_Limit)
        raw = (raw & 0b0000011111111100) >> 2
        return raw * CURRENT_SCALE

    def set_input_current_dpm_limit(self, value):
        v = int(value / CURRENT_SCALE)
        if v > 0x190:
            v = 0x190
        elif v < 8:
            v = 8
        else:
            v = v<<2

        self._write_u16(REG0x06_Input_Current_DPM_Limit, v)

    def get_input_voltage_dpm_limit(self):
        raw = self._read_u16(REG0x08_Input_Voltage_DPM_Limit)

        raw = (raw & 0b0011111111111100) >> 2
        return raw * VOLTAGE_SCALE

    def set_input_voltage_dpm_limit(self, value):
        v = int(value / VOLTAGE_SCALE)
        if v > 0xbb8:
            v = 0xbb8
        elif v < 0xd2:
            v = 0xd2
        else:
            v = v<<2

        self._write_u16(REG0x08_Input_Voltage_DPM_Limit, v)

    def get_reverse_mode_input_current_limit(self):
        raw = self._read_u16(REG0x0A_Reverse_Mode_Input_Current_Limit)
        raw = (raw & 0b0000011111111100) >> 2
        return raw * CURRENT_SCALE

    def set_reverse_mode_input_current_limit(self, value):
        v = int(value / CURRENT_SCALE)
        if v > 0x190:
            v = 0x190
        elif v < 8:
            v = 8
        else:
            v = v<<2

        self._write_u16(REG0x0A_Reverse_Mode_Input_Current_Limit, v)

    def get_reverse_mode_input_voltage_limit(self):
        raw = self._read_u16(REG0x0C_Reverse_Mode_Input_Voltage_Limit)

        raw = (raw & 0b0011111111111100) >> 2
        return raw * VOLTAGE_SCALE

    def set_reverse_mode_input_voltage_limit(self, value):
        v = int(value / VOLTAGE_SCALE)
        if v > 0xbb8:
            v = 0xbb8
        elif v < 0xa5:
            v = 0xa5
        else:
            v = v<<2

        self._write_u16(REG0x0C_Reverse_Mode_Input_Voltage_Limit, v)

    def get_reverse_enable(self):
        v = self._read_u8(REG0x19_Power_Path_and_Reverse_Mode_Control)
        return (v & 0x01) != 0

    def set_reverse_enable(self, b):
        v = self._read_u8(REG0x19_Power_Path_and_Reverse_Mode_Control)
        if b:
            v |= 0x01
        else:
            v &= ~0x01
        self._write_u8(REG0x19_Power_Path_and_Reverse_Mode_Control, v)

    def set_watchdog_timeout(self, value):
        if value == 0:
            wd = 0
        elif value <= 40:
            wd = 1
        elif value <= 80:
            wd = 2
        else:
            wd = 3

        self._write_u8(REG0x15_Timer_Control, wd<<4)

    def setup_adc(self, enable=True, continuous=True,
                  resolution_bits=15,
                  average=False, average_init=False):
        # Disable all channels to start
        v = 0
        self._write_u8(REG0x2C_ADC_Channel_Control, v)

        # Set resulation and mode
        v = 0
        if enable:
            v |= 1<<7
        if not continuous:
            v |= 1<<6

        if resolution_bits == 15:
            v |= 0<<4
        elif resolution_bits == 14:
            v |= 1<<4
        elif resolution_bits == 13:
            v |= 2<<4
        else:
            raise ValueError("Invalid resolution_bits")

        if average:
            v |= 1<<3
        if average_init:
            v |= 1<<2
        self._write_u8(REG0x2B_ADC_Control, v)

    def get_iin_adc(self):
        raw = self._read_s16(REG0x2D_IAC_ADC)
        return raw * 0.8e-3

    def get_iout_adc(self):
        raw = self._read_s16(REG0x2F_IOUT_ADC)
        return raw * 2.0e-3 # FIXME Why is this different from above

    def get_vin_adc(self):
        raw = self._read_u16(REG0x31_VAC_ADC)
        return raw * 2.0e-3

    def get_vout_adc(self):
        raw = self._read_u16(REG0x33_VOUT_ADC)
        v = raw * 2.0e-3
        # Quadratic correction derived from IT8511 reference calibration
        # error_mv = a*v^2 + b*v + c, correction subtracts the error
        correction = (0.056768 * v * v - 2.4064 * v - 182.57) * 1e-3
        return v - correction

    # Status_1 bits
    ADC_DONE_STAT = const(1<<7) # ADC conversion complete
    IAC_DPM_STAT = const(1<<6) # Set when in input current regulation
    VAC_DPM_STAT = const(1<<5) # Set when in input voltage regulation
    WD_STAT = const(1<<3)      # Set when I2C watchdog expired
    CHARGE_STAT_MASK = const(0x07) # FIXME Not really clear what these values are

    # Status_2 bits
    PG_STAT = const(1<<7)      # Power Good
    TS_STAT_OFFSET = const(4)  # Offset and mask for temperature sensor
    TS_STAT_MASK = const(0x07)

    # Status_3 bits
    FSW_SYNC_STAT_OFFSET = const(4)
    FSW_SYNC_STAT_MASK = const(0x03)
    REVERSE_STAT = const(1<<2)

    def get_status(self):
        status_1 = self._read_u8(REG0x21_Status_1)
        status_2 = self._read_u8(REG0x22_Status_2)
        status_3 = self._read_u8(REG0x23_Status_3)

        return (status_1, status_2, status_3)

    def get_status_str(self):
        (status_1, status_2, status_3) = self.get_status()

        result = []

        result.append(f"STATUS_1={status_1:02x}")
        if status_1 & ADC_DONE_STAT:
            result.append("ADC_DONE")
        if status_1 & IAC_DPM_STAT:
            result.append("IAC_DPM")
        if status_1 & VAC_DPM_STAT:
            result.append("VAC_DPM")
        if status_1 & WD_STAT:
            result.append("WD")
        result.append(f"CHARGE={status_1&CHARGE_STAT_MASK}")

        result.append(f"STATUS_2={status_2:02x}")
        if status_2 & PG_STAT:
            result.append("PG")
        ts = (status_2>>TS_STAT_OFFSET) & TS_STAT_MASK
        result.append(f"TS={ts}")

        result.append(f"STATUS_3={status_3:02x}")
        fsw_sync = (status_3>>FSW_SYNC_STAT_OFFSET) & FSW_SYNC_STAT_MASK
        result.append(f"FSW_SYNC={fsw_sync}")
        if status_3 & REVERSE_STAT:
            result.append("REVERSE")

        return ",".join(result)

    # Fault Status bits
    VAC_UV_STAT = const(1<<7)
    VAC_OV_STAT = const(1<<6)
    IBAT_OCP_STAT = const(1<<5)
    VBAT_OV_STAT = const(1<<4)
    TSHUT_STAT = const(1<<3)
    DRV_OKZ_STAT = const(1<<1)

    def get_fault_status(self):
        return self._read_u8(REG0x24_Fault_Status)

    def get_fault_status_str(self):
        fault = self.get_fault_status()
        result = []
        result.append(f"FAULT={fault:02x}")
        if fault & VAC_UV_STAT:
            result.append("VAC_UV")
        if fault & VAC_OV_STAT:
            result.append("VAC_OV")
        if fault & IBAT_OCP_STAT:
            result.append("IBAT_OCP")
        if fault & VBAT_OV_STAT:
            result.append("VBAT_OV")
        if fault & DRV_OKZ_STAT:
            result.append("DRV_OKZ")
        return ",".join(result)

