export interface LogEntry {
  type: 'log';
  run_id: string;
  timestamp: string;
  source: string;
  message: string;
  details?: string | null;
}

export interface AgentResult {
  session_id: string;
  model: string;
  workspace: string;
  final_response: string;
}

export type StreamEvent = LogEntry | {
  type: 'final';
  run_id: string;
  result: AgentResult;
};
