# Orchestration

Minimal FastAPI skeleton for the future agent workflow. It has no queue, active
agent loop, compiler, or hardware dependencies. Python 3.10+ is required.

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r src/orchestration/requirements.txt
python -m uvicorn src.orchestration.main:app --reload --host 127.0.0.1 --port 8000
```

Endpoints:

```sh
curl http://127.0.0.1:8000/health
# 200: {"status":"ok"}
curl -i http://127.0.0.1:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"task":"Send Hello over UART once per second."}'
# 501: agent execution is not implemented; nothing is queued or executed.
```

Interactive API docs: http://127.0.0.1:8000/docs. Requests require a nonblank `task`
of at most 10,000 characters; invalid requests return 422. `run_agent_loop` raises
`NotImplementedError` if called. The endpoint does not call it or execute task text
as shell commands. The frontend currently uses its independent mock workflow.

Smoke checks (from the root, in the same virtual environment):

```sh
python -m pip install -r src/orchestration/requirements-dev.txt
python -m unittest src.orchestration.test_api
```

## Future agent flow

Receive task → prepare isolated workspace → call model → execute permitted tool
requests → return results to model → repeat until completion or a defined limit.
Orchestration owns revisions, retries, limits, and completion. Future permitted tools
will read/edit files, compile firmware, request hardware execution, and retrieve UART
output and available FPGA traces through the runner boundary. Tool results and brief
action summaries can be sent to the dashboard; private model reasoning must not be.
Model credentials belong on the backend, outside Git (for example environment
variables). Never put them in the dashboard bundle.

The runner owns concrete build and hardware operations; it does not call models or
manage agent retries. These backend parts may share one process initially. Job
queues, repository ingestion, trace analysis, and transport remain future work;
the older Week 5–9 milestones are planning goals, not implemented capabilities.
The Pi executes firmware; the separate FPGA captures connected digital signals and
explicit debug milestones, not arbitrary program state.
