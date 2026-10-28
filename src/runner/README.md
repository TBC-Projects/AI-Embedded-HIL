# Runner

Future concrete build and hardware execution boundary on the machine with access
to the bench. This directory is currently documentation only: no runner service,
compiler, uploader, or hardware operations are implemented.

The runner will eventually:

- Accept firmware source or a build artifact through an interface to be agreed.
- Compile firmware if assigned that responsibility.
- Upload and start firmware on the Raspberry Pi.
- Collect UART output and available FPGA traces.
- Handle timeouts, reset, and recovery.
- Return structured build output, execution feedback, and test evidence to orchestration.

The Pi executes firmware. A separate FPGA captures connected digital signals and
explicitly emitted debug milestones; it cannot inspect arbitrary program state.
Orchestration owns model calls, agent revisions, and retries. Runner does not call
the model or manage the agent loop. Dashboard code lives in `src/dashboard/`.

## Unresolved interfaces

Agree these with the hardware owners before implementation:

- Build ownership: orchestration, runner, or another build component.
- Binary format and source/artifact handoff.
- Upload and start protocol.
- Reset mechanism and recovery procedure.
- Serial configuration.
- FPGA capture/trace retrieval protocol.
- Structured result format, including timeouts and infrastructure errors.

An unavailable device means unable to test; a missing expected UART message in a
valid capture is a test failure. Do not turn an infrastructure error into a test
failure or a simulated success.

The existing Week 5–8 roadmap discusses a cross-compiler, linker script, polling
queue, UART handshake/CRC32, and watchdog/reset. These are proposals, not agreed
protocols or implemented interfaces. Target firmware/bootloader work belongs in
`src/target/`; FPGA logic belongs in `src/fpga/`. No protocol is assumed by this MVP.

Orchestration and runner need not be separate services initially. Accessing a
teammate's hardware remotely may later require a reachable runner service; network
transport, access controls, and bench connectivity remain to be designed.
