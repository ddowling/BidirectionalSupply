# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
import board
from display import display_error

try:
    board.setup()

    board.monitor(True)
except Exception as e:
    board.monitor(False)
    display_error(str(e))
