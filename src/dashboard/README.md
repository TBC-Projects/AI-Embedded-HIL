# Dashboard

React + TypeScript + Vite page for a live firmware run. This MVP is entirely
browser-local and works without Python. Node.js 22.14+ and npm are recommended.

```sh
cd src/dashboard
npm ci
npm run dev
```

Open the URL printed by Vite (normally http://127.0.0.1:5173).

```sh
npm run typecheck
npm run build
npm test
```

## What is simulated

Run plays a fixed UART example regardless of the task text. Attempt 1 sends Hello
once and fails because two expected messages are missing. A scripted revision adds
a loop and a delay; attempt 2 passes. Compiler output, agent action summaries,
UART captures, tests, and the sample diff are all simulated. No files are edited,
model called, firmware compiled, or device accessed. The device always says
Disconnected. Stop cancels pending updates and preserves only evidence already
seen; a new run starts fresh. Timestamps are local playback times, not hardware
measurement times. The sample diff illustrates intent; it is not compilable firmware.

`src/workflow.ts` defines the replaceable workflow interface, typed events and
results. Execution status is separate from test outcome. `src/mockWorkflow.ts`
implements the complete simulation; `src/App.tsx` renders it. The page accepts a
Workflow prop so a future transport can be supplied without replacing the UI.
No API client or network integration is implemented. Future infrastructure failures
must return “unable to test”; observed behavior mismatches return “failed”.

The dashboard displays action summaries and tool results, never private model
reasoning. Future agent workflow belongs in `src/orchestration/`; concrete build
and hardware operations belong in `src/runner/`. A waveform viewer is outside this
MVP's scope.
