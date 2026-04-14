"""Core agent: parses SWE-bench task JSON, launches mini-swe-agent in a subprocess,
streams status updates, and returns the patch as an artifact."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import queue
from pathlib import Path

from a2a.server.tasks import TaskUpdater
from a2a.types import Message, TaskState, Part, TextPart
from a2a.utils import get_message_text, new_agent_text_message

CONFIG_DIR = Path(__file__).parent.parent / "config"


class Agent:
    def __init__(self, model: str = "deepseek/deepseek-chat", llm_api_base: str | None = None):
        self.model = model
        self.llm_api_base = llm_api_base

    async def run(self, message: Message, updater: TaskUpdater) -> None:
        input_text = get_message_text(message)

        # Parse the SWE-bench task JSON from the message
        task_data = self._parse_task(input_text)
        if not task_data:
            await updater.add_artifact(
                parts=[Part(root=TextPart(text=json.dumps({"instance_id": "unknown", "patch": ""})))],
                name="patch",
            )
            return

        instance_id = task_data.get("instance_id", "unknown")
        await updater.update_status(
            TaskState.working,
            new_agent_text_message(f"Working on {instance_id} with {self.model}..."),
        )

        # Run mini-swe-agent in a subprocess to isolate litellm from A2A event loop
        patch = await self._run_solver(task_data, updater)

        # Return result as artifact
        result = json.dumps({"instance_id": instance_id, "patch": patch})
        await updater.add_artifact(
            parts=[Part(root=TextPart(text=result))],
            name="patch",
        )

    def _parse_task(self, text: str) -> dict | None:
        """Extract SWE-bench task JSON from message text."""
        # Try parsing the whole text as JSON
        try:
            data = json.loads(text)
            if "problem_statement" in data:
                return data
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        import re
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if "problem_statement" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # Try finding JSON object in text
        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(text[brace_start:i + 1])
                            if "problem_statement" in data:
                                return data
                        except json.JSONDecodeError:
                            pass
                        break

        print(f"WARNING: Could not parse task JSON from message: {text[:200]}")
        return None

    async def _run_solver(self, task_data: dict, updater: TaskUpdater) -> str:
        """Launch mini-swe-agent as a subprocess and stream status updates."""
        instance_id = task_data.get("instance_id", "unknown")

        with tempfile.TemporaryDirectory() as tmpdir:
            instance_path = os.path.join(tmpdir, "instance.json")
            result_path = os.path.join(tmpdir, "result.json")

            with open(instance_path, "w") as f:
                json.dump(task_data, f)

            # Build subprocess environment
            env = os.environ.copy()
            env["INSTANCE_PATH"] = instance_path
            env["RESULT_PATH"] = result_path
            env["MODEL_NAME"] = self.model
            if self.llm_api_base:
                env["LLM_API_BASE"] = self.llm_api_base

            # Config file path
            config_path = CONFIG_DIR / "swebench.yaml"
            if config_path.exists():
                env["MSWEA_CONFIG"] = str(config_path)

            runner_script = str(Path(__file__).parent / "run_mini_swe_agent.py")

            # Launch subprocess
            proc = await asyncio.create_subprocess_exec(
                sys.executable, runner_script,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Stream stderr for status updates + heartbeats
            heartbeat_task = asyncio.create_task(
                self._heartbeat(updater, instance_id, proc)
            )

            stderr_lines = []
            try:
                async for line in proc.stderr:
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        stderr_lines.append(decoded)
                        # Send periodic status updates (every 10 lines)
                        if len(stderr_lines) % 10 == 0:
                            status_msg = decoded[:200]
                            await updater.update_status(
                                TaskState.working,
                                new_agent_text_message(f"[{instance_id}] {status_msg}"),
                            )
            except Exception:
                pass

            await proc.wait()
            heartbeat_task.cancel()

            # Read result
            if os.path.exists(result_path):
                with open(result_path) as f:
                    result = json.load(f)
                return result.get("patch", "")
            else:
                print(f"No result file for {instance_id}, exit code: {proc.returncode}")
                if stderr_lines:
                    print(f"Last stderr: {stderr_lines[-3:]}")
                return ""

    async def _heartbeat(self, updater: TaskUpdater, instance_id: str, proc):
        """Send heartbeat every 60s to keep SSE connection alive."""
        try:
            while proc.returncode is None:
                await asyncio.sleep(60)
                if proc.returncode is None:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(f"[{instance_id}] Still working..."),
                    )
        except asyncio.CancelledError:
            pass
