* I will be using JLCPCB for PCB, part sourcing and assembly.
* In the schematic symbol fields dialog I added an extra column for the JLCPCB part number. All of these parts should start with a "C".
* When the BOM is exported from KiCad it should be possible to import it directly into the JLCPCB BOM tool.
* Most of the footprints are obvious but things like the pushbutton switches are a specific layout. It is possible to convert from the JLCPCB part number to a footprint using the `easyeda2kicad` tool.

Install

    pip install easyeda2kicad


## BQ25758 IIN/IOUT Overcurrent Protection — Threshold Resistor Formula

The IIN and IOUT pins each have an internal transconductance amplifier that
converts the sense resistor voltage drop into a pin voltage used for OCP:

```
Vsense  = Isense × Rsense
Ipin    = Gm × Vsense
Vpin    = Ipin × Rpin        = Gm × Isense × Rsense × Rpin
Trip when Vpin ≥ Vthreshold  (Vthreshold = 2V, per datasheet)
```

Solving for the trip current limit:

```
Ilimit = Vthreshold / (Gm × Rsense × Rpin)
Rpin   = Vthreshold / (Gm × Rsense × Ilimit)
```

The IIN and IOUT pins have **different internal Gm values** (not documented in
the datasheet; determined by measurement). Both sense resistors are 5mR.

### IIN pin — Gm_in = 0.02 A/V (measured)

```
Ilimit = 2 / (0.02 × 5e-3 × Rpin) = 20000 / Rpin
Rpin   = 20000 / Ilimit
```

| Rpin   | Ilimit |
|--------|--------|
| 4990 Ω | ~4.0 A  (original board build — too low for 10A operation) |
| 2000 Ω | 10.0 A  (target; use 2kΩ E24 standard value)              |

**Action**: Replace the IIN pin resistor from 4990Ω to 2kΩ.

**Status (2026-03-14)**: Board #3 has been reworked with 2kΩ. Boards #1, #2, #4, #5
retain the original 4990Ω and will trip at ~4A in bypass mode — do not exceed
this when sweeping those boards until they are reworked.

### IOUT pin — Gm_out = 0.008 A/V (measured; = Gm_in × 2/5)

```
Ilimit = 2 / (0.008 × 5e-3 × Rpin) = 50000 / Rpin
Rpin   = 50000 / Ilimit
```

| Rpin   | Ilimit |
|--------|--------|
| 4990 Ω | ~10.0 A (original board build — already correct for 10A) |
| 5000 Ω | 10.0 A  (nominal) |

**No change needed** to the IOUT pin resistor — 4990Ω gives ≈10A as intended.

### The 2/5 factor

The ratio Gm_out/Gm_in = 2/5 matches the same factor that causes the IIN ADC
to read at 0.8mA/LSB instead of the datasheet value of 2mA/LSB. Both effects
stem from the BQ25758's internal circuits behaving differently on the input
versus output path when the input sense resistor is 5mR rather than the 2mR
assumed by much of the datasheet text.

---

## Ideal Diode Switch (LM74810) — Negative Voltage Spike Issue

Board #1 had LM74810 ideal diode circuits destroyed, suspected to be caused by
negative voltage spikes on the switch input/output nodes exceeding the absolute
maximum ratings of the GATE and CATHODE pins.

Board #2 has 100nF capacitors added on the input and output of each ideal diode
switch circuit. This appears to suppress the spikes sufficiently — board #2 is
working correctly under switching tests. Confirmed by circuit inspection.

For the next PCB revision:
- Add 100nF caps on input and output of each ideal diode switch circuit
- Add bidirectional TVS on the input to each switch to clamp transients
  before they reach the LM74810

---

## Test Equipment — udev Rules

The IT8511 DC load is assigned a persistent alias via udev so scripts always
find it at `/dev/it8511` regardless of USB enumeration order.

Create `/etc/udev/rules.d/99-instruments.rules`:

```
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", ATTRS{serial}=="6676201034", SYMLINK+="it8511", GROUP="dialout"
```

Reload rules:
```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

The Fluke 45 multimeter uses a Prolific PL2303 USB-serial adapter which has no
unique serial number, so matching by serial is not possible. Instead match on
the physical USB port path (KERNELS), which is stable as long as it is always
plugged into the same socket:

```
ACTION=="add", SUBSYSTEM=="tty", KERNELS=="<port_path>", SYMLINK+="fluke45", GROUP="dialout"
```

Find the port path with:
```bash
udevadm info -a -n /dev/ttyUSB0 | grep KERNELS | head -2
```

The RP2350 board enumerates as `/dev/ttyACM0` (no alias needed as only one
board is connected at a time).

---

## JLCPCB Fabrication

Grab footprint and 3d model

    easyeda2kicad  --footprint --3d --lcsc_id=C33222334
    easyeda2kicad --lcsc_id C559500 --symbol --footprint --3d --project-relative --output /mnt/hgfs/dpd/Documents/Open\ Source\ Solutions/BidirectionalSupply/hardware/BidirectionalSupply.kicad_sym

