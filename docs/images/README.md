# Images

Photos used by the documentation. Only add images you took yourself or that
carry a license compatible with MIT, and name the source here and in the commit
message.

| File | Used in | What it shows | Source |
|---|---|---|---|
| `icon.png` | README | The integration icon (copy of `custom_components/triki/brand/icon.png`). | this project |
| `triki-front.jpg` | README, hardware.md | The token from above: silver cap, black T. | [Flopsstuff/triki](https://github.com/Flopsstuff/triki) `assets/1.jpg`, © 2026 Flopsstuff, MIT |
| `triki-back.jpg` | README, hardware.md | The underside: green board with the Ż logo. | Flopsstuff/triki `assets/2.jpg`, MIT |
| `triki-axes.jpg` | README, hardware.md | The token with the sensor's X, Y, Z axes drawn in. | Flopsstuff/triki `assets/axes.jpg`, MIT |
| `open-1-tool.svg` … `open-4-cell.svg` | hardware.md | **Placeholders.** The four steps of opening the cap and taking the CR2032 out: tool and token; lifting the green part at the rim; the open token with the cell in place (which side up); the cell out and the contacts. Replace each with a `.jpg` of the same name and update the links. | wanted |

The Flopsstuff photos are stored in Git LFS upstream, which is why they are
copied here instead of linked: a raw GitHub link to an LFS file returns the
pointer text, not the image.

Linked, not copied: the board photo, the chip photo and the reference schematic
in `hardware.md` come from
[Piwencjusz/zabka-triki-hardware](https://github.com/Piwencjusz/zabka-triki-hardware),
which has no license file. Do not copy them here unless the authors grant one.
The same goes for [DISKIMG/Triki-PCB](https://github.com/DISKIMG/Triki-PCB).
The cap renders in [koksny/TRIKI-Control](https://github.com/koksny/TRIKI-Control)
(MIT) are generic bottle caps and were not used.

Still wanted (see the table in the first version of this file for ideas):
a side view with the LED window, a board photo with the chips readable, an
ESP32 proxy next to the spot where the token is used, a screenshot of the
device page in Home Assistant after the first connection, and a short photo
series of opening the cap and lifting out the CR2032 (which tool, where to
start, which way the cell faces) for
[hardware.md](../hardware.md#opening-it-and-the-battery). Keep photos under
500 kB (`convert in.jpg -resize 1600x -quality 82 out.jpg`).
