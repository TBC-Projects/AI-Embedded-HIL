"""Minimal API skeleton. Submitted tasks are never executed."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="Embedded AI HIL orchestration", version="0.1.0")


class TaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=10000)

    @field_validator("task")
    @classmethod
    def nonblank_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Task must contain non-whitespace characters")
        return value.strip()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tasks", status_code=501)
def submit_task(request: TaskRequest) -> None:
    """Validate the request, then explicitly report the unimplemented feature."""
    raise HTTPException(
        status_code=501,
        detail="Agent execution is not implemented. No task was queued or executed; "
        "no model, compiler, or hardware was contacted. The dashboard uses a separate mock workflow.",
    )


def run_agent_loop(task: TaskRequest) -> None:
    """Placeholder: isolated workspace -> model -> permitted tools -> feedback.

    Eventually repeat until completion or an explicit iteration/time limit.
    Orchestration owns revisions/retries; runner owns build/hardware operations.
    """
    raise NotImplementedError("The firmware agent loop is not implemented")
