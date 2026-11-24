import { useCallback, useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import { createChat, deleteChat, getChat, listChats, stopTask, streamTask } from './backendWorkflow';
import { mergeConversation } from './chatState';
import type { ActiveRun, ChatSummary, Conversation, LogEntry } from './workflow';

const example = 'Create qemu-demo/src/main.c using hil.h. Print Hello from firmware and return 0. Compile qemu-demo, then use run_qemu for 1 second. Explain the UART output. Do not flash.';
const errorMessage = (error: unknown) => error instanceof TypeError
  ? 'Cannot reach the backend. Check that it is running on port 8000.'
  : error instanceof Error ? error.message : 'The request failed.';

function ActivityLog({ entries }: { entries: LogEntry[] }) {
  const window = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    if (window.current && follow.current) window.current.scrollTop = window.current.scrollHeight;
  }, [entries]);
  return <div className="event-log" ref={window} onScroll={() => {
    const el = window.current;
    if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }} role="log" aria-label="Backend activity and QEMU UART output" aria-live="polite" aria-relevant="additions">
    {!entries.length ? <p className="help log-empty">Waiting for backend activity…</p> : <ol>{entries.map((entry, index) =>
      <li key={entry.id ?? `${entry.run_id}-${index}`} className={entry.source === 'QEMU UART' ? 'uart-entry' : entry.source === 'Error' ? 'error-entry' : ''}>
        <div className="entry-meta"><time dateTime={entry.timestamp}>{new Date(entry.timestamp).toLocaleTimeString([], { hour12: false })}</time><span className="source">{entry.source}</span></div>
        <p className="message">{entry.message}</p>
        {entry.details && (entry.source === 'QEMU UART' || entry.source === 'QEMU'
          ? <pre>{entry.details}</pre>
          : <details><summary>Details</summary><pre>{entry.details}</pre></details>)}
      </li>)}</ol>}
  </div>;
}

