# Dashboard

React + TypeScript + Vite frontend for the local firmware agent. A conversation
sidebar selects saved chats. Each turn shows your prompt, a chronological
backend/QEMU log, and the Markdown answer. One run can be active globally.

## Start locally

First start the backend from the repository root in one terminal:

```sh
export GOOGLE_API_KEY='your-key'
./.venv/bin/python -m pip install -r src/orchestration/requirements.txt
./.venv/bin/python -m uvicorn src.orchestration.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal (Node.js 22.14+ and npm):

```sh
cd src/dashboard
npm ci
npm run dev
```

Open the Local URL printed by Vite (normally http://127.0.0.1:5173). Click New conversation, then send “Do not use tools. Say Hello.” Or click
Use QEMU example to fill the composer with a compile/QEMU task.
Python dependencies, an API key, and model access are required for agent work.
The compile/QEMU example also needs arm-none-eabi-gcc, arm-none-eabi-objcopy,
and qemu-system-arm; see the orchestration README. The API key stays on the backend.

Vite forwards `/api/*` to http://127.0.0.1:8000 for both dev and preview. No CORS
configuration or separate frontend environment variables are needed locally.
A production static server would need the equivalent proxy; no deployment is set up.

## What happens

Send POSTs the prompt to `/api/tasks/stream` with the selected chat ID and a new run ID. The response is
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

Send is disabled while a request is active. Stop calls the backend Stop endpoint
and waits for cleanup. Closing/unmounting the page aborts the stream, which cancels
the server run. QEMU child processes are stopped; a compiler already running in
its worker thread is allowed to finish before the shared workspace is released.
The backend also rejects another active run from a second tab or curl client.
Errors stay in the log; no final answer is invented for failed or stopped runs.

Gemini calls, file writes, compilation, and QEMU are real. Physical flashing remains
simulated; no Pi or FPGA is contacted. Generated files remain in
`src/orchestration/workspaces/` across all chats. Switching chats does not restore
old files. Sessions, prompts, answers, and logs persist in the backend SQLite file
`src/orchestration/data/conversations.db`. Install the updated Python requirements;
there is no separate database to install. A follow-up uses the selected chat's
saved ADK context; a new chat has separate context but shares the files.

The sidebar title comes from the first message. Select any chat to reload its
history, or expand a turn's Activity log to inspect earlier tool/QEMU output.
Deleting a chat removes only its history, never workspace files. Switching chats
during a run keeps it running; the composer stays disabled until that run ends.
Closing/reloading the streaming tab stops the run, preserving its logs. There is
no automatic retry, retention limit, or context compaction.

## Checks

```sh
npm run typecheck
npm run build
npm test
```

Tests verify stream decoding, events before EOF, request errors, Stop targeting,
chat API calls, follow-up IDs, and history/stream merging without duplicate logs.
