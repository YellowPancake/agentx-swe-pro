"""Subprocess runner: executes mini-swe-agent in isolation.

Called by agent.py via subprocess to avoid litellm/httpx conflicts
with the A2A event loop. Reads instance JSON, runs the solver,
writes result JSON.
"""

import json
import os
import sys
import traceback

def main():
    instance_path = os.environ["INSTANCE_PATH"]
    result_path = os.environ["RESULT_PATH"]
    model_name = os.environ.get("MODEL_NAME", "deepseek/deepseek-chat")
    llm_api_base = os.environ.get("LLM_API_BASE")
    config_path = os.environ.get("MSWEA_CONFIG")

    # mini-swe-agent env overrides
    step_limit = int(os.environ.get("MSWEA_STEP_LIMIT", "25"))
    cost_limit = float(os.environ.get("MSWEA_COST_LIMIT", "2.0"))
    cmd_timeout = int(os.environ.get("MSWEA_CMD_TIMEOUT", "300"))
    subprocess_timeout = int(os.environ.get("MSWEA_SUBPROCESS_TIMEOUT", "1800"))
    max_tokens = int(os.environ.get("MSWEA_MAX_TOKENS", "4096"))

    with open(instance_path) as f:
        instance = json.load(f)

    instance_id = instance.get("instance_id", "unknown")
    problem_statement = instance.get("problem_statement", "")
    docker_image = instance.get("docker_image", "")
    base_commit = instance.get("base_commit", "")
    repo = instance.get("repo", "")
    hints = instance.get("hints", "")

    print(f"[runner] Instance: {instance_id}", file=sys.stderr)
    print(f"[runner] Model: {model_name}", file=sys.stderr)
    print(f"[runner] Docker image: {docker_image}", file=sys.stderr)
    print(f"[runner] Step limit: {step_limit}, Cost limit: ${cost_limit}", file=sys.stderr)

    patch = ""
    try:
        from mini_swe_agent import DefaultAgent, DockerEnvironment, LitellmModel

        # Load config if available
        agent_kwargs = {}
        if config_path and os.path.exists(config_path):
            import yaml
            with open(config_path) as f:
                config = yaml.safe_load(f)
            agent_kwargs = {
                "system_template": config.get("system_template"),
                "instance_template": config.get("instance_template"),
            }
            # Override limits from config if not set via env
            if "MSWEA_STEP_LIMIT" not in os.environ:
                step_limit = config.get("step_limit", step_limit)
            if "MSWEA_COST_LIMIT" not in os.environ:
                cost_limit = config.get("cost_limit", cost_limit)

        # Create Docker environment (sibling container)
        env = DockerEnvironment(
            image_name=docker_image,
            timeout=cmd_timeout,
        )

        # Create LLM model
        model_kwargs = {"model": model_name, "max_tokens": max_tokens}
        if llm_api_base:
            model_kwargs["api_base"] = llm_api_base
        model = LitellmModel(**model_kwargs)

        # Create agent
        agent = DefaultAgent(
            model=model,
            environment=env,
            step_limit=step_limit,
            cost_limit=cost_limit,
            **{k: v for k, v in agent_kwargs.items() if v is not None},
        )

        print(f"[runner] Starting agent for {instance_id}...", file=sys.stderr)

        # Run agent
        result = agent.run(
            problem_statement=problem_statement,
            base_commit=base_commit,
            repo=repo,
            hints=hints,
        )

        patch = result.patch if hasattr(result, "patch") else str(result)
        print(f"[runner] Patch generated: {len(patch)} chars", file=sys.stderr)

    except Exception as e:
        print(f"[runner] ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        patch = ""

    finally:
        # Cleanup Docker image to save disk space
        if docker_image:
            try:
                import subprocess as sp
                sp.run(["docker", "rmi", "-f", docker_image],
                       capture_output=True, timeout=30)
                print(f"[runner] Cleaned up image: {docker_image}", file=sys.stderr)
            except Exception:
                pass

    # Write result
    with open(result_path, "w") as f:
        json.dump({"instance_id": instance_id, "patch": patch}, f)

    print(f"[runner] Done: {instance_id}", file=sys.stderr)


if __name__ == "__main__":
    main()
