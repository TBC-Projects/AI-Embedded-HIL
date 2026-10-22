# FPGA

`pintrace6` for the PYNQ-Z2.

* Week 5: Synthesize for the PYNQ-Z2. The synthesis tool is not chosen yet. Check the 100 MHz timestamp counter, rising/falling-edge trigger, and circular BRAM buffer in a testbench or with a waveform generator.
* Week 6: AXI-Lite registers the processing system can reach. The host side of that map lives in `src/pynq/`.
* Week 7: Inputs are the six Pi strobes and ground on a PMOD or Arduino header. Pin numbers go in `doc/hardware.md`.

The capture core has to be able to observe SPI, I2C, UART, PWM, and GPIO. Week 7 only requires the GPIO strobes.
