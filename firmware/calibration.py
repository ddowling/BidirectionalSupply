import json
import os
import machine
import ubinascii

class Calibration:
    """
    Calibration data manager for BidirectionalSupply boards.
    
    Loads calibration constants from calibration.dat JSON file.
    Each board can have individual calibration constants for:
    - Output voltage ADC (vout_adc)
    - Input voltage ADC (vin_adc) 
    - Output current ADC (iout_adc)
    - Input current ADC (iin_adc)
    - Ideal diode switch voltage sense (switch_vsense)
    """
    
    def __init__(self, filename="calibration.dat", auto_board_id=True):
        self.filename = filename
        self.data = {}
        self.auto_board_id = auto_board_id
        self.load()
    
    def load(self):
        """Load calibration data from JSON file with validation"""
        backup_filename = self.filename + '.bak'
        
        # Try to load main file first
        for attempt_file in [self.filename, backup_filename]:
            try:
                with open(attempt_file, 'r') as f:
                    loaded_data = json.load(f)
                
                # Validate loaded data
                if self._validate_calibration_data(loaded_data):
                    self.data = loaded_data
                    print(f"Loaded calibration data from {attempt_file}")
                    return
                else:
                    print(f"Invalid calibration data in {attempt_file}, trying backup...")
                    continue
                    
            except OSError:
                if attempt_file == self.filename:
                    print(f"Calibration file {self.filename} not found, trying backup...")
                continue
            except Exception as e:
                print(f"Error loading {attempt_file}: {e}")
                continue
        
        # If we get here, both main and backup failed
        print("Using default calibration - no valid calibration file found")
        self.data = self._get_default_calibration()
    
    def _validate_calibration_data(self, data):
        """Validate that calibration data has required structure"""
        if not isinstance(data, dict):
            return False
        
        # Check required top-level keys
        required_keys = ['board_id', 'calibration_date']
        for key in required_keys:
            if key not in data:
                print(f"Missing required key: {key}")
                return False
        
        # Check ADC channel structure
        adc_channels = ['vout_adc', 'vin_adc', 'iout_adc', 'iin_adc', 'switch_vsense']
        for channel in adc_channels:
            if channel in data:
                if not isinstance(data[channel], dict):
                    print(f"Invalid {channel} structure")
                    return False
                # Check required subkeys
                for subkey in ['gain', 'offset']:
                    if subkey not in data[channel]:
                        print(f"Missing {channel}.{subkey}")
                        return False
                    if not isinstance(data[channel][subkey], (int, float)):
                        print(f"Invalid {channel}.{subkey} type")
                        return False
        
        return True
    
    def save(self):
        """Save current calibration data to JSON file with atomic write protection"""
        temp_filename = self.filename + '.tmp'
        backup_filename = self.filename + '.bak'
        
        try:
            # First, validate the data can be serialized to JSON
            json_str = json.dumps(self.data)
            if len(json_str) < 10:  # Sanity check - should be much longer
                raise ValueError("JSON data appears to be too short/corrupted")
            
            # Create backup of existing file if it exists
            try:
                with open(self.filename, 'r') as src:
                    with open(backup_filename, 'w') as dst:
                        dst.write(src.read())
            except OSError:
                pass  # Original file doesn't exist, that's ok
            
            # Write to temporary file first
            with open(temp_filename, 'w') as f:
                f.write(json_str)
            
            # Verify the temporary file was written correctly
            with open(temp_filename, 'r') as f:
                test_data = json.load(f)
                if 'board_id' not in test_data:
                    raise ValueError("Saved data missing required fields")
            
            # Atomic replacement: rename temp file to actual file
            import os
            try:
                os.remove(self.filename)  # Remove original (MicroPython doesn't have rename)
            except OSError:
                pass
            os.rename(temp_filename, self.filename)
            
            print(f"Saved calibration data to {self.filename}")
            
            # Keep backup file for future recovery - don't delete it
            print(f"Backup saved to {backup_filename}")
                
        except Exception as e:
            print(f"Error saving calibration: {e}")
            
            # Try to restore from backup if it exists
            try:
                with open(backup_filename, 'r') as src:
                    with open(self.filename, 'w') as dst:
                        dst.write(src.read())
                print("Restored calibration from backup")
            except OSError:
                print("No backup available to restore")
            
            # Clean up any leftover temp file
            try:
                import os
                os.remove(temp_filename)
            except OSError:
                pass
                
            raise  # Re-raise the exception so caller knows save failed
    
    def _get_hardware_board_id(self):
        """Get unique board ID from RP2350 hardware"""
        try:
            unique_id = machine.unique_id()
            hex_id = ubinascii.hexlify(unique_id).decode('ascii')
            # Use last 8 characters for readability
            return f"RP2350_{hex_id[-8:].upper()}"
        except:
            return "RP2350_UNKNOWN"
    
    def _get_default_calibration(self):
        """Default calibration constants (no correction)"""
        board_id = self._get_hardware_board_id() if self.auto_board_id else "default"
        return {
            "board_id": board_id,
            "hardware_id": self._get_hardware_board_id(),
            "calibration_date": "not_calibrated",
            "vout_adc": {
                "gain": 1.0,
                "offset": 0.0,
                "quad_a": 0.0,
                "quad_b": 0.0,
                "quad_c": 0.0,
                "rms_error_mv": 0.0
            },
            "vin_adc": {
                "gain": 1.0, 
                "offset": 0.0,
                "rms_error_mv": 0.0
            },
            "iout_adc": {
                "gain": 1.0,
                "offset": 0.0,
                "rms_error_ma": 0.0
            },
            "iin_adc": {
                "gain": 1.0,
                "offset": 0.0, 
                "rms_error_ma": 0.0
            },
            "switch_vsense": {
                "gain": 1.0,
                "offset": 0.0,
                "rms_error_mv": 0.0
            }
        }
    
    def get_board_id(self):
        """Get board identifier"""
        return self.data.get("board_id", "default")
    
    def get_hardware_id(self):
        """Get hardware-based board identifier"""
        return self.data.get("hardware_id", self._get_hardware_board_id())
    
    def set_board_id(self, board_id=None):
        """Set board identifier. If None, uses hardware ID"""
        if board_id is None:
            board_id = self._get_hardware_board_id()
        self.data["board_id"] = board_id
        self.data["hardware_id"] = self._get_hardware_board_id()
    
    def get_calibration_date(self):
        """Get calibration date"""
        return self.data.get("calibration_date", "not_calibrated")
    
    def set_calibration_date(self, date_str):
        """Set calibration date"""
        self.data["calibration_date"] = date_str
    
    def calibrate_vout_adc(self, raw_value):
        """Apply calibration to output voltage ADC reading.

        Applies quadratic correction first (if coefficients are non-zero),
        then linear gain/offset correction.
        Quadratic: error_mv = a*v^2 + b*v + c, subtracted from raw value.
        """
        cal = self.data.get("vout_adc", {"gain": 1.0, "offset": 0.0})
        v = raw_value
        # Apply quadratic correction if coefficients are present
        a = cal.get("quad_a", 0.0)
        b = cal.get("quad_b", 0.0)
        c = cal.get("quad_c", 0.0)
        if a != 0.0 or b != 0.0 or c != 0.0:
            correction = (a * v * v + b * v + c) * 1e-3
            v = v - correction
        # Apply linear gain/offset correction
        return (v - cal.get("offset", 0.0)) / cal.get("gain", 1.0)
    
    def calibrate_vin_adc(self, raw_value):
        """Apply calibration to input voltage ADC reading"""
        cal = self.data.get("vin_adc", {"gain": 1.0, "offset": 0.0})
        return (raw_value - cal["offset"]) / cal["gain"]
    
    def calibrate_iout_adc(self, raw_value):
        """Apply calibration to output current ADC reading"""
        cal = self.data.get("iout_adc", {"gain": 1.0, "offset": 0.0})
        return (raw_value - cal["offset"]) / cal["gain"]
    
    def calibrate_iin_adc(self, raw_value):
        """Apply calibration to input current ADC reading"""
        cal = self.data.get("iin_adc", {"gain": 1.0, "offset": 0.0})
        return (raw_value - cal["offset"]) / cal["gain"]
        
    def calibrate_switch_vsense(self, raw_value):
        """Apply calibration to ideal diode switch voltage sense"""
        cal = self.data.get("switch_vsense", {"gain": 1.0, "offset": 0.0})
        return (raw_value - cal["offset"]) / cal["gain"]
    
    def set_vout_calibration(self, gain=1.0, offset=0.0, quad_a=0.0, quad_b=0.0, quad_c=0.0, rms_error_mv=0.0):
        """Set output voltage ADC calibration constants.

        Args:
            gain: Linear gain correction
            offset: Linear offset correction (V)
            quad_a: Quadratic coefficient (mV/V^2)
            quad_b: Linear coefficient (mV/V)
            quad_c: Constant offset (mV)
            rms_error_mv: RMS error after calibration
        """
        if "vout_adc" not in self.data:
            self.data["vout_adc"] = {}
        self.data["vout_adc"]["gain"] = gain
        self.data["vout_adc"]["offset"] = offset
        self.data["vout_adc"]["quad_a"] = quad_a
        self.data["vout_adc"]["quad_b"] = quad_b
        self.data["vout_adc"]["quad_c"] = quad_c
        self.data["vout_adc"]["rms_error_mv"] = rms_error_mv
    
    def set_vin_calibration(self, gain, offset, rms_error_mv=0.0):
        """Set input voltage ADC calibration constants"""
        if "vin_adc" not in self.data:
            self.data["vin_adc"] = {}
        self.data["vin_adc"]["gain"] = gain
        self.data["vin_adc"]["offset"] = offset
        self.data["vin_adc"]["rms_error_mv"] = rms_error_mv
    
    def set_iout_calibration(self, gain, offset, rms_error_ma=0.0):
        """Set output current ADC calibration constants"""
        if "iout_adc" not in self.data:
            self.data["iout_adc"] = {}
        self.data["iout_adc"]["gain"] = gain
        self.data["iout_adc"]["offset"] = offset
        self.data["iout_adc"]["rms_error_ma"] = rms_error_ma
    
    def set_iin_calibration(self, gain, offset, rms_error_ma=0.0):
        """Set input current ADC calibration constants"""  
        if "iin_adc" not in self.data:
            self.data["iin_adc"] = {}
        self.data["iin_adc"]["gain"] = gain
        self.data["iin_adc"]["offset"] = offset
        self.data["iin_adc"]["rms_error_ma"] = rms_error_ma
    
    def set_switch_calibration(self, gain, offset, rms_error_mv=0.0):
        """Set ideal diode switch voltage sense calibration constants"""
        if "switch_vsense" not in self.data:
            self.data["switch_vsense"] = {}
        self.data["switch_vsense"]["gain"] = gain
        self.data["switch_vsense"]["offset"] = offset
        self.data["switch_vsense"]["rms_error_mv"] = rms_error_mv
    
    def get_calibration_summary(self):
        """Get summary of all calibration data"""
        summary = []
        summary.append(f"Board ID: {self.get_board_id()}")
        summary.append(f"Calibration Date: {self.get_calibration_date()}")
        summary.append("")
        
        for channel in ["vout_adc", "vin_adc", "iout_adc", "iin_adc", "switch_vsense"]:
            if channel in self.data:
                cal = self.data[channel]
                gain = cal.get("gain", 1.0)
                offset = cal.get("offset", 0.0)
                if "rms_error_mv" in cal:
                    error = cal["rms_error_mv"]
                    unit = "mV"
                else:
                    error = cal.get("rms_error_ma", 0.0)
                    unit = "mA"

                line = f"{channel}: gain={gain:.6f}, offset={offset:.6f}, error={error:.1f}{unit}"
                # Show quadratic coefficients if present
                a = cal.get("quad_a", 0.0)
                b = cal.get("quad_b", 0.0)
                c = cal.get("quad_c", 0.0)
                if a != 0.0 or b != 0.0 or c != 0.0:
                    line += f"\n  quad: {a:.6f}*V^2 + {b:.4f}*V + {c:.2f} mV"
                summary.append(line)
        
        return "\n".join(summary)
    
    def is_calibrated(self, channel=None):
        """Check if calibration data exists for a channel (or any channel if None)"""
        if channel is None:
            # Check if any channel is calibrated (non-default values)
            for ch in ["vout_adc", "vin_adc", "iout_adc", "iin_adc", "switch_vsense"]:
                if ch in self.data:
                    cal = self.data[ch]
                    if cal.get("gain", 1.0) != 1.0 or cal.get("offset", 0.0) != 0.0:
                        return True
            return False
        else:
            # Check specific channel
            if channel not in self.data:
                return False
            cal = self.data[channel]
            return cal.get("gain", 1.0) != 1.0 or cal.get("offset", 0.0) != 0.0
    
    def diagnose_files(self):
        """Diagnose calibration file issues and provide repair suggestions"""
        import os
        print("=== Calibration File Diagnosis ===")
        
        # Check main file
        try:
            stat = os.stat(self.filename)
            print(f"Main file ({self.filename}): {stat[6]} bytes")
            if stat[6] == 0:
                print("  WARNING: Main file is empty!")
            
            with open(self.filename, 'r') as f:
                content = f.read()
                if len(content) > 0:
                    try:
                        data = json.loads(content)
                        if self._validate_calibration_data(data):
                            print("  Main file: Valid JSON structure")
                        else:
                            print("  Main file: Invalid calibration data structure")
                    except:
                        print("  Main file: Invalid JSON syntax")
                else:
                    print("  Main file: Empty file")
        except OSError:
            print(f"Main file ({self.filename}): Does not exist")
        
        # Check backup file
        backup_file = self.filename + '.bak'
        try:
            stat = os.stat(backup_file)
            print(f"Backup file ({backup_file}): {stat[6]} bytes")
            
            with open(backup_file, 'r') as f:
                content = f.read()
                if len(content) > 0:
                    try:
                        data = json.loads(content)
                        if self._validate_calibration_data(data):
                            print("  Backup file: Valid - can be used for recovery")
                        else:
                            print("  Backup file: Invalid calibration structure")
                    except:
                        print("  Backup file: Invalid JSON syntax")
        except OSError:
            print(f"Backup file ({backup_file}): Does not exist")
        
        # Check temp file (shouldn't exist normally)
        temp_file = self.filename + '.tmp'
        try:
            stat = os.stat(temp_file)
            print(f"WARNING: Temp file ({temp_file}): {stat[6]} bytes - leftover from failed save")
        except OSError:
            pass  # Good - temp file shouldn't exist
            
    def repair_from_backup(self):
        """Attempt to repair main calibration file from backup"""
        backup_file = self.filename + '.bak'
        try:
            with open(backup_file, 'r') as f:
                backup_data = json.load(f)
            
            if self._validate_calibration_data(backup_data):
                with open(self.filename, 'w') as f:
                    json.dump(backup_data, f)
                print(f"Successfully repaired {self.filename} from backup")
                self.load()  # Reload the repaired data
                return True
            else:
                print("Backup file contains invalid data - cannot repair")
                return False
        except Exception as e:
            print(f"Failed to repair from backup: {e}")
            return False