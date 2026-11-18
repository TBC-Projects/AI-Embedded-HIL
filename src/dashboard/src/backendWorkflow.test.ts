import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readEvents, stopTask, streamTask } from './backendWorkflow';
import type { StreamEvent } from './workflow';

const event = { type: 'log', run_id: 'one', timestamp: '2026-11-17T00:00:00Z', source: 'QEMU UART', message: 'Captured UART output', details: 'Hello 🌍\nHIL:DONE' } as const;

test('stream parser preserves split UTF-8, split lines, and ordered events', async () => {
  const final = { type: 'final', run_id: 'one', result: { session_id: 'one', model: 'test', workspace: '/tmp', final_response: 'Hello' } };
  const bytes = new TextEncoder().encode(`${JSON.stringify(event)}\n${JSON.stringify(final)}`);
  const body = new ReadableStream<Uint8Array>({ start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
    controller.close();
  } });
  const received: StreamEvent[] = [];
  await readEvents(body, value => received.push(value));
  assert.deepEqual(received, [event, final]);
});

test('events are delivered before the response finishes', async () => {
  let sender!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start(controller) { sender = controller; } });
  let notify!: () => void;
  const receivedOne = new Promise<void>(resolve => { notify = resolve; });
  const received: StreamEvent[] = [];
  const reading = readEvents(body, value => { received.push(value); notify(); });
  sender.enqueue(new TextEncoder().encode(JSON.stringify(event) + '\n'));
  await receivedOne;
  assert.equal(received.length, 1);
  sender.close();
  await reading;
});

test('task submission reports backend errors and sends the abort signal', async t => {
  const controller = new AbortController();
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    assert.equal(url, '/api/tasks/stream?run_id=one');
    assert.equal(init.signal, controller.signal);
    assert.deepEqual(JSON.parse(init.body as string), { task: 'Hello' });
    return new Response(JSON.stringify({ detail: 'Another run is active.' }), { status: 409 });
  });
  await assert.rejects(streamTask('Hello', 'one', () => {}, controller.signal), /Another run is active/);
});

test('Stop targets the run ID and tolerates an already finished run', async t => {
  t.mock.method(globalThis, 'fetch', async (url: string, init: RequestInit) => {
    assert.equal(url, '/api/tasks/one/stop');
    assert.equal(init.method, 'POST');
    return new Response('{}', { status: 404 });
  });
  assert.equal(await stopTask('one'), false);
});
