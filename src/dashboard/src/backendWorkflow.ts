import type { StreamEvent } from './workflow';

// HTTP chunks can split a JSON line or even a UTF-8 character anywhere.
export async function readEvents(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      const lines = pending.split('\n');
      pending = lines.pop() ?? '';
      for (const line of lines) {
        if (line.trim()) onEvent(JSON.parse(line) as StreamEvent);
      }
      if (done) break;
    }
    if (pending.trim()) onEvent(JSON.parse(pending) as StreamEvent);
  } finally {
    reader.releaseLock();
  }
}

async function requireSuccess(response: Response): Promise<void> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string'
      ? body.detail : `Backend request failed (HTTP ${response.status}).`);
  }
}

export async function streamTask(
  task: string,
  runId: string,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/tasks/stream?run_id=${encodeURIComponent(runId)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task }), signal,
  });
  await requireSuccess(response);
  if (!response.body) throw new Error('The backend returned no log stream.');
  await readEvents(response.body, onEvent);
}

export async function stopTask(runId: string): Promise<boolean> {
  const response = await fetch(`/api/tasks/${encodeURIComponent(runId)}/stop`, { method: 'POST' });
  // The run can finish naturally just before Stop reaches the server.
  if (response.status !== 404) await requireSuccess(response);
  return response.status !== 404;
}
