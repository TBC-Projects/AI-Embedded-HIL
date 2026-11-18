import { useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import { stopTask, streamTask } from './backendWorkflow';
import type { AgentResult, LogEntry } from './workflow';

const example = 'Create qemu-demo/src/main.c using hil.h. Its main function should print Hello from firmware using hil_puts, then return 0. Compile project qemu-demo. If successful, call run_qemu for 1 second. Explain the observed UART output, then finish. Do not flash.';

export default function App() {
  const [task, setTask] = useState(example);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [answer, setAnswer] = useState<AgentResult | null>(null);
  const active = useRef<{ id: string; controller: AbortController } | null>(null);
  const logWindow = useRef<HTMLDivElement>(null);
  const followLog = useRef(true);

  useEffect(() => () => {
    const previous = active.current;
    active.current = null;
    previous?.controller.abort();
  }, []);

  useEffect(() => {
    const window = logWindow.current;
    if (window && followLog.current) window.scrollTop = window.scrollHeight;
  }, [entries]);

  function addError(runId: string, message: string) {
    setEntries(previous => [...previous, {
      type: 'log', run_id: runId, timestamp: new Date().toISOString(),
      source: 'Error', message,
    }]);
  }

  async function run() {
    if (active.current) return;
    if (!task.trim()) { setError('Enter a task first.'); return; }
    const id = crypto.randomUUID();
    const controller = new AbortController();
    active.current = { id, controller };
    setError(''); setEntries([]); setAnswer(null); setBusy(true); setStopping(false);
    followLog.current = true;
    try {
      await streamTask(task.trim(), id, event => {
        if (active.current?.id !== id || event.run_id !== id) return;
        if (event.type === 'log') setEntries(previous => [...previous, event]);
        else setAnswer(event.result);
      }, controller.signal);
    } catch (error) {
      if (active.current?.id === id && !controller.signal.aborted) {
        addError(id, error instanceof TypeError
          ? 'Cannot reach the backend or the connection was lost. Check the backend terminal and that the server is running.'
          : error instanceof Error ? error.message : 'The request failed.');
      }
    } finally {
      if (active.current?.id === id) {
        active.current = null;
        setBusy(false); setStopping(false);
      }
    }
  }

  async function stop() {
    const current = active.current;
    if (!current || stopping) return;
    setStopping(true);
    try {
      const stopped = await stopTask(current.id);
      // Also abort a request that was still connecting when Stop was pressed.
      if (!stopped && active.current?.id === current.id) current.controller.abort();
    } catch {
      if (active.current?.id === current.id) {
        addError(current.id, 'Could not confirm Stop with the backend. Closing the stream; check the backend terminal for cleanup.');
        current.controller.abort();
      }
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="./"><span className="brand-icon" aria-hidden="true">▥</span> bench <span>/ embedded AI</span></a>
        <span className="eyebrow">THE BORING CLUB · HIL PROJECT</span>
      </header>
      <main>
        <div className="intro"><p className="eyebrow">FIRMWARE WORKSPACE</p><h1>Write. Run. Observe.</h1><p>Give the agent a task and follow its work from source code to emulator output.</p></div>
        <div className="notice">Agent calls, file changes, ARM builds, and QEMU runs are real. Physical flashing is simulated; no Pi or FPGA is connected.</div>
        <div className="workspace">
          <section className="panel task-panel" aria-labelledby="task-heading">
            <h2 id="task-heading"><span>01</span> Your task</h2>
            <label htmlFor="task">What should the firmware do?</label>
            <textarea id="task" value={task} disabled={busy} onChange={event => { setTask(event.target.value); setError(''); }} aria-invalid={!!error} aria-describedby="task-help task-error" />
            <p className="help" id="task-help">Files stay in the shared workspace. The agent can compile, observe QEMU output, and revise its code.</p>
            <p className="error" id="task-error" role="alert">{error}</p>
            <div className="actions"><button className="primary" disabled={busy} onClick={run}>▷ Run</button><button className="secondary" disabled={!busy || stopping} onClick={stop}>{stopping ? 'Stopping…' : '□ Stop'}</button></div>
            <p className="help footnote">One task at a time. Stop waits for cleanup; an active compiler finishes before the workspace is released.</p>
          </section>
          <section className="panel log-panel" aria-labelledby="log-heading">
            <div className="panel-heading"><h2 id="log-heading"><span>02</span> Activity log</h2><span className="counter">{entries.length} entries</span></div>
            <div className="event-log" ref={logWindow} onScroll={() => {
              const window = logWindow.current;
              if (window) followLog.current = window.scrollHeight - window.scrollTop - window.clientHeight < 60;
            }} role="log" aria-label="Backend activity and QEMU UART output" aria-live="polite" aria-relevant="additions">
              {!entries.length ? <div className="empty"><span aria-hidden="true">⌁</span><p>Run a task to see backend activity here.</p><small>QEMU UART captures appear in this same log.</small></div> :
                <ol>{entries.map((entry, index) => <li key={`${entry.run_id}-${index}`} className={entry.source === 'QEMU UART' ? 'uart-entry' : entry.source === 'Error' ? 'error-entry' : ''}>
                  <div className="entry-meta"><time dateTime={entry.timestamp}>{new Date(entry.timestamp).toLocaleTimeString([], { hour12: false })}</time><span className="source">{entry.source}</span></div>
                  <p className="message">{entry.message}</p>
                  {entry.details && (entry.source === 'QEMU UART' || entry.source === 'QEMU'
                    ? <pre>{entry.details}</pre>
                    : <details><summary>Details</summary><pre>{entry.details}</pre></details>)}
                </li>)}</ol>}
            </div>
          </section>
          <section className="panel answer-panel" aria-labelledby="answer-heading">
            <h2 id="answer-heading"><span>03</span> Final answer</h2>
            {answer ? <><div className="answer"><Markdown skipHtml>{answer.final_response}</Markdown></div><p className="help">Model: {answer.model}<br />Workspace: <code>{answer.workspace}</code></p></> : <p className="help">The agent’s final response will appear here. Tool observations and errors stay in the log above.</p>}
          </section>
        </div>
        <footer>BENCH / AI EMBEDDED HARDWARE-IN-THE-LOOP</footer>
      </main>
    </div>
  );
}
