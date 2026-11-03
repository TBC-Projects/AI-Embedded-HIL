# Capture host daemon

Host process on the Runner PC, not on the FPGA — the Basys 3 has no onboard processor or Linux image. The service stack is not chosen yet. It talks to `pintrace6` over the board's built-in USB-UART and serves capture registers to the orchestrator.

| Function | Role |
| --- | --- |
| Status | Capture core state |
| Arm | Arm the trigger |
| Capture | Run a capture |
| Trace | Return the timestamped trace |

How these are exposed is not chosen yet. Week 7 exit check reads the trace over the USB-UART link and shows timestamps for the Pi GPIO toggles. The analyzer in `src/orchestration/` is the client.
