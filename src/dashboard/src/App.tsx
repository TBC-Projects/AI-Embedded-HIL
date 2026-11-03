import { useEffect, useRef, useState } from 'react';
import { createMockWorkflow } from './mockWorkflow';
import type { ExecutionStatus, Stage, Workflow, WorkflowEvent, WorkflowResult } from './workflow';

const defaultWorkflow = createMockWorkflow();
const stages = ['Editing', 'Compiling', 'Waiting for device', 'Testing', 'Finished'];

export default function App({ workflow = defaultWorkflow }: { workflow?: Workflow }) {
  const [task, setTask] = useState('Send Hello over UART once per second.');
  const [submittedTask, setSubmittedTask] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState<ExecutionStatus>('idle');
  const [stage, setStage] = useState<Stage>('Idle');
  const [attempt, setAttempt] = useState(0);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const currentId = useRef<string | null>(null);
  const handle = useRef<ReturnType<Workflow['start']> | null>(null);
  const running = status === 'running';

  useEffect(() => () => {
    currentId.current = null;
    handle.current?.stop();
  }, [workflow]);

  function run() {
    if (handle.current) return;
    if (!task.trim()) { setError('Enter a firmware task before starting the demonstration.'); return; }
    const runId = crypto.randomUUID();
    currentId.current = runId;
    setError(''); setSubmittedTask(task.trim()); setEvents([]); setResult(null);
    setAttempt(0); setStage('Editing'); setStatus('running');
    // Reserve synchronously so even rapid clicks cannot create concurrent runs.
    handle.current = { stop() {} };
    const control = workflow.start({ runId, task: task.trim() }, {
      onProgress(nextStage, nextAttempt) {
        if (currentId.current !== runId) return;
        setStage(nextStage); setAttempt(nextAttempt);
      },
      onEvent(event) {
        if (currentId.current === runId && event.runId === runId) setEvents(previous => [...previous, event]);
      },
      onResult(nextResult) {
        if (currentId.current !== runId || nextResult.runId !== runId) return;
        currentId.current = null;
        handle.current = null;
        setResult(nextResult);
        setStatus(nextResult.outcome === 'stopped' ? 'stopped' : 'finished');
        setStage(nextResult.outcome === 'stopped' ? 'Stopped' : 'Finished');
      },
    });
    if (currentId.current === runId) handle.current = control;
  }

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="./" aria-label="Bench home"><span className="brand-icon">▥</span> bench<span className="brand-sub"> / embedded AI</span></a>
        <span className="project-label">THE BORING CLUB <span>·</span> HIL PROJECT</span>
      </header>
      <main>
        <div className="intro">
          <div><p className="eyebrow">FIRMWARE WORKSPACE / MVP 0.1</p><h1>A task. A test. A better iteration.</h1><p className="subtitle">Follow the path from firmware intent to measured feedback.</p></div>
          <span className="local-label"><span className="dot" /> LOCAL DEMONSTRATION</span>
        </div>
        <div className="mock-banner"><span className="mock-symbol">◈</span><div><strong>Mock mode — no agent or hardware connected</strong><p>Run plays a fixed demonstration using sample firmware. Your task is not interpreted or executed. All logs, evidence, and outcomes are simulated.</p></div><span className="badge">SIMULATED</span></div>
        <div className="workspace">
          <section className="panel task-panel" aria-labelledby="task-heading">
            <div className="section-heading"><span className="section-number">01</span><h2 id="task-heading">Define the task</h2></div>
            <label htmlFor="task">Firmware task</label>
            <textarea id="task" value={task} disabled={running} onChange={event => { setTask(event.target.value); setError(''); }} aria-describedby={error ? 'task-error task-help' : 'task-help'} aria-invalid={!!error} />
            <p id="task-help" className="help">Describe the behavior you want to observe on the device.</p>
            {error && <p id="task-error" role="alert" className="error">{error}</p>}
            <div className="actions"><button className="primary" disabled={running} onClick={run}><span aria-hidden="true">▷</span> Run demo</button><button className="secondary" disabled={!running} onClick={() => handle.current?.stop()}><span aria-hidden="true">□</span> Stop</button></div>
            <div className="device-card"><div className="device-title"><span className="chip" aria-hidden="true">▧</span><strong>Target device</strong><span className="disconnected"><span className="dot" /> Disconnected</span></div><p>Raspberry Pi Zero W</p><p className="help">No hardware connection is attempted in this MVP.</p></div>
            <div className="scope-note"><p className="eyebrow">THE FEEDBACK LOOP</p><p>Task → agent → build → device → test → revision</p><p className="help">The Pi executes firmware. The separate FPGA observes connected digital signals and emitted debug milestones, not arbitrary program state.</p></div>
          </section>
          <section className="panel progress-panel" aria-labelledby="progress-heading">
            <div className="section-heading"><span className="section-number">02</span><h2 id="progress-heading">Live progress</h2><span className={`status ${running ? 'active' : ''}`} role="status">{stage}</span></div>
            <div className="stage-track" aria-label="Workflow stages">{stages.map((item, index) => <div className={stage === item ? 'selected' : ''} key={item}><span>{String(index + 1).padStart(2, '0')}</span>{item === 'Waiting for device' ? 'Waiting for device' : item}</div>)}</div>
            <div className="log-heading"><span>EVENT STREAM <span className="muted">/ SIMULATED</span></span><span>{events.length} events{attempt > 0 ? ` · Attempt ${attempt}` : ''}</span></div>
            <div className="event-log" role="log" aria-label="Simulated chronological event log" aria-live="polite" aria-relevant="additions">
              {events.length === 0 ? <div className="empty-state"><span className="empty-icon" aria-hidden="true">⌁</span><h3>Ready when you are.</h3><p>Run the demo to watch a failed test,<br />a sample revision, and a passing test.</p><span className="terminal-hint">Waiting for a demonstration…</span></div> : <ol>{events.map((event, index) => <li key={`${event.runId}-${index}`}><time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleTimeString([], { hour12: false })}</time><span className={`source source-${event.source.toLowerCase()}`}>{event.source}</span><div><p><span className="sim-label">Simulated · </span>{event.message}</p>{event.details && <details><summary>View details</summary><pre>{event.details}</pre></details>}</div></li>)}</ol>}
            </div>
          </section>
          <section className="panel result-panel" aria-labelledby="result-heading">
            <div className="section-heading"><span className="section-number">03</span><h2 id="result-heading">Final result</h2><span className="muted small">SIMULATED OUTPUT</span></div>
            {result ? <div className="result-content"><div className="result-overview"><span className={`outcome outcome-${result.outcome.replaceAll(' ', '-')}`}>Simulated · {result.outcome}</span><span className="attempt-count">{result.attempts} {result.attempts === 1 ? 'attempt' : 'attempts'}</span><p>{result.summary}</p><p className="help">Submitted task (not executed): {submittedTask}</p></div><div className="result-evidence"><details><summary>Simulated test evidence ({result.evidence.length})</summary>{result.evidence.length ? result.evidence.map(item => <div className="evidence" key={item.attempt}><strong>Simulated attempt {item.attempt} · {item.outcome}</strong><p>Expected: {item.expected}</p><p>Observed: {item.observed}</p></div>) : <p>No test evidence was produced before stopping.</p>}</details><details><summary>Simulated sample code diff</summary><p className="help">Illustrative sample only; unrelated to actual repository changes.</p><pre className="diff">{result.diff || 'No sample revision was reached before stopping.'}</pre></details></div></div> : <div className="result-placeholder"><span aria-hidden="true">↳</span><p>{running ? 'Demonstration in progress. The result will appear here.' : 'Your demonstration result will appear here.'}<small>Outcome, attempt count, test evidence, and a sample code diff.</small></p></div>}
            <p className="result-footnote">A missing expected UART message is a test failure. An unavailable device means unable to test.</p>
          </section>
        </div>
        <footer><span>BENCH / AI EMBEDDED HARDWARE-IN-THE-LOOP</span><span>Sample firmware. Simulated evidence. No hardware access.</span></footer>
      </main>
    </div>
  );
}
