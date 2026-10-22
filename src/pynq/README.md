# PYNQ host daemon

Host process on the PYNQ-Z2 Linux image. The service stack is not chosen yet. It maps the `pintrace6` AXI-Lite registers with `/dev/mem` and serves them to the orchestrator.

| Function | Role |
| --- | --- |
| Status | Capture core state |
| Arm | Arm the trigger |
| Capture | Run a capture |
| Trace | Return the timestamped trace |

How these are exposed is not chosen yet. Week 7 exit check reads the trace and shows timestamps for the Pi GPIO toggles. The analyzer in `src/orchestration/` is the client.
