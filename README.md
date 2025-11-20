This is a design for a Bidirectional Buck-Boost DC-DC converter based on the Texas Instruments [BQ25758](https://www.ti.com/lit/ds/symlink/bq25758.pdf) integrated circuit. 
The BQ25758 has a wide supply range from 4.2V to 60V and the external MOSFETs and Inductor should support currents up to 10A. This design is closely based on the 
[BQ25758 Evaluation Module](https://www.ti.com/lit/ug/sluucd0b/sluucd0b.pdf?ts=1762398106820&ref_url=https%253A%252F%252Fwww.ti.com%252Ftool%252FBQ25758EVM). I decided to spin my own board as I
wanted to add a microcontroller and four Ideal Diodes with load switches to make a completely standalone board. 

I am interested in using this circuit as a DC UPS, Battery Charger and Solar MPPT. I have used various purpose build modules previously but I have often run into limitations due to their fixed 
function design and closed firmware.

The BQ25758 I<sub>2</sub>C interface is connected to an on-board RP2350 and there are 4 Ideal-Diode switches also connected to the RB2350. All of the high current connections are brought out to
pluggable terminal blocks so it is possible to reconfigure the circuit to accomodate different use cases. 
Having the ability to switch the DC-DC converter direction means that the system bus voltage can be decoupled from the battery voltage.

I was originally going to use a STM32 for the board microcontroller as I have used these on a lot of previous designed but when I started looking at battery capacity tracking algorithms I noted
that the more advanced employed an Unsented Kalman Filter and required the use of an Equivalent Circuit Model for the battery. I decided to opt for the
[RP2350](https://pip-assets.raspberrypi.com/categories/1214-rp2350/documents/RP-008373-DS-2-rp2350-datasheet.pdf?disposition=inline) with its hardware floating point and
the ability to run MicroPython as I figure this will be easier to iterate the firmware and run experiments on the board. Using MicroPython allow writing log files to the flash memory to
allow continous logging of battery voltage, current and temperature. This data can then be processed either on the board or remotely to allow a battery model to be fitted to actual
battery performance.

