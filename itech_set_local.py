# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
from itech_serial import IT8500
l = IT8500("/dev/ttyUSB0")
l.identify()
l.control_set_local()
