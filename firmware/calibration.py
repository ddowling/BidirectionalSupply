# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
import json
import os
import machine
import ubinascii


class LinearCalibration:
    """Linear gain/offset calibration: corrected = (raw - offset) / gain"""

    def __init__(self):
        self.gain = 1.0
        self.offset = 0.0
        self.rms_error = 0.0

    def convert(self, v):
        return (v - self.offset) / self.gain

    def save(self):
        return {'gain': self.gain, 'offset': self.offset, 'rms_error': self.rms_error}

    def load(self, data):
        try:
            self.gain = float(data['gain'])
            self.offset = float(data['offset'])
        except (KeyError, TypeError, ValueError):
            return False
        # Handle legacy rms_error key names (rms_error_mv, rms_error_ma)
        for key in ('rms_error', 'rms_error_mv', 'rms_error_ma'):
            if key in data:
                self.rms_error = float(data[key])
                break
        return True


class QuadraticCalibration(LinearCalibration):
    """Quadratic error correction (mV) applied before linear gain/offset.

    Error model: error_mv = quad_a*v^2 + quad_b*v + quad_c
    Corrected:   v -= error_mv / 1000
    Then:        result = (v - offset) / gain
    """

    def __init__(self):
        super().__init__()
        self.quad_a = 0.0
        self.quad_b = 0.0
        self.quad_c = 0.0

    def convert(self, v):
        a, b, c = self.quad_a, self.quad_b, self.quad_c
        if a != 0.0 or b != 0.0 or c != 0.0:
            v -= (a * v * v + b * v + c) * 1e-3
        return super().convert(v)

    def save(self):
        d = super().save()
        d.update({'quad_a': self.quad_a, 'quad_b': self.quad_b, 'quad_c': self.quad_c})
        return d

    def load(self, data):
        if not super().load(data):
            return False
        self.quad_a = float(data.get('quad_a', 0.0))
        self.quad_b = float(data.get('quad_b', 0.0))
        self.quad_c = float(data.get('quad_c', 0.0))
        return True


