export interface LogEntry {
  type: 'log';
  id?: number;
  run_id: string;
  chat_id?: string;
  timestamp: string;
  source: string;
  message: string;
  details?: string | null;
}

export interface AgentResult {
  session_id: string;
  chat_id?: string;
  run_id?: string;
  model: string;
  workspace: string;
  final_response: string;
}

export interface ChatSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatRun {
  run_id: string;
  chat_id: string;
  task: string;
  created_at: string;
  outcome: string;
  result: AgentResult | null;
  logs: LogEntry[];
}

export interface Conversation extends ChatSummary {
  runs: ChatRun[];
}

export interface ActiveRun {
  run_id: string;
  chat_id: string;
}

export type StreamEvent = LogEntry | {
  type: 'final';
  run_id: string;
  result: AgentResult;
};
