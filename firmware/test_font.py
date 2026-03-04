import st7789_purefb as st7789
import time
from machine import Pin, PWM, SPI, Timer

from ezFBfont import ezFBfont
import ezFBfont_10x20_ascii_17 as fixed_font_data
import ezFBfont_helvR24_latin_38 as helvetica_font_data
import random
from array import array

dis_clk = Pin(2)
dis_tx = Pin(3)
#dis_rx = Pin(4) # Not used
dis_reset = Pin(6, Pin.OUT)
dis_dc = Pin(7, Pin.OUT, value=1)
dis_cs = Pin(8, Pin.OUT, value=1)
dis_bl = Pin(9, Pin.OUT, value=0)

dis_bl_pwm = PWM(dis_bl, duty_u16=0x0)

spi0 = SPI(0,
           sck=dis_clk, mosi=dis_tx, miso=None,
           phase=0, polarity=0,
           baudrate=30000000)

# There parameters and the setting of non inverting mode are required
# to get the 76x284 display working
display = st7789.ST7789_SPI(spi0,
                            width=76,
                            height=284,
                            reset=dis_reset,
                            cs=dis_cs,
                            dc=dis_dc,
                            backlight=dis_bl_pwm,
                            rotation=1,
                            color_order=st7789.BGR,
                            reverse_bytes_in_word=True
                            )

fixed_font = ezFBfont(display, fixed_font_data, fg=st7789.WHITE)
helvetica_font = ezFBfont(display, helvetica_font_data, fg=st7789.WHITE)

right_arrow = array('h', [
    0, 5,
    15, 5,
    15, 10,
    25, 0,
    15, -10,
    15, -5,
    0, -5
])

uptime = 0

v1 = 5.0
a1 = 1.0
v2 = 5.0
a2 = 1.0

def show_booting():
    global uptime
    n_dots = uptime % 10
    display.fill(st7789.BLACK)
    fixed_font.write('Booting' + '.' * n_dots, 0, 10)
    display.show()
    uptime += 1

def update_display():
    #t_start = time.time_ns()

    display.fill(st7789.BLACK)
    helvetica_font.write(f'{v1:.3f}V', 0, 0)
    helvetica_font.write(f'{a1:.3f}A', 0, 35)
    helvetica_font.write(f'{v2:.3f}V', 150, 0)
    helvetica_font.write(f'{a2:.3f}A', 150, 35)

    display.poly(110, 35, right_arrow, st7789.GREEN, f=True)

    display.show()
    t_end = time.time_ns()

    #t_delta_ms = (t_end - t_start) / 1e6
    #print(f"Display update took {t_delta_ms}ms")

def _poll(t):
    # Will be replace with the actual measurements
    global v1, a1, v2, a2
    v1 += (random.random() - 0.5) * 0.01
    a1 += (random.random() - 0.5) * 0.01
    v2 += (random.random() - 0.5) * 0.01
    a2 += (random.random() - 0.5) * 0.01

    update_display()

#show_booting()
# See if we can update the display from a timer?
poll_timer = Timer()
poll_timer.init(mode=Timer.PERIODIC, period=100, callback=_poll)
