# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
import board
from display import display_error

board.monitor(True)

try:
    board.setup()
    board.load_startup()

except Exception as e:
    display_error(str(e))
