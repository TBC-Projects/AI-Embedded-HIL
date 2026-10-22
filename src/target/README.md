# Target firmware

Bare-metal code for the Raspberry Pi Zero W.

* Week 5: UART bootloader. Receive a precompiled binary over serial and execute it from RAM. Leave the SD card inserted.
* Week 7: A generated C image toggles six GPIO milestone strobes the FPGA can see.
* Week 9: Datasheet-driven drivers. Examples in scope are BCM2835 system-timer delays, mini-UART initialization, and interrupt handling.

Generated sources from the agent land here for the runner to compile. The runner itself is in `src/runner/`.
