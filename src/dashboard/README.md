# Dashboard

React + TypeScript + Vite frontend for the local firmware agent. One prompt, one
active run, one chronological backend/QEMU log, and a final-answer panel. The old
fixed mock workflow, stage tracker, test evidence, and sample diff have been removed.

## Start locally

First start the backend from the repository root in one terminal:

```sh
export GOOGLE_API_KEY='your-key'
./.venv/bin/python -m uvicorn src.orchestration.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal (Node.js 22.14+ and npm):

```sh
cd src/dashboard
npm ci
npm run dev
```

Open the Local URL printed by Vite (normally http://127.0.0.1:5173). Run the
pre-filled compile/QEMU task, or begin with “Do not use tools. Say Hello.”
Python dependencies, an API key, and model access are required for agent work.
The compile/QEMU example also needs arm-none-eabi-gcc, arm-none-eabi-objcopy,
and qemu-system-arm; see the orchestration README. The API key stays on the backend.

Vite forwards `/api/*` to http://127.0.0.1:8000 for both dev and preview. No CORS
configuration or separate frontend environment variables are needed locally.
A production static server would need the equivalent proxy; no deployment is set up.

## What happens

Run POSTs the prompt to `/api/tasks/stream` with a new run ID. The response is
newline-delimited JSON. `backendWorkflow.ts` decodes lines incrementally, including
UTF-8 characters split across HTTP chunks. `App.tsx` appends log events and displays
the final-answer event. There are no separate stage/status events or status panels.

The log shows the same application activity printed by the backend: setup, model
requests/responses, tool calls/results, waiting messages, errors, and cleanup.
Long details are expandable. Captured QEMU UART text is displayed inline immediately
after its tool result, separately labeled from emulator diagnostics. This capture
arrives as a block after the observation window, not one character at a time.
A completed observation does not automatically mean the firmware passed a test.
Reading older entries pauses auto-follow until you scroll back near the bottom.

Run is disabled while a request is active. Stop calls the backend Stop endpoint
and waits for cleanup. Closing/unmounting the page aborts the stream, which cancels
the server run. QEMU child processes are stopped; a compiler already running in
its worker thread is allowed to finish before the shared workspace is released.
The backend also rejects another active run from a second tab or curl client.
Errors stay in the log; no final answer is invented for failed or stopped runs.

Gemini calls, file writes, compilation, and QEMU are real. Physical flashing remains
simulated; no Pi or FPGA is contacted. Generated files remain in
`src/orchestration/workspaces/` across requests. The session starts fresh each time.

## Checks

```sh
npm run typecheck
npm run build
npm test
```

Tests verify stream decoding, events before EOF, request errors, and Stop targeting.
