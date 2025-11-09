* I will be using JLCPCB for PCB, part sourcing and assembly.
* In the schematic symbol fields dialog I added an extra column for the JLCPCB part number. All of these parts should start with a "C".
* When the BOM is exported from KiCad it should be possible to import it directly into the JLCPCB BOM tool.
* Most of the footprints are obvious but things like the pushbutton switches are a specific layout. It is possible to convert from the JLCPCB part number to a footprint using the `easyeda2kicad` tool.

Install

    pip install easyeda2kicad


Grab footprint and 3d model

    easyeda2kicad  --footprint --3d --lcsc_id=C33222334
    easyeda2kicad --lcsc_id C559500 --symbol --footprint --3d --project-relative --output /mnt/hgfs/dpd/Documents/Open\ Source\ Solutions/BidirectionalSupply/hardware/BidirectionalSupply.kicad_sym