class Calibration:
    """
    Calibration data manager for BidirectionalSupply boards.

    Loads calibration constants from calibration.dat JSON file.
    Each board can have individual calibration constants for:
    - Output voltage ADC (vout_adc): quadratic + linear correction
    - Input voltage ADC (vin_adc): linear correction
    - Output current ADC (iout_adc): linear correction
    - Input current ADC (iin_adc): linear correction
    """

    def __init__(self, filename="calibration.dat", auto_board_id=True):
        self.filename = filename
        self.auto_board_id = auto_board_id
        self._board_id = None
        self._hardware_id = None
        self._calibration_date = None
        self._die_temp_celsius = None
        self.vout_adc = QuadraticCalibration()
        self.vin_adc = LinearCalibration()
        self.iout_adc = LinearCalibration()
        self.iin_adc = LinearCalibration()
        self.load()

    def _reset_channels(self):
        """Reset board metadata and all channel objects to defaults"""
        self._board_id = self._get_hardware_board_id() if self.auto_board_id else "default"
        self._hardware_id = self._get_hardware_board_id()
        self._calibration_date = None
        self.vout_adc = QuadraticCalibration()
        self.vin_adc = LinearCalibration()
        self.iout_adc = LinearCalibration()
        self.iin_adc = LinearCalibration()

    @staticmethod
    def _validate_data(data):
        """Check that data has the required calibration structure (no side effects)"""
        if not isinstance(data, dict):
            return False
        if 'board_id' not in data or 'calibration_date' not in data:
            return False
        for name in ('vout_adc', 'vin_adc', 'iout_adc', 'iin_adc'):
            if name in data:
                ch = data[name]
                if not isinstance(ch, dict) or 'gain' not in ch or 'offset' not in ch:
                    return False
        return True

    def _load_from_dict(self, data):
        """Load calibration from a dict. Returns True on success."""
        if not self._validate_data(data):
            return False
        self._board_id = data['board_id']
        self._hardware_id = data.get('hardware_id', self._get_hardware_board_id())
        self._calibration_date = data.get('calibration_date')
        self._die_temp_celsius = data.get('die_temp_celsius')
        for name in ('vout_adc', 'vin_adc', 'iout_adc', 'iin_adc'):
            if name in data:
                if not getattr(self, name).load(data[name]):
                    print(f"Invalid {name} calibration data")
                    return False
        return True

    def load(self):
        """Load calibration data from JSON file with validation"""
        backup_filename = self.filename + '.bak'
        for attempt_file in [self.filename, backup_filename]:
            try:
                with open(attempt_file, 'r') as f:
                    loaded_data = json.load(f)
                if self._load_from_dict(loaded_data):
                    print(f"Loaded calibration data from {attempt_file}")
                    return
                else:
                    print(f"Invalid calibration data in {attempt_file}, trying backup...")
            except OSError:
                if attempt_file == self.filename:
                    print(f"Calibration file {self.filename} not found, trying backup...")
            except Exception as e:
                print(f"Error loading {attempt_file}: {e}")

        print("Using default calibration - no valid calibration file found")
        self._reset_channels()

    def save(self):
        """Save calibration data to JSON file with atomic write protection"""
        temp_filename = self.filename + '.tmp'
        backup_filename = self.filename + '.bak'

        data = {
            'board_id': self._board_id or 'default',
            'hardware_id': self._hardware_id or self._get_hardware_board_id(),
            'calibration_date': self._calibration_date,
            'die_temp_celsius': self._die_temp_celsius,
            'vout_adc': self.vout_adc.save(),
            'vin_adc': self.vin_adc.save(),
            'iout_adc': self.iout_adc.save(),
            'iin_adc': self.iin_adc.save(),
        }

        try:
            json_str = json.dumps(data)
            if len(json_str) < 10:
                raise ValueError("JSON data appears to be too short/corrupted")

            try:
                with open(self.filename, 'r') as src:
                    with open(backup_filename, 'w') as dst:
                        dst.write(src.read())
            except OSError:
                pass  # Original file doesn't exist yet

            with open(temp_filename, 'w') as f:
                f.write(json_str)

            with open(temp_filename, 'r') as f:
                if 'board_id' not in json.load(f):
                    raise ValueError("Saved data missing required fields")

            try:
                os.remove(self.filename)
            except OSError:
                pass
            os.rename(temp_filename, self.filename)

            print(f"Saved calibration data to {self.filename}")
            print(f"Backup saved to {backup_filename}")

        except Exception as e:
            print(f"Error saving calibration: {e}")
            try:
                with open(backup_filename, 'r') as src:
                    with open(self.filename, 'w') as dst:
                        dst.write(src.read())
                print("Restored calibration from backup")
            except OSError:
                print("No backup available to restore")
            try:
                os.remove(temp_filename)
            except OSError:
                pass
            raise

    def _get_hardware_board_id(self):
        """Get unique board ID from RP2350 hardware"""
        try:
            unique_id = machine.unique_id()
            hex_id = ubinascii.hexlify(unique_id).decode('ascii')
            return f"RP2350_{hex_id[-8:].upper()}"
        except:
            return "RP2350_UNKNOWN"

    def get_board_id(self):
        return self._board_id or "default"

    def get_hardware_id(self):
        return self._hardware_id or self._get_hardware_board_id()

    def set_board_id(self, board_id=None):
        if board_id is None:
            board_id = self._get_hardware_board_id()
        self._board_id = board_id
        self._hardware_id = self._get_hardware_board_id()

    def get_calibration_date(self):
        return self._calibration_date or "not_calibrated"

    def set_calibration_date(self, date_str):
        self._calibration_date = date_str

    def get_die_temp_celsius(self):
        return self._die_temp_celsius

    def set_die_temp_celsius(self, temp):
        self._die_temp_celsius = temp

    # --- Calibration application ---

    def calibrate_vout_adc(self, raw_value):
        return self.vout_adc.convert(raw_value)

    def calibrate_vin_adc(self, raw_value):
        return self.vin_adc.convert(raw_value)

    def calibrate_iout_adc(self, raw_value):
        # The BQ25758 current ADC has a ~2mA/LSB resolution floor: at low
        # currents (below ~100mA) it reads zero counts. Applying the linear
        # calibration to a zero reading produces a spurious positive offset
        # (~110mA). Clamp to zero to avoid reporting phantom current at no load.
        return max(0.0, self.iout_adc.convert(raw_value))

    def calibrate_iin_adc(self, raw_value):
        # Same ADC floor issue as iout — clamp to zero.
        return max(0.0, self.iin_adc.convert(raw_value))

    # --- Setting calibration constants ---

    def set_vout_calibration(self, gain=1.0, offset=0.0, quad_a=0.0, quad_b=0.0, quad_c=0.0, rms_error_mv=0.0):
        self.vout_adc.gain = gain
        self.vout_adc.offset = offset
        self.vout_adc.quad_a = quad_a
        self.vout_adc.quad_b = quad_b
        self.vout_adc.quad_c = quad_c
        self.vout_adc.rms_error = rms_error_mv

    def set_vin_calibration(self, gain=1.0, offset=0.0, rms_error_mv=0.0):
        self.vin_adc.gain = gain
        self.vin_adc.offset = offset
        self.vin_adc.rms_error = rms_error_mv

    def set_iout_calibration(self, gain=1.0, offset=0.0, rms_error_ma=0.0):
        self.iout_adc.gain = gain
        self.iout_adc.offset = offset
        self.iout_adc.rms_error = rms_error_ma

    def set_iin_calibration(self, gain=1.0, offset=0.0, rms_error_ma=0.0):
        self.iin_adc.gain = gain
        self.iin_adc.offset = offset
        self.iin_adc.rms_error = rms_error_ma

    def get_calibration_summary(self):
        temp_str = f"{self._die_temp_celsius:.1f}°C" if self._die_temp_celsius is not None else "not recorded"
        summary = [
            f"Board ID: {self.get_board_id()}",
            f"Calibration Date: {self.get_calibration_date()}",
            f"Die Temp at Calibration: {temp_str}",
            "",
        ]
        channels = [
            ('vout_adc', 'mV'),
            ('vin_adc', 'mV'),
            ('iout_adc', 'mA'),
            ('iin_adc', 'mA'),
        ]
        for name, unit in channels:
            ch = getattr(self, name)
            line = f"{name}: gain={ch.gain:.6f}, offset={ch.offset:.6f}, error={ch.rms_error:.1f}{unit}"
            if isinstance(ch, QuadraticCalibration):
                a, b, c = ch.quad_a, ch.quad_b, ch.quad_c
                if a != 0.0 or b != 0.0 or c != 0.0:
                    line += f"\n  quad: {a:.6f}*V^2 + {b:.4f}*V + {c:.2f} mV"
            summary.append(line)
        return "\n".join(summary)

    def is_calibrated(self, channel=None):
        if self._calibration_date is None:
            return False
        if channel is not None:
            return hasattr(self, channel)
        return True

    def diagnose_files(self):
        """Diagnose calibration file issues"""
        print("=== Calibration File Diagnosis ===")
        for label, filename in [("Main", self.filename), ("Backup", self.filename + '.bak')]:
            try:
                stat = os.stat(filename)
                print(f"{label} file ({filename}): {stat[6]} bytes")
                if stat[6] == 0:
                    print(f"  WARNING: {label} file is empty!")
                    continue
                with open(filename, 'r') as f:
                    data = json.loads(f.read())
                if self._validate_data(data):
                    status = "Valid - can be used for recovery" if label == "Backup" else "Valid JSON structure"
                    print(f"  {label} file: {status}")
                else:
                    print(f"  {label} file: Invalid calibration data structure")
            except OSError:
                print(f"{label} file ({filename}): Does not exist")
            except Exception:
                print(f"  {label} file: Invalid JSON syntax")

        temp_file = self.filename + '.tmp'
        try:
            stat = os.stat(temp_file)
            print(f"WARNING: Temp file ({temp_file}): {stat[6]} bytes - leftover from failed save")
        except OSError:
            pass

    def repair_from_backup(self):
        """Attempt to repair main calibration file from backup"""
        backup_file = self.filename + '.bak'
        try:
            with open(backup_file, 'r') as f:
                backup_data = json.load(f)
            if self._validate_data(backup_data):
                with open(self.filename, 'w') as f:
                    json.dump(backup_data, f)
                print(f"Successfully repaired {self.filename} from backup")
                self.load()
                return True
            else:
                print("Backup file contains invalid data - cannot repair")
                return False
        except Exception as e:
            print(f"Failed to repair from backup: {e}")
            return False
