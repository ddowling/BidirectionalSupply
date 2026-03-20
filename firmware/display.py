from ezFBfont import ezFBfont
from machine import Pin, PWM, SPI
import st7789_purefb as st7789
from st7789_purefb import (
    BLACK,
    BLUE,
    RED,
    GREEN,
    CYAN,
    MAGENTA,
    YELLOW,
    WHITE)

import ezFBfont_10x20_ascii_17 as fixed_font_data
import ezFBfont_helvR24_latin_38 as helvetica_font_data

from array import array
import time

dis_spi = SPI(0,
              sck=Pin(6), mosi=Pin(7), miso=None,
              phase=0, polarity=0,
              baudrate=30000000)
dis_reset = Pin(4, Pin.OUT)
dis_dc = Pin(10, Pin.OUT, value=1)
dis_cs = Pin(5, Pin.OUT, value=1)
dis_bl_pwm = PWM(Pin(11), freq=100_000, duty_u16=0x0)

# Parameters for the 76x284 display
display = st7789.ST7789_SPI(dis_spi,
                            width=76,
                            height=284,
                            reset=dis_reset,
                            cs=dis_cs,
                            dc=dis_dc,
                            backlight=dis_bl_pwm,
                            bright=0.6, # 1.0=full_off 0.0=full_on
                            rotation=1,
                            color_order=st7789.BGR
                            )

fixed_font = ezFBfont(display, fixed_font_data, fg=WHITE)

helvetica_font = ezFBfont(display, helvetica_font_data, fg=WHITE)

right_arrow = array('h', [
    0, 5,
    15, 5,
    15, 10,
    25, 0,
    15, -10,
    15, -5,
    0, -5
])

left_arrow = array('h', [
    25, 5,
    10, 5,
    10, 10,
    0, 0,
    10, -10,
    10, -5,
    25, -5
])

def display_blank():
    display.fill(BLACK)
    display.show()

def display_convertor_info(context):
    '''
    Display convertor voltages and currents
    context is a BoardContext providing lazy-evaluated measurements
    '''
    #t_start = time.time_ns()

    display.fill(BLACK)
    fixed_font.bg = BLACK
    helvetica_font.bg = BLACK

    helvetica_font.write(f'{context.get("vin"):.2f}V', 0, 0)
    helvetica_font.write(f'{context.get("iin"):.2f}A', 0, 35)
    helvetica_font.write(f'{context.get("vout"):.2f}V', 150, 0)
    helvetica_font.write(f'{context.get("iout"):.2f}A', 150, 35)

    if context.get('enabled'):
        arrow_offset = int(time.ticks_ms() / 100) % 10
        if context.get('reverse_enable'):
            display.poly(120 - arrow_offset, 35, left_arrow, GREEN, True)
        else:
            display.poly(110 + arrow_offset, 35, right_arrow, GREEN, True)

    char_w = fixed_font._font.max_width()
    char_h = fixed_font._font.height()

    mode = context.get('regulation_mode')
    mode_color = GREEN if mode == 'CV' else YELLOW if mode == 'CC' else WHITE
    fixed_font.fg = mode_color
    fixed_font.write(mode, display.width - len(mode) * char_w, 0)
    fixed_font.fg = WHITE

    charger_state = context.get('charger_state')
    if charger_state:
        fixed_font.write(charger_state,
                         display.width - len(charger_state) * char_w,
                         char_h)

    display.show()

    #t_end = time.time_ns()
    #t_delta_ms = (t_end - t_start) / 1e6
    #print(f"Display update took {t_delta_ms}ms")

def _wrap_words(text, chars_per_line):
    """Split text into lines fitting within chars_per_line, breaking on spaces."""
    words = text.split()
    lines = []
    line = ''
    for word in words:
        if len(line) == 0:
            line = word
        elif len(line) + 1 + len(word) <= chars_per_line:
            line += ' ' + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

def display_error(message):
    display.fill(RED)

    fixed_font.bg = RED
    fixed_font.fg = WHITE

    char_w = fixed_font._font.max_width()
    char_h = fixed_font._font.height()
    chars_per_line = display.width // char_w

    lines = _wrap_words(message, chars_per_line)
    total_h = len(lines) * char_h
    y0 = (display.height - total_h) // 2
    for i, line in enumerate(lines):
        x = (display.width - len(line) * char_w) // 2
        fixed_font.write(line, x, y0 + i * char_h)

    display.show()

