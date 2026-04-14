import argparse
import os

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from executor import Executor


def main():
    parser = argparse.ArgumentParser(description="SWE-bench Pro Purple Agent")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9009)
    parser.add_argument("--card-url", type=str)
    parser.add_argument("--model", type=str, default=None,
                        help="LLM model name (e.g. deepseek/deepseek-chat, gpt-4o-mini)")
    parser.add_argument("--llm-api-base", type=str, default=None,
                        help="Custom API base URL for LLM provider")
    args = parser.parse_args()

    model = args.model or os.environ.get("MODEL_NAME", "deepseek/deepseek-chat")
    llm_api_base = args.llm_api_base or os.environ.get("LLM_API_BASE")

    skill = AgentSkill(
        id="fix-github-issue",
        name="Fix GitHub Issue",
        description="Analyzes a GitHub issue in a Docker environment and produces a git diff patch",
        tags=["coding", "debugging", "swe-bench"],
        examples=["Fix the failing test in the repository by analyzing the issue description"],
    )

    agent_card = AgentCard(
        name="AgentX-SWE-Pro",
        description="A coding agent that solves SWE-bench Pro tasks using mini-swe-agent",
        url=args.card_url or f"http://{args.host}:{args.port}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=Executor(model=model, llm_api_base=llm_api_base),
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    print(f"Starting AgentX-SWE-Pro on {args.host}:{args.port} with model={model}")
    uvicorn.run(server.build(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
