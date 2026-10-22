# Hardware

Active boards for this quarter are the **PYNQ-Z2** and **Raspberry Pi Zero W** targets. The DE1-SoC is the alternate FPGA on the parts list. The FT2232H is the debug adapter on the parts list. The flash path in the Week 5–6 plan is the Pi UART bootloader.

## Parts

1. FPGA - PYNQ-Z2 (Xilinx Zynq-7000) or DE1-SoC
2. Target microcontrollers - Raspberry Pi Zero W
3. Prototyping hardware - breadboards, jumper wires, logic level shifters
4. Debug interface - FT2232H USB-to-JTAG/UART adapter

## What each board is for

| Board | Role |
| --- | --- |
| PYNQ-Z2 | Runs `pintrace6`. The Zynq ARM (processing system) hosts the capture service. Programmable logic holds the 100 MHz counter, edge trigger, and circular BRAM. |
| Pi Zero W | Runs the generated bare-metal image from RAM. Two boards are on the list so one can stay wired while the other is bring-up or a spare. |
| FT2232H | USB adapter for JTAG and UART debug. |
| Level shifters, breadboard, jumpers | Bench wiring between the Pi and the FPGA headers. |

The FPGA is specified to watch SPI, I2C, UART, PWM, and GPIO. The first integration milestone uses GPIO only: six strobes.

## Week 7 wiring

Leads 2 and 3 connect the benches. The plan names the signals. Fill the pin columns when the headers are chosen, and keep that map in this file so the dashboard and the trace analyzer use the same names.

Connect:

* Six Pi Zero W GPIO pins used as milestone strobes
* One shared ground
* PYNQ-Z2 PMOD or Arduino headers into `pintrace6`

| Strobe | Pi Zero W pin | PYNQ-Z2 header pin | `pintrace6` input | Notes |
| --- | --- | --- | --- | --- |
| 0 | | | | |
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| GND | | | | Common ground |

Week 7 exit check: after the runner flashes a C program that toggles these strobes, read the PYNQ trace and confirm the captured timestamps line up with those edges.

## Clocks and buffers

| Item | Spec |
| --- | --- |
| Timestamp counter | 100 MHz |
| Trigger | Rising edge or falling edge |
| Storage | Circular buffer in BRAM |
| Host registers | AXI-Lite, mapped with `/dev/mem` on the PYNQ |
| Host service | Status, arm, capture, and trace. The interface is not chosen yet. |

## Boot and recovery

| Path | Behavior |
| --- | --- |
| Normal flash | Runner sends a compiled binary over UART. Bootloader checks CRC32 and branches into RAM. The SD card stays inserted. |
| Hang or panic | Runner watchdog times out and pulses a reset or power-cycle to the Pi, then the job can be retried. |

Add the reset-line pins to the wiring table when the circuit is built.
