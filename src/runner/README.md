# Runner

Concrete build and hardware execution boundary for the machine attached to the
bench. The compile half is implemented; the upload/flash/trace half is not.

## Compile tool (`compile.py`)

Turns one firmware workspace into the two files the rest of the system needs.
It runs exactly the command `src/build/build.py` documents (same `CFLAGS`, same
outputs), so the two cannot drift silently.

```
python src/runner/compile.py <workspace>          # human summary
python src/runner/compile.py <workspace> --json   # everything, machine readable
```

### Workspace layout

```
workspace/
    start.S  hil.c  hil.h  linker.ld     fixed support layer, copied from src/build/target/
    src/*.c                              the agent's code
```

`kernel.elf`, `kernel.bin` and `build.log` are written into the workspace root.
`src/build/target/` is the single source of truth for the fixed files; the
harness copies them in and the agent never edits them.

### Outputs

| File | Consumer |
|---|---|
| `kernel.elf` | the QEMU gate boots this |
| `kernel.bin` | flat image; the UART bootloader receives exactly these bytes |
| `build.log` | the command line plus the full compiler output, for humans |

The result is a `CompileResult` dataclass: `ok`, `status`, `summary`,
`diagnostics` (trimmed to 40 lines / 4000 chars), `artifact_id`, `elf`, `binary`,
`size`, `crc32`, `duration_s`, `command`. `artifact_id` is `kernel-<crc32>` —
the same checksum the `HIL1` upload header carries.

### Statuses and blame

| status | blame | meaning |
|---|---|---|
| `ok` | — | image built |
| `compile_error`, `link_error`, `too_large`, `no_sources` | code | send `diagnostics` back to the model |
| `missing_linker_script`, `toolchain_missing`, `timeout`, `objcopy_failed` | rig | retry without spending a repair budget |

Old `kernel.elf` / `kernel.bin` are deleted before every build, so a failed
build can never leave a stale image for the uploader to flash.

### Verification

```bash
arm-none-eabi-gcc -print-libgcc-file-name    # must print a real path
arm-none-eabi-gcc --version                  # 14.2.1 works
```

On Windows PowerShell, quote the argument (`'-print-file-name=libgcc.a'`) or
use `cmd`; unquoted, PowerShell mangles the `=` and gcc prints a bogus value.

## Not implemented yet

- Upload/start over the Pi's UART bootloader (`HIL1 + length + crc32`).
- FPGA trace retrieval (`A`/`S`/`D` commands).
- Reset and watchdog recovery.
- The long-running job service; today `compile.py` is a library plus a CLI.

`src/build/runner.py` is the separate D4 teaching deliverable for the flash
path; until it exists, the compile stage is the only hardware-adjacent code.

## Boundaries

The Pi executes firmware. A separate FPGA captures connected digital signals and
explicitly emitted debug milestones; it cannot inspect arbitrary program state.
Orchestration owns model calls, agent revisions and retries. The runner does not
call the model and does not manage the agent loop; dashboard code lives in
`src/dashboard/`.

Build ownership is now settled: the runner compiles, the build stage (`D2`)
wraps it. Remaining unresolved interfaces are the upload protocol, reset
procedure, serial configuration and the structured trace format.

An unavailable device means "unable to test"; a missing expected UART message in
a valid capture is a test failure. Do not turn an infrastructure error into a
test failure or a simulated success.
