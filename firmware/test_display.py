import st7789_purefb as st7789
import time

"""
    st7789 framebuffer driver demo for ST7789 SPI displays
    https://github.com/easytarget/st7789-framebuffer
"""

from machine import Pin, PWM, SPI

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

display.fill(st7789.BLACK)

def demo1():
    print('init done, running demo')

    for i in range(10):
        print('black')
        display.fill(st7789.BLACK)
        display.text("Hello", 10, 10)
        display.show()
        time.sleep(0.5)
        print('red')
        display.fill(st7789.RED)
        display.text(f"World {i}", 10, 10)
        display.show()
        time.sleep(0.5)
