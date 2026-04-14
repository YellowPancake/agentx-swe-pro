# AgentX SWE-Pro Agent

A purple agent for the [AgentX/AgentBeats](https://rdi.berkeley.edu/agentx-agentbeats.html) competition — SWE-bench Pro (Coding Agent) track.

Receives GitHub issue descriptions via [A2A protocol](https://a2a-protocol.org/latest/), fixes them using [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) in Docker sibling containers, and returns git diff patches.

## Architecture

```
Green Agent → POST /messages (task JSON)
  → server.py (A2A + uvicorn, port 9009)
  → executor.py (task lifecycle management)
  → agent.py (parse task, launch subprocess)
  → run_mini_swe_agent.py (Docker container + LLM ReAct loop)
  → patch artifact → Green Agent
```

## Quick Start

```bash
# Install dependencies
uv sync

# Run locally (needs Docker for sibling containers)
DEEPSEEK_API_KEY=sk-xxx uv run src/server.py --model deepseek/deepseek-chat

# Test agent card
curl http://localhost:9009/.well-known/agent-card.json | python3 -m json.tool
```

## Docker

```bash
docker build -t agentx-swe-pro .

docker run -d -p 9009:9009 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e DEEPSEEK_API_KEY=sk-xxx \
  -e MODEL_NAME=deepseek/deepseek-chat \
  agentx-swe-pro
```

## Testing

```bash
uv sync --extra test
uv run pytest --agent-url http://localhost:9009
```

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| MODEL_NAME | deepseek/deepseek-chat | LLM model (via litellm) |
| MSWEA_STEP_LIMIT | 25 | Max LLM turns per task |
| MSWEA_COST_LIMIT | 2.0 | Max cost per task ($) |
| MSWEA_CMD_TIMEOUT | 300 | Bash command timeout (s) |

## Publishing

Push to `main` → GitHub Actions builds and publishes to GHCR:
```
ghcr.io/<username>/agentx-swe-pro:latest
```
