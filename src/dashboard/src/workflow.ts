export type Stage = 'Idle' | 'Editing' | 'Compiling' | 'Waiting for device' | 'Testing' | 'Finished' | 'Stopped';
export type ExecutionStatus = 'idle' | 'running' | 'finished' | 'stopped';
export type TestOutcome = 'passed' | 'failed' | 'unable to test' | 'stopped';
export type Source = 'Agent' | 'Build' | 'Device' | 'Test';

export interface WorkflowEvent {
  runId: string;
  timestamp: string;
  source: Source;
  message: string;
  details?: string;
}
export interface TestEvidence {
  attempt: number;
  outcome: 'passed' | 'failed' | 'unable to test';
  expected: string;
  observed: string;
}
export interface WorkflowResult {
  runId: string;
  outcome: TestOutcome;
  summary: string;
  attempts: number;
  evidence: TestEvidence[];
  diff: string;
}
export interface WorkflowObserver {
  onProgress(stage: Stage, attempt: number): void;
  onEvent(event: WorkflowEvent): void;
  onResult(result: WorkflowResult): void;
}
export interface Workflow {
  start(request: { runId: string; task: string }, observer: WorkflowObserver): { stop(): void };
}
