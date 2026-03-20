# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
import math
from micropython import const

# CHARGE_STAT[2:0] names indexed by value (REG0x21 bits 2:0)
_CHARGE_STAT_NAMES = ('Off', 'Trickle', 'Pre-chg', 'CC', 'CV', 'Rsvd', 'Top-off', 'Done')

class BQ25758:
    # ADC step sizes
    # Voltage channels: 2mV per LSB (datasheet value, confirmed accurate)
    VIN_ADC_SCALE  = 2.0e-3
    VOUT_ADC_SCALE = 2.0e-3
    # Current channels: datasheet specifies 2mA per LSB for both IIN and IOUT,
    # assuming a 2mR sense resistor. This design uses 5mR on the input (Rac_sns),
    # which is the TI-recommended value but causes the ADC to see 2.5× more voltage
    # per amp, giving an effective scale of 2.0 × (2/5) = 0.8mA/LSB for IIN.
    # The output side uses the assumed 2mR, so IOUT_ADC_SCALE matches the datasheet.
    # Remaining chip-to-chip error (~1%) is handled by LinearCalibration.
    IIN_ADC_SCALE  = 0.8e-3   # 0.8mA/LSB (5mR sense resistor; datasheet says 2mA/LSB for 2mR)
    IOUT_ADC_SCALE = 2.0e-3   # 2.0mA/LSB (2mR sense resistor, confirmed by measurement)

    # IIN / IOUT overcurrent protection (OCP) threshold via external resistor on IIN/IOUT pins.
    #
    # Both pins have an internal transconductance amplifier (Gm not stated in datasheet;
    # determined by measurement). Gm differs between input and output:
    #   Vsense  = Isense × Rsense (Rsense = 5mR on both input and output)
    #   Ipin    = Gm × Vsense
    #   Vpin    = Ipin × Rpin  = Gm × Isense × Rsense × Rpin
    #   Trip when Vpin ≥ Vthreshold (Vthreshold = 2V, datasheet)
    #   Ilimit  = Vthreshold / (Gm × Rsense × Rpin)
    #
    # IIN pin:  Gm_in  = 0.02 A/V  → Ilimit = 20000 / Rpin
    #   Rpin = 4990Ω → ~4A trip (too low); replace with 2kΩ for 10A.
    # IOUT pin: Gm_out = 0.008 A/V → Ilimit = 50000 / Rpin
    #   Rpin = 4990Ω → ~10A trip (correct, no change needed).
    #
    # Note: Gm_out/Gm_in = 2/5 — the same factor that causes IIN_ADC_SCALE to be
    # 0.8mA/LSB instead of the datasheet's 2mA/LSB. Both reflect the 5mR input
    # sense resistor vs the 2mR assumed by much of the BQ25758 datasheet text.

    # Limit Register scaling values
    # Assumes a 5mR shunt resistor which is standard. One step is 50mA
    CURRENT_SCALE=50e-3
    # One ADC step is 20mV
    VOLTAGE_SCALE=20e-3

    # Device register names from datasheet
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

    def __init__(self,
                 i2c_bus,
                 chip_enable_pin=None,
                 i2c_address=0x6b):
        self.i2c_bus = i2c_bus
        self.chip_enable_pin = chip_enable_pin
        self.i2c_address = i2c_address
        self.detected = False

    def _read_u8(self, reg_addr):
        try:
            buf = self.i2c_bus.readfrom_mem(self.i2c_address, reg_addr, 1)
        except OSError:
            self.detected = False
            raise

        return buf[0]

    def _read_u16(self, reg_addr):
        try:
            buf = self.i2c_bus.readfrom_mem(self.i2c_address, reg_addr, 2)
        except OSError:
            self.detected = False
            raise

        return buf[0] + (buf[1]<<8)

    def _read_s16(self, reg_addr):
        try:
            v = self._read_u16(reg_addr)
        except OSError:
            self.detected = False
            raise

        if v >= 0x8000:
            v = v - 0x10000
        return v

    def _write_u8(self, reg_addr, value):
        buf = bytearray(1)
        buf[0] = value
        try:
            self.i2c_bus.writeto_mem(self.i2c_address, reg_addr, buf)
        except OSError:
            self.detected = False
            raise

    def _write_u16(self, reg_addr, value):
        buf = bytearray(2)
        buf[0] = value & 0xff
        buf[1] = (value>>8) & 0xff
        try:
            self.i2c_bus.writeto_mem(self.i2c_address, reg_addr, buf)
        except OSError:
            self.detected = False
            raise

    def setup(self):
        self.detected = False

        id = self._read_u8(REG0x3D_Part_Information)
        if id != 0x22:
            raise RuntimeError(f"Bad part ID : {id:02x}")

        # Set REG_RST to 1 to reset all registers to defaults in case this is
        # a warm restart
        self._write_u8(REG0x19_Power_Path_and_Reverse_Mode_Control, 1<<7)

        # Watchdog disabled by default. Enable via startup.dat:
        #   watchdog_timeout=40   (40s timeout)
        self.set_watchdog_timeout(0)
        self.detected = True

    def is_detected(self):
        return self.detected

    def is_enabled(self):
        return not self.chip_enable_pin.value()

    def set_enabled(self, b=True):
        # Inverted logic on CE pin
        self.chip_enable_pin.value(not b)

    def get_output_current_limit(self):
        '''Output voltage will be regulated to keep within this current limit'''
        raw = self._read_u16(REG0x02_Output_Current_Limit)
        raw = (raw & 0b0000011111111100) >> 2
        return raw * self.CURRENT_SCALE

    def set_output_current_limit(self, value):
        '''Output voltage will be regulated to keep within this current limit'''
        v = int(value / self.CURRENT_SCALE)
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
        return raw * self.VOLTAGE_SCALE

    def set_output_voltage_limit(self, value):
        '''Desired output voltage if current limit allows'''
        v = int(value / self.VOLTAGE_SCALE)
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
        return raw * self.CURRENT_SCALE

    def set_input_current_dpm_limit(self, value):
        v = int(value / self.CURRENT_SCALE)
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
        return raw * self.VOLTAGE_SCALE

    def set_input_voltage_dpm_limit(self, value):
        v = int(value / self.VOLTAGE_SCALE)
        if v > 0xbb8:
            v = 0xbb8
        elif v < 0xd2:
            v = 0xd2
        else:
            v = v<<2

        self._write_u16(REG0x08_Input_Voltage_DPM_Limit, v)

    def get_reverse_current(self):
        raw = self._read_u16(REG0x0A_Reverse_Mode_Input_Current_Limit)
        raw = (raw & 0b0000011111111100) >> 2
        return raw * self.CURRENT_SCALE

    def set_reverse_current(self, value):
        v = int(value / self.CURRENT_SCALE)
        if v > 0x190:
            v = 0x190
        elif v < 8:
            v = 8
        else:
            v = v<<2

        self._write_u16(REG0x0A_Reverse_Mode_Input_Current_Limit, v)

    def get_reverse_voltage(self):
        raw = self._read_u16(REG0x0C_Reverse_Mode_Input_Voltage_Limit)

        raw = (raw & 0b0011111111111100) >> 2
        return raw * self.VOLTAGE_SCALE

    def set_reverse_voltage(self, value):
        v = int(value / self.VOLTAGE_SCALE)
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

    def get_auto_reverse(self):
        '''Read EN_AUTO_REV (bit 1 of REG0x19).
        Defined on BQ25750 but marked reserved on BQ25758 — tested and
        functional: automatically switches to reverse mode on VIN loss.
        Does not auto-switch back when VIN is restored.
        '''
        v = self._read_u8(REG0x19_Power_Path_and_Reverse_Mode_Control)
        return (v & 0x02) != 0

    def set_auto_reverse(self, b):
        '''Set EN_AUTO_REV (bit 1 of REG0x19).
        See get_auto_reverse() for behaviour notes.
        '''
        v = self._read_u8(REG0x19_Power_Path_and_Reverse_Mode_Control)
        if b:
            v |= 0x02
        else:
            v &= ~0x02
        self._write_u8(REG0x19_Power_Path_and_Reverse_Mode_Control, v)

    def set_bypass(self, b):
        '''Enable or disable bypass mode (EN_BYPASS bit in REG0x1E).

        When enabled, the DC/DC converter is disabled and the high-side FETs
        are turned on directly, passing input to output with minimal drop.
        '''
        v = self._read_u8(REG0x1E_Bypass_and_Overload_Control)
        if b:
            v |= (1 << 4)
        else:
            v &= ~(1 << 4)
        self._write_u8(REG0x1E_Bypass_and_Overload_Control, v)

    def get_bypass(self):
        '''Return True if bypass mode is enabled.'''
        v = self._read_u8(REG0x1E_Bypass_and_Overload_Control)
        return (v & (1 << 4)) != 0

    def set_hiz(self, b):
        '''Enable or disable HIZ mode (EN_HIZ bit 2 in REG0x17_Converter_Control).

        When a valid input supply is present, HIZ mode disables switching and
        the REGN LDO; system load is provided by the battery. Also triggered
        by the IIN pin falling below the hardware threshold.
        '''
        v = self._read_u8(self.REG0x17_Converter_Control)
        if b:
            v |= (1 << 2)
        else:
            v &= ~(1 << 2)
        self._write_u8(self.REG0x17_Converter_Control, v)

    def get_hiz(self):
        '''Return True if HIZ mode is enabled.'''
        v = self._read_u8(self.REG0x17_Converter_Control)
        return (v & (1 << 2)) != 0

    def set_watchdog_timeout(self, value):
        '''Set I2C watchdog timeout in seconds.
        0=disabled, 1-40=40s, 41-80=80s, >80=160s.
        Converter is disabled if no I2C traffic within the timeout period.
        '''
        if value == 0:
            wd = 0
        elif value <= 40:
            wd = 1
        elif value <= 80:
            wd = 2
        else:
            wd = 3
        self._write_u8(REG0x15_Timer_Control, wd << 4)

    def get_watchdog_timeout(self):
        '''Return watchdog timeout in seconds (0=disabled, 40, 80, or 160).'''
        wd = (self._read_u8(REG0x15_Timer_Control) >> 4) & 0x03
        return (0, 40, 80, 160)[wd]

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
        return raw * self.IIN_ADC_SCALE

    def get_iout_adc(self):
        raw = self._read_s16(REG0x2F_IOUT_ADC)
        return raw * self.IOUT_ADC_SCALE

    def get_vin_adc(self):
        raw = self._read_u16(REG0x31_VAC_ADC)
        return raw * self.VIN_ADC_SCALE

    def get_vout_adc(self):
        raw = self._read_u16(REG0x33_VOUT_ADC)
        return raw * self.VOUT_ADC_SCALE

    def get_ts_adc(self):
        '''Return TS pin voltage as a fraction of VREGN (0.0 to 1.0).
        Step size is 0.0976% per LSB (1/1024 per LSB).
        Circuit: REGN -> NTC -> TS pin -> 10k bias -> GND
        '''
        raw = self._read_u16(REG0x37_TS_ADC)
        return raw / 1024.0

    def get_ts_celsius(self, bias_kohm=10.0):
        '''Return thermistor temperature in degrees Celsius.

        Assumes a Semitec 103AT 10k NTC thermistor with Steinhart-Hart
        coefficients fitted from the datasheet table.
        bias_kohm: bias resistor value in kOhms (default 10k).
        Circuit: REGN -> NTC -> TS pin -> bias_kohm -> GND
        '''
        fraction = self.get_ts_adc()
        if fraction <= 0.0 or fraction >= 1.0:
            return None  # Out of range
        # Recover NTC resistance in kOhms from voltage divider
        r_ntc = bias_kohm * (1.0 - fraction) / fraction
        # Steinhart-Hart equation fitted to Semitec 103AT data
        A = 2.68660875e-3
        B = 2.85931334e-4
        C = 7.32506554e-7
        ln_r = math.log(r_ntc)
        t_kelvin = 1.0 / (A + B * ln_r + C * ln_r ** 3)
        return t_kelvin - 273.15

    # Status_1 bits
    ADC_DONE_STAT = const(1<<7) # ADC conversion complete
    IAC_DPM_STAT = const(1<<6) # Set when in input current regulation
    VAC_DPM_STAT = const(1<<5) # Set when in input voltage regulation
    WD_STAT = const(1<<3)      # Set when I2C watchdog expired
    CHARGE_STAT_MASK = const(0x07)
    # CHARGE_STAT[2:0] values (REG0x21 bits 2:0):
    #   0 = Not switching
    #   1 = Trickle charge (VBAT < VBAT_SHORT)
    #   2 = Pre-charge (VBAT < VBAT_LOWV)
    #   3 = CC mode (fast charge, constant current)
    #   4 = CV mode (taper charge, constant voltage)
    #   5 = Reserved
    #   6 = Top-off timer active
    #   7 = Charge termination done

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
        chg = status_1 & CHARGE_STAT_MASK
        result.append(f"CHARGE={chg}({_CHARGE_STAT_NAMES[chg]})")

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

    def output_regulation_mode(self):
        '''Return the current converter regulation mode as a string.

        Returns 'CC' when in constant-current mode (CHARGE_STAT=3),
        'CV' when in constant-voltage mode (CHARGE_STAT=4/6/7),
        or 'Off' when not switching (0/1/2/5).
        '''
        chg = self._read_u8(REG0x21_Status_1) & CHARGE_STAT_MASK
        if chg == 3:
            return 'CC'
        elif chg in (4, 6, 7):
            return 'CV'
        else:
            return 'Off'

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

