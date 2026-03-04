I have a couple of cheap 2.25" ST7789 RGB displays that I would like to use on this project. They are 284 x 76 pixel resolution.

https://www.ebay.com.au/itm/205521286472
https://www.aliexpress.com/item/1005008937314193.html

I found some good driver code from the repository at https://github.com/easytarget/st7789-framebuffer
It uses SPI to dump the full framebuffer to the display. This is most suitable in my application as I have enough RAM on the RP2350.

This repository recommends the microPyEZfonts repository for font handling
      https://github.com/easytarget/microPyEZfonts

I will clone this repository into the firmware directory and see if I can use something like symbolic links to just install the fonts required onto the device.



