# FPGA

`pintrace6` for the Basys 3.

* Week 5: Synthesize for the Basys 3. The synthesis tool is not chosen yet. Check the 100 MHz timestamp counter, rising/falling-edge trigger, and circular BRAM buffer in a testbench or with a waveform generator.
* Week 6: Capture registers framed over the board's built-in USB-UART, since the Basys 3 has no onboard processor. The host side of that link lives in `src/capture-host/`, run on the Runner PC.
* Week 7: Inputs are the six Pi strobes and ground on a PMOD header. Pin numbers go in `doc/hardware.md`.

The capture core has to be able to observe SPI, I2C, UART, PWM, and GPIO. Week 7 only requires the GPIO strobes.
