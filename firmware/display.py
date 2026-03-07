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
                            color_order=st7789.BGR,
                            reverse_bytes_in_word=True
                            )

fixed_font = ezFBfont(display, fixed_font_data,
                      fg=WHITE, cswap=True)

helvetica_font = ezFBfont(display, helvetica_font_data,
                          fg=WHITE, cswap=True)

right_arrow = array('h', [
    0, 5,
    15, 5,
    15, 10,
    25, 0,
    15, -10,
    15, -5,
    0, -5
])

def display_blank():
    display.fill(BLACK)
    display.show()

def display_convertor_info(context):
    '''
    Display convertor voltages and currents
    context is an dictionary like class that looks up some
    predefined quantities
    '''
    #t_start = time.time_ns()

    display.fill(BLACK)
    helvetica_font.write(f'{context['vin']:.3f}V', 0, 0)
    helvetica_font.write(f'{context['iin']:.3f}A', 0, 35)
    helvetica_font.write(f'{context['vout']:.3f}V', 150, 0)
    helvetica_font.write(f'{context['iout']:.3f}A', 150, 35)

    # FIXME This needs to show converter direction
    arrow_offset = int(time.ticks_ms()/100) % 10
    display.poly(110 + arrow_offset, 35,
                 right_arrow, GREEN, f=True)

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
    for i, line in enumerate(lines):
        fixed_font.write(line, 0, i * char_h)

    display.show()

