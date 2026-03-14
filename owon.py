#!/usr/bin/env python3

import serial

class Owon:

  SUPPORTED_DEVICES = {"OWON,SPE", "OWON,SPM", "OWON,P4","KIPRIM,DC"}

  def __init__(self, port="/dev/spm6103", default_timeout=0.5):
    self.ser = None
    self.port = port
    self.timeout = default_timeout

  def open(self):
    self.ser = serial.Serial(self.port, 115200, timeout=self.timeout)
    identity = self.read_identity()
    if not any([s in identity for s in self.SUPPORTED_DEVICES]):
      self.close()
      raise Exception("Not connected to a supported PSU!")

  def close(self):
    self.ser.close()

  def __enter__(self):
    self.open()
    return self

  def __exit__(self, *args, **kwargs):
    self.close()

  def _cmd(self, command, accept_silent=False, timeout=None):
    if self.ser == None:
      raise Exception("Connection is not open!")
    self.ser.write(bytes(command, 'utf-8') + b"\n")
    self.ser.timeout = timeout if timeout is not None else self.timeout
    ret = self.ser.readline().decode('utf-8', errors='ignore')
    ret = ret.strip()
    if len(ret) == 0 and not accept_silent:
      raise Exception(f"No response for command: '{command}'!")
    return ret

  def _silent_cmd(self, command, timeout=0.01):
    if self._cmd(command, accept_silent=True, timeout=timeout) == "ERR":
      raise Exception(f"Error while executing command: '{command}'")

  def read_identity(self):
    return self._cmd("*IDN?")

  # *RST command does not seem to do anything so skip

  def measure_voltage(self):
    return float(self._cmd("MEAS:VOLT?"))

  def measure_current(self):
    return float(self._cmd("MEAS:CURR?"))

  def measure_power(self):
    return float(self._cmd("MEAS:POW?"))

  def get_voltage(self):
    return float(self._cmd("VOLT?"))

  def get_current(self):
    return float(self._cmd("CURR?"))

  def get_voltage_limit(self):
    return float(self._cmd("VOLT:LIM?"))

  def get_current_limit(self):
    return float(self._cmd("CURR:LIM?"))

  def set_voltage(self, voltage):
    return self._silent_cmd(f"VOLT {voltage:.3f}")

  def set_current(self, current):
    return self._silent_cmd(f"CURR {current:.3f}")

  def set_voltage_limit(self, voltage):
    return self._silent_cmd(f"VOLT:LIM {voltage:.3f}")

  def set_current_limit(self, current):
    return self._silent_cmd(f"CURR:LIM {current:.3f}")

  def get_output(self):
    ret = self._cmd(f"OUTP?")
    if ret in ["0", "1"]:
      return ret == "1"
    elif ret in ["ON", "OFF"]:
      return ret == "ON"
    else:
      raise Exception(f"Unknown return for get output command: {ret}")

  def set_output(self, enabled):
    self._silent_cmd(f"OUTP {'ON' if enabled else 'OFF'}")

  def set_remote(self, enabled):
    if enabled:
      # Note: SYSTem:REMote does not work on P4603
      self._silent_cmd("SYST:REM")
    else:
      # Note: SYSTem:LOCal does not work on P4603
      self._silent_cmd("SYST:LOC")
