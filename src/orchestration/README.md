# Orchestration

Service for the agent loop and the job queue. The agent framework and the queue implementation are not chosen yet.

* Week 5: Agent pipeline scaffold, repository ingestion, and a first generated C function that writes a GPIO register.
* Week 6: Job queue and run state. The runner polls this service.
* Week 8: Trace analyzer. Read the FPGA trace from the PYNQ and return missing strobes, timing deltas, and races.
* Week 9: Consume that report and revise the C until the flashed image passes.

Dashboard code lives in `src/dashboard/`.
