import type { Conversation } from './workflow';

// A history fetch can finish after new streamed logs arrive. Merge by run/log ID
// so switching chats and polling cannot duplicate entries or erase newer output.
export function mergeConversation(previous: Conversation | undefined, incoming: Conversation): Conversation {
  if (!previous) return incoming;
  const runs = new Map(previous.runs.map(run => [run.run_id, run]));
  for (const next of incoming.runs) {
    const old = runs.get(next.run_id);
    if (!old) { runs.set(next.run_id, next); continue; }
    const logs = new Map([...old.logs, ...next.logs].map(log => [
      log.id ?? `${log.timestamp}-${log.source}-${log.message}`, log,
    ]));
    runs.set(next.run_id, { ...old, ...next, result: next.result ?? old.result,
      logs: [...logs.values()].sort((a, b) => (a.id && b.id) ? a.id - b.id : a.timestamp.localeCompare(b.timestamp)),
    });
  }
  return { ...incoming, runs: [...runs.values()].sort((a, b) => a.created_at.localeCompare(b.created_at)) };
}
