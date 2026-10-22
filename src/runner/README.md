# Runner

Daemon on the machine that owns the debug cable.

* Week 5: Bare-metal cross-compiler and custom linker script. Toolchain packaging is not chosen yet. The bootloader those binaries boot through is in `src/target/`.
* Week 6: Poll the job queue, compile, and run the UART flash handshake with CRC32.
* Week 8: Watchdog and timeout so a hung image cannot hold the queue. Pulse a hardware reset or power-cycle on panic.

The orchestrator enqueues source. This process is the flasher.
