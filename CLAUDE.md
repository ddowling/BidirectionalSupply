# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BidirectionalSupply is a bidirectional Buck-Boost DC-DC converter design based on the Texas Instruments BQ25758 IC. The system supports:
- Wide supply range (4.2V to 60V)
- Bidirectional power conversion up to 10A
- RP2350 microcontroller with MicroPython firmware
- Four Ideal Diode switches with load control
- ST7789 display support (284x76 pixels)
- I²C control interface
- DC UPS, Battery Charger, and Solar MPPT applications

## Architecture

### Hardware Components
- **Main Board**: KiCad PCB design with BQ25758 power management IC
- **Microcontroller**: RP2350 with floating point support running MicroPython
- **Display**: ST7789 RGB display (284x76 resolution) via SPI
- **Power Switches**: Four ideal diode switches with voltage sensing
- **Communication**: Two I²C buses (main converter + auxiliary devices)

### Firmware Structure
- **`firmware/main.py`**: Entry point that calls `board.monitor(True)`
- **`firmware/board.py`**: Hardware abstraction layer with pin definitions and device initialization
- **`firmware/BQ25758.py`**: Complete driver for the BQ25758 power management IC
- **`firmware/display.py`**: Display interface implementation
- **`firmware/st7789_*.py`**: ST7789 display drivers (base and extended versions)
- **`firmware/st7789-framebuffer/`**: Full framebuffer-based display library with font support

### Hardware Design Files
- **`hardware/*.kicad_*`**: KiCad schematic and PCB files
- **`hardware/BidirectionalSupply.pretty/`**: Custom KiCad footprint library
- **`hardware/NOTES.md`**: JLCPCB fabrication notes and part sourcing information

## Development Workflow

### Hardware Development
- PCB design uses KiCad with JLCPCB assembly
- Parts include JLCPCB part numbers (starting with "C") in schematic symbols
- Use `easyeda2kicad` tool for generating footprints from JLCPCB parts:
  ```bash
  pip install easyeda2kicad
  easyeda2kicad --lcsc_id C559500 --symbol --footprint --3d --project-relative --output hardware/BidirectionalSupply.kicad_sym
  ```

### Firmware Development
- **Platform**: MicroPython on RP2350
- **Entry Point**: `firmware/main.py` calls `board.monitor(True)` to start LED heartbeat
- **Hardware Setup**: Call `board.setup()` to initialize I²C buses and BQ25758
- **Key Classes**:
  - `BQ25758`: Complete register-level driver with voltage/current control
  - Display drivers support 284x76 ST7789 displays with custom fonts

### Pin Configuration (from board.py)
- **BQ25758 I²C**: SDA=Pin(0), SCL=Pin(1), INT=Pin(2), CE=Pin(3)
- **AUX I²C**: SDA=Pin(10), SCL=Pin(11)
- **Status LED**: Pin(8) with inverted logic
- **Ideal Diode Switches**: Enable pins 12-15, ADC sense pins 26-29
- **AUX SPI Header**: RX=Pin(4), CS=Pin(5), SCK=Pin(6), TX=Pin(7)

### Display Development
The active display driver is `st7789_purefb.py` (framebuffer-based) with `ezFBfont` for font rendering.
Display resolution is 284x76 with specific offset configuration for this hardware.

#### Font files
Font files (`ezFBfont.py`, `ezFBfont_*.py`) are copied directly into `firmware/` so that
`cp firmware/*.py <target>` deploys everything needed in one step. The upstream source is the
[microPyEZfonts](https://github.com/easytarget/microPyEZfonts) library — copy specific font files
from there into `firmware/` as needed. Do not use symlinks; keep real file copies so the repo is
self-contained and portable.

### Development Testing
- Use `board.setup()` to initialize all hardware
- Monitor BQ25758 status with `bq.get_status_str()` and `bq.get_fault_status_str()`
- Test ideal diode switches with `board.set_switch(n, state)` and `board.get_switch_vsense(n)`
- LED heartbeat indicates system activity via `board.monitor(True)`

## Key APIs

### BQ25758 Power Management
```python
# Basic setup
bq.setup()  # Initialize with default settings
bq.setup_adc()  # Enable ADC measurements

# Power control
bq.set_output_voltage_limit(voltage_v)
bq.set_output_current_limit(current_a)
bq.set_reverse_enable(True)  # Enable bidirectional mode

# Monitoring
voltage = bq.get_vout_adc()
current = bq.get_iout_adc()
status = bq.get_status_str()
```

### Ideal Diode Switch Control
```python
# Switch control (0-3)
board.set_switch(switch_num, True)  # Enable switch
enabled = board.get_switch(switch_num)
voltage = board.get_switch_vsense(switch_num)  # Read switch voltage
```

This system is designed for battery management, solar MPPT, and DC UPS applications with full bidirectional power flow control and comprehensive monitoring capabilities.

### Calibration
During testing is became apparent that the internal ADC in the BQ25758 is not very accurate. Some experiments have been performed to fit a parabolic curve to the measured voltage and current values when compared to an external IT8500 DC load.
See **`automated_calibration.py`** for the code to drive this calibration.
Have reached out to Texas Instruments for some more details and receoved the line that "The ADC of the BQ25750 is intended for use as a general indicator". See https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1616973/bq25758-voltage-readings-on-adc-low and 
https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1510781/bq25750-request-for-calculation-sheet 
The is an FAQ page for the BQ2575X parts at https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1357460/faq-bq2575x-faq-page?tisearch=e2e-sitesearch&keymatch=bq25750%252520adc#