export default function App() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [histories, setHistories] = useState<Record<string, Conversation>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [activeRun, setActiveRun] = useState<ActiveRun | null>(null);
  const localRun = useRef<{ id: string; chatId: string; controller: AbortController } | null>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const current = selected ? histories[selected] : undefined;
  const task = selected ? drafts[selected] ?? '' : '';

  const loadChat = useCallback(async (id: string) => {
    const incoming = await getChat(id);
    setHistories(previous => ({ ...previous, [id]: mergeConversation(previous[id], incoming) }));
  }, []);

  const refreshList = useCallback(async () => {
    const data = await listChats();
    setChats(data.chats);
    if (!localRun.current) setActiveRun(data.active_run);
    return data.chats;
  }, []);

  useEffect(() => {
    let mounted = true;
    listChats().then(data => {
      if (!mounted) return;
      setChats(data.chats); setActiveRun(data.active_run);
      const saved = localStorage.getItem('bench-chat');
      setSelected(data.chats.some(chat => chat.id === saved) ? saved : data.chats[0]?.id ?? null);
    }).catch(error => { if (mounted) setError(errorMessage(error)); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => {
      mounted = false;
      const run = localRun.current;
      localRun.current = null;
      run?.controller.abort();
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    localStorage.setItem('bench-chat', selected);
    follow.current = true;
    loadChat(selected).catch(error => setError(errorMessage(error)));
  }, [selected, loadChat]);

  useEffect(() => {
    if (!activeRun) return;
    const interval = setInterval(() => {
      refreshList().catch(() => {});
      if (selected && !localRun.current) loadChat(selected).catch(() => {});
    }, 2000);
    return () => clearInterval(interval);
  }, [activeRun, selected, refreshList, loadChat]);

  useEffect(() => {
    const el = transcript.current;
    if (el && follow.current) el.scrollTop = el.scrollHeight;
  }, [current]);

  async function newConversation() {
    if (creating) return;
    setCreating(true); setError('');
    try {
      const chat = await createChat();
      setHistories(previous => ({ ...previous, [chat.id]: chat }));
      setChats(previous => [chat, ...previous]);
      setSelected(chat.id);
    } catch (error) { setError(errorMessage(error)); }
    finally { setCreating(false); }
  }

  async function removeConversation(id: string) {
    if (!window.confirm('Delete this conversation and its logs? Shared workspace files will be kept.')) return;
    try {
      await deleteChat(id);
      setHistories(previous => { const copy = { ...previous }; delete copy[id]; return copy; });
      const remaining = await refreshList();
      if (selected === id) setSelected(remaining[0]?.id ?? null);
      setError('');
    } catch (error) { setError(errorMessage(error)); }
  }

  async function send() {
    if (!selected || localRun.current || activeRun) return;
    if (!task.trim()) { setError('Enter a message first.'); return; }
    const chatId = selected;
    const id = crypto.randomUUID();
    const controller = new AbortController();
    localRun.current = { id, chatId, controller };
    setActiveRun({ run_id: id, chat_id: chatId }); setStopping(false); setError('');
    setDrafts(previous => ({ ...previous, [chatId]: '' }));
    follow.current = true;
    setHistories(previous => ({ ...previous, [chatId]: {
      ...previous[chatId], runs: [...previous[chatId].runs, {
        run_id: id, chat_id: chatId, task: task.trim(), created_at: new Date().toISOString(),
        outcome: 'running', result: null, logs: [],
      }],
    } }));
    try {
      await streamTask(task.trim(), id, event => {
        if (localRun.current?.id !== id || event.run_id !== id) return;
        setHistories(previous => ({ ...previous, [chatId]: {
          ...previous[chatId], runs: previous[chatId].runs.map(run => run.run_id !== id ? run : event.type === 'log'
            ? { ...run, logs: [...run.logs.filter(log => !event.id || log.id !== event.id), event] }
            : { ...run, result: event.result, outcome: 'completed' }),
        } }));
      }, controller.signal, chatId);
    } catch (error) {
      if (localRun.current?.id === id && !controller.signal.aborted) {
        setError(errorMessage(error));
        setDrafts(previous => ({ ...previous, [chatId]: task }));
      }
    } finally {
      if (localRun.current?.id === id) {
        localRun.current = null;
        setActiveRun(null); setStopping(false);
        // Reload the durable record, including errors, Stop, and cleanup messages.
        try {
          const saved = await getChat(chatId);
          setHistories(previous => ({ ...previous, [chatId]: saved }));
          await refreshList();
        } catch (error) { setError(errorMessage(error)); }
      }
    }
  }

  async function stop() {
    if (!activeRun || stopping) return;
    setStopping(true);
    try {
      const stopped = await stopTask(activeRun.run_id);
      if (!stopped && localRun.current?.id === activeRun.run_id) localRun.current.controller.abort();
      if (!localRun.current) {
        setActiveRun(null); setStopping(false);
        if (selected) await loadChat(selected);
        await refreshList();
      }
    } catch (error) { setError(errorMessage(error)); setStopping(false); }
  }

  return <div className="chat-app">
    <aside className="sidebar" aria-label="Conversations">
      <a className="brand" href="./"><span className="brand-icon" aria-hidden="true">▥</span> bench <span>/ embedded AI</span></a>
      <button className="new-chat" onClick={newConversation} disabled={creating}>＋ New conversation</button>
      <p className="eyebrow sidebar-label">CONVERSATIONS</p>
      <nav>{chats.map(chat => <div key={chat.id} className={`chat-row ${selected === chat.id ? 'selected' : ''}`}>
        <button className="chat-select" aria-current={selected === chat.id ? 'page' : undefined} onClick={() => { setSelected(chat.id); setError(''); }}>{chat.title}</button>
        <button className="delete-chat" aria-label={`Delete ${chat.title}`} title="Delete conversation; keep files" disabled={activeRun?.chat_id === chat.id} onClick={() => removeConversation(chat.id)}>×</button>
      </div>)}</nav>
      <div className="sidebar-note"><strong>One shared workspace</strong><p>All chats can read and edit the same files. Deleting a chat keeps those files.</p><span>THE BORING CLUB · HIL PROJECT</span></div>
    </aside>
    <main className="chat-main">
      <header className="chat-header"><div><p className="eyebrow">FIRMWARE WORKSPACE</p><h1>{current?.title ?? 'Write. Run. Observe.'}</h1></div><span>Local agent · physical flashing simulated</span></header>
      <div className="transcript" ref={transcript} onScroll={() => {
        const el = transcript.current;
        if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }}>
        {(!current || !current.runs.length) && <div className="welcome"><span aria-hidden="true">⌁</span><h2>{loading ? 'Loading conversations…' : selected ? 'What shall we build?' : 'Start a conversation.'}</h2><p>Ask the agent to inspect files, write firmware, compile it, or observe its UART output in QEMU.</p><p>Messages and activity logs are saved locally. Every chat shares the current workspace files.</p>{!selected && <button className="primary" onClick={newConversation} disabled={creating || loading}>＋ New conversation</button>}</div>}
        {current?.runs.map(run => <article className="turn" key={run.run_id}>
          <div className="user-message"><div className="message-label">YOU <time dateTime={run.created_at}>{new Date(run.created_at).toLocaleString()}</time></div><p>{run.task}</p></div>
          <details className="run-log" open={activeRun?.run_id === run.run_id ? true : undefined}>
            <summary>Activity log <span>{run.logs.length} entries · includes QEMU output</span></summary>
            <ActivityLog entries={run.logs} />
          </details>
          {run.result ? <div className="assistant-message"><div className="message-label">BENCH AGENT <span>{run.result.model}</span></div><div className="answer"><Markdown skipHtml>{run.result.final_response}</Markdown></div></div>
            : activeRun?.run_id !== run.run_id && <p className="help no-answer">No final reply for this turn. See the activity log for details.</p>}
        </article>)}
      </div>
      <div className="composer-area">
        {error && <p className="error" role="alert">{error}</p>}
        <form className="composer" onSubmit={event => { event.preventDefault(); void send(); }}>
          <label className="sr-only" htmlFor="message">Message the firmware agent</label>
          <textarea id="message" value={task} disabled={!current || !!activeRun} placeholder={selected ? 'Ask a question or request a firmware change…' : 'Create a conversation to begin…'} onChange={event => { if (selected) setDrafts(previous => ({ ...previous, [selected]: event.target.value })); }} onKeyDown={event => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); void send(); }
          }} />
          <div className="composer-actions"><button type="button" className="example-button" disabled={!current || !!activeRun} onClick={() => { if (selected) setDrafts(previous => ({ ...previous, [selected]: example })); }}>Use QEMU example</button><div><button type="button" className="secondary" disabled={!activeRun || stopping} onClick={stop}>{stopping ? 'Stopping…' : 'Stop'}</button><button className="primary" type="submit" disabled={!current || !!activeRun || !task.trim()}>Send ↑</button></div></div>
        </form>
        <p className="composer-note">Real model calls, files, builds, and QEMU. One run at a time. Saved chat history does not restore earlier file versions.</p>
      </div>
    </main>
  </div>;
}
