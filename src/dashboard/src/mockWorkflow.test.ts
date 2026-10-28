import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createMockWorkflow } from './mockWorkflow';
import type { WorkflowEvent, WorkflowResult } from './workflow';

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

test('fixed demonstration fails once, revises, and passes with typed evidence', async () => {
  const events: WorkflowEvent[] = [];
  const result = await new Promise<WorkflowResult>(resolve => {
    createMockWorkflow(1).start({ runId: 'complete', task: 'An unrelated task' }, {
      onProgress() {}, onEvent: event => events.push(event), onResult: resolve,
    });
  });
  assert.equal(result.outcome, 'passed');
  assert.equal(result.attempts, 2);
  assert.deepEqual(result.evidence.map(item => item.outcome), ['failed', 'passed']);
  assert.ok(result.diff.includes('+    for (;;)'));
  assert.equal(events.length, 10);
  assert.ok(events.every(event => event.runId === 'complete' && !Number.isNaN(Date.parse(event.timestamp))));
  assert.deepEqual([...new Set(events.map(event => event.source))], ['Agent', 'Build', 'Device', 'Test']);
});

test('stop cancels pending updates; restart receives only its own events', async () => {
  const workflow = createMockWorkflow(2);
  const oldEvents: WorkflowEvent[] = [];
  const results: WorkflowResult[] = [];
  const old = workflow.start({ runId: 'old', task: 'example' }, {
    onProgress() {}, onEvent: event => oldEvents.push(event), onResult: result => results.push(result),
  });
  await delay(1);
  old.stop(); old.stop();
  const countAtStop = oldEvents.length;
  const newEvents: WorkflowEvent[] = [];
  const next = await new Promise<WorkflowResult>(resolve => {
    workflow.start({ runId: 'new', task: 'example' }, {
      onProgress() {}, onEvent: event => newEvents.push(event), onResult: resolve,
    });
  });
  assert.equal(oldEvents.length, countAtStop);
  assert.equal(results.length, 1);
  assert.equal(results[0].outcome, 'stopped');
  assert.equal(next.outcome, 'passed');
  assert.ok(newEvents.every(event => event.runId === 'new'));
});

test('immediate stop produces zero attempts and no invented test evidence', async () => {
  let result: WorkflowResult | undefined;
  let eventCount = 0;
  const control = createMockWorkflow(1).start({ runId: 'immediate', task: 'example' }, {
    onProgress() {}, onEvent() { eventCount++; }, onResult(value) { result = value; },
  });
  control.stop();
  await delay(10);
  assert.equal(result?.outcome, 'stopped');
  assert.equal(result?.attempts, 0);
  assert.deepEqual(result?.evidence, []);
  assert.equal(eventCount, 0);
});
