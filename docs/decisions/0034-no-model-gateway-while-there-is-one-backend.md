# 0034. No model gateway while there is one model backend

Status: Accepted
Date: 2026-10-24

## Context

The component index has listed LiteLLM as a candidate model gateway since the first plan, with one thing to prove: that it earns its footprint while there is only one model backend ([components](../components/README.md#planned)). [ADR 0001](0001-k3s-for-initial-orchestration.md) holds optional components back until the orchestrator's footprint is measured, and milestone 3's criterion is that deferred components go in or get dropped based on that measurement ([roadmap](../roadmap.md#3-toolchain-integration)).

The measurement is done. Over 15.3 hours to 2026-10-24, the orchestrator's CPU averaged 3.3 %, and its available memory never fell below 5,389 of 7,881 MB ([worklog](../worklogs/0003-toolchain-integration.md#orchestrator-footprint)). Room is not the question any more. A reason is.

Today there is one backend: llama.cpp on the worker, serving one model on `127.0.0.1:8080`. The agent runs on the same machine and calls it there. Nothing outside the worker can reach the model server ([AI worker](../components/ai-worker.md#the-model-server)). Jobs run one at a time, and the slot is erased before and after each job ([0032](0032-erase-the-slot-before-each-job-and-refuse-on-failure.md)).

A gateway gives one API across several backends, keys and spending limits per caller, and a log of every request. With one local backend, no cost per token, and one job at a time, none of these has anything to act on.

## Options

| Option | What it gives | What it costs |
| --- | --- | --- |
| LiteLLM on the orchestrator, as first planned | One place for model calls, beside the tool service | Prompts and answers cross the network twice per turn, worker to orchestrator and back. The model server has to listen beyond localhost, and the worker's rules have to let the orchestrator in to it |
| LiteLLM on the worker, in front of the model server | The same API, with no new network path | A Python service with a large dependency tree on the machine that runs the agent, inside the 4.1 GB the model server leaves free. It sits between two processes that already talk over localhost |
| No gateway until there is a second backend | Nothing to run, patch, or pin | The agent stays tied to one server's address. A second backend means this decision again |

## Decision

No gateway. LiteLLM leaves the component index.

The trigger to decide again is a second model backend: a second model served at the same time, or a hosted model with a key and a cost per token. Either gives a gateway something to route, limit, or account for.

## Trade-offs

- **No record of model calls that the worker cannot change.** The model's turns come back only in the job's transcript, inside the result the worker writes. A gateway on the orchestrator would have kept its own copy. The tool calls, which are what reach the system, are already logged on the orchestrator, out of the worker's reach ([0014](0014-a-small-tool-service-and-an-audit-log-on-the-orchestrator.md)).
- **The agent is tied to one server's address.** The job program and the runs by hand name `127.0.0.1:8080` and the alias `local`. A different model behind the same server changes nothing on the agent's side, as in the comparison for [0031](0031-qwen3-5-4b-stays-the-workers-model.md). A different server means changing both.
- **The memory stays free.** It is the margin for the collectors and change components of the later milestones, which are not measured yet.
