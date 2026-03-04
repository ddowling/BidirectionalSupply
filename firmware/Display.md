I have a couple of cheap 2.25" ST7789 RGB displays that I would like to use on this project. They are 284 x 76 pixel resolution.

https://www.ebay.com.au/itm/205521286472
https://www.aliexpress.com/item/1005008937314193.html

Initially I will just use a pure micropython based library but I do want the
ability to choose different fonts from the default 8x8 font provided by the
MicroPython FrameBuffer class.

I adapted a driver by Salvatore Sanfilippo based on originally from https://github.com/devbis/st7789py_mpy

The only real change is to support the 284x76 resolution:
```
        elif (self.width, self.height) == (76, 284):
            self.xstart = 82
            self.ystart = 18
        elif (self.width, self.height) == (284, 76):
            self.xstart = 18
            self.ystart = 82
```

I found another repository at https://github.com/easytarget/st7789-framebuffer
It seems to have similar SPI code but works on a full framebuffer which is
possible in my application as I have enough RAM on the RP2350.

This repository recommends the microPyEZfonts repository for font handling
      https://github.com/easytarget/microPyEZfonts

