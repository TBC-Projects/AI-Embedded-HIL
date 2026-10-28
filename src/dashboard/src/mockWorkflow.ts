import type { Source, Stage, TestEvidence, Workflow } from './workflow';

const evidence: TestEvidence[] = [
  { attempt: 1, outcome: 'failed', expected: 'UART “Hello” at 0, 1000, and 2000 ms.', observed: 'Sample UART: “Hello” at 0 ms only. Messages at 1000 and 2000 ms are missing.' },
  { attempt: 2, outcome: 'passed', expected: 'UART “Hello” at 0, 1000, and 2000 ms.', observed: 'Sample UART: “Hello” at 0, 1000, and 2000 ms. All expected messages match.' },
];
const diff = `--- sample/hello.c (attempt 1)
+++ sample/hello.c (attempt 2)
@@ -1,4 +1,6 @@
 void main(void) {
-    uart_puts("Hello\\n");
+    for (;;) {
+        uart_puts("Hello\\n");
+        delay_ms(1000);
+    }
 }`;

type Step = { stage: Stage; attempt: number; source: Source; message: string; details?: string; evidence?: TestEvidence };
const steps: Step[] = [
  { stage: 'Editing', attempt: 1, source: 'Agent', message: 'Preparing the fixed sample firmware.', details: 'Demonstration only. The submitted task is recorded in the UI but is not interpreted. Sample firmware initially sends Hello just once.' },
  { stage: 'Compiling', attempt: 1, source: 'Build', message: 'Sample compilation completed.', details: '[simulated compiler output]\nCompiling sample/hello.c\nLinking sample/hello.elf\nBuild complete: 0 errors. No compiler was invoked.' },
  { stage: 'Waiting for device', attempt: 1, source: 'Device', message: 'Loading recorded device feedback.', details: 'No device connection, upload, reset, or execution takes place. The real device remains disconnected.' },
  { stage: 'Testing', attempt: 1, source: 'Device', message: 'Sample UART: [0 ms] Hello', details: '[simulated capture]\n0 ms: Hello\n1000 ms: <no message>\n2000 ms: <no message>' },
  { stage: 'Testing', attempt: 1, source: 'Test', message: 'Attempt 1 failed: two expected UART messages are missing.', details: 'Expected: Hello at 0, 1000, 2000 ms.\nObserved: Hello at 0 ms only.\nThis is a simulated test failure. An unavailable device would instead produce “unable to test”.', evidence: evidence[0] },
  { stage: 'Editing', attempt: 2, source: 'Agent', message: 'Revising the sample to repeat the UART write every second.', details: 'Action summary: place the sample write inside a loop and add a 1000 ms delay. This is a scripted action, not a model call or repository edit.' },
  { stage: 'Compiling', attempt: 2, source: 'Build', message: 'Revised sample compilation completed.', details: '[simulated compiler output]\nCompiling sample/hello.c\nLinking sample/hello.elf\nBuild complete: 0 errors. No compiler was invoked.' },
  { stage: 'Waiting for device', attempt: 2, source: 'Device', message: 'Loading the second recorded capture.' },
  { stage: 'Testing', attempt: 2, source: 'Device', message: 'Sample UART: Hello at 0, 1000, and 2000 ms.', details: '[simulated capture]\n0 ms: Hello\n1000 ms: Hello\n2000 ms: Hello' },
  { stage: 'Testing', attempt: 2, source: 'Test', message: 'Attempt 2 passed: all three expected messages match.', evidence: evidence[1] },
];

// Simulates the entire visible workflow. It performs no network or hardware operations.
export function createMockWorkflow(stepDelay = 850): Workflow {
  return {
    start({ runId }, observer) {
      let active = true;
      let index = 0;
      let attempts = 0;
      const collected: TestEvidence[] = [];
      let timer: ReturnType<typeof setTimeout>;
      const finish = (stopped: boolean) => {
        if (!active) return;
        active = false;
        clearTimeout(timer);
        observer.onResult({
          runId, outcome: stopped ? 'stopped' : 'passed', attempts,
          summary: stopped
            ? 'Demonstration stopped. No agent or hardware was used.'
            : 'The fixed UART example passed after one revision. All evidence is simulated; your submitted task was not executed.',
          evidence: [...collected], diff: attempts >= 2 ? diff : '',
        });
      };
      const next = () => {
        if (!active) return;
        const step = steps[index++];
        attempts = step.attempt;
        if (step.evidence) collected.push(step.evidence);
        observer.onProgress(step.stage, attempts);
        observer.onEvent({ runId, timestamp: new Date().toISOString(), source: step.source, message: step.message, details: step.details });
        // A consumer may cancel synchronously from a callback.
        if (!active) return;
        if (index === steps.length) finish(false);
        else timer = setTimeout(next, stepDelay);
      };
      timer = setTimeout(next, 0);
      return { stop: () => finish(true) };
    },
  };
}
