"""OpenRouter Agent — an autonomous agent, any model, one key.

Same idea as the Claude Agent, but it talks to OpenRouter's OpenAI-compatible
gateway — so one OPENROUTER_API_KEY gives you Claude, GPT, Gemini, Llama, and
hundreds of other models. Set OPENROUTER_MODEL to pick; swap it any time
without touching your keys.

Give it a task via AGENT_TASK; it works to completion using a bash tool and
file read/write, then calls task_complete. The full transcript and token/cost
usage stream to stdout so you can watch it live in Berth's log viewer.

Runs on infrastructure you control, with your own key. The task and its output
never leave your machine except the model calls routed through OpenRouter.

Required env vars:
  OPENROUTER_API_KEY  Key from openrouter.ai/keys
  AGENT_TASK          What you want the agent to do (a plain-English task)

Optional env vars:
  OPENROUTER_MODEL    Any model id from openrouter.ai/models
                      (default: anthropic/claude-sonnet-4.5)
  AGENT_MAX_TURNS     Safety cap on agent loop iterations (default: 40)
  AGENT_WORKDIR       Directory the agent may read/write (default: ./workspace)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from openai import OpenAI

MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5").strip()
MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "40"))
BASE_URL = "https://openrouter.ai/api/v1"


def die(msg: str) -> "NoReturn":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def resolve_workdir() -> Path:
    workdir = Path(os.environ.get("AGENT_WORKDIR", "./workspace")).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir


def confine(workdir: Path, raw_path: str) -> Path:
    """Resolve a model-supplied path and confine it to the workspace.

    The path comes from the model and can be steered by the task text, so it's
    treated as untrusted: resolve to canonical form (following any ..) and
    reject anything that escapes the workspace root.
    """
    candidate = (workdir / raw_path).resolve() if not os.path.isabs(raw_path) else Path(raw_path).resolve()
    if candidate != workdir and workdir not in candidate.parents:
        raise ValueError(f"path {raw_path!r} is outside the workspace")
    return candidate


def tool(name: str, description: str, properties: dict, required: list) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


TOOLS = [
    tool(
        "bash",
        "Run a shell command in the workspace directory and return its combined "
        "stdout and stderr.",
        {"command": {"type": "string", "description": "The shell command to run"}},
        ["command"],
    ),
    tool(
        "read_file",
        "Read a file from the workspace and return its contents.",
        {"path": {"type": "string", "description": "Path relative to the workspace"}},
        ["path"],
    ),
    tool(
        "write_file",
        "Create or overwrite a file in the workspace with the given content.",
        {
            "path": {"type": "string", "description": "Path relative to the workspace"},
            "content": {"type": "string", "description": "The full file content to write"},
        },
        ["path", "content"],
    ),
    tool(
        "task_complete",
        "Call this when the task is finished. Provide a concise summary of what "
        "you did and where the results are. This ends the run.",
        {"summary": {"type": "string", "description": "What was accomplished"}},
        ["summary"],
    ),
]


def run_tool(workdir: Path, name: str, args: dict) -> str:
    try:
        if name == "bash":
            proc = subprocess.run(
                args["command"], shell=True, cwd=workdir,
                capture_output=True, text=True, timeout=300,
            )
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
            return (out or f"(no output, exit code {proc.returncode})")[:20000]
        if name == "read_file":
            return confine(workdir, args["path"]).read_text()[:20000]
        if name == "write_file":
            path = confine(workdir, args["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"])
            return f"wrote {len(args['content'])} bytes to {path.name}"
        return f"unknown tool: {name}"
    except subprocess.TimeoutExpired:
        return "command timed out after 300s"
    except Exception as e:  # surface to the model so it can adapt
        return f"{type(e).__name__}: {e}"


def main() -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        die("OPENROUTER_API_KEY not set — get one at https://openrouter.ai/keys")
    task = os.environ.get("AGENT_TASK", "").strip()
    if not task:
        die("AGENT_TASK not set — describe what you want the agent to do")

    workdir = resolve_workdir()
    client = OpenAI(
        base_url=BASE_URL,
        api_key=os.environ["OPENROUTER_API_KEY"],
        default_headers={
            "HTTP-Referer": "https://getberth.dev",
            "X-Title": "Berth OpenRouter Agent",
        },
    )

    print(f"═══ OpenRouter Agent ({MODEL}) ═══")
    print(f"Workspace: {workdir}")
    print(f"Task: {task}\n")

    system = (
        "You are an autonomous agent running on the user's own machine. Work the "
        "given task to completion using your tools, then call task_complete with "
        "a summary. Act decisively — you can run commands and read/write files "
        "without asking for confirmation. Keep going until the task is done or "
        "you are genuinely blocked, then explain the blocker in task_complete."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]

    total_in = total_out = 0
    total_cost = 0.0
    for _turn in range(MAX_TURNS):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                extra_body={"usage": {"include": True}},
            )
        except Exception as e:
            die(f"OpenRouter request failed: {e}\n"
                f"Check that OPENROUTER_MODEL={MODEL!r} exists and supports tools "
                "(browse models at https://openrouter.ai/models).")

        usage = getattr(response, "usage", None)
        if usage:
            total_in += usage.prompt_tokens or 0
            total_out += usage.completion_tokens or 0
            total_cost += float(getattr(usage, "cost", 0) or 0)

        msg = response.choices[0].message
        if msg.content and msg.content.strip():
            print(f"{msg.content.strip()}\n")

        if not msg.tool_calls:
            # Model stopped without a tool call — nudge it to finish.
            messages.append({"role": "assistant", "content": msg.content or ""})
            messages.append({"role": "user", "content": "Continue, or call task_complete if you're done."})
            continue

        # Echo the assistant turn (with its tool_calls) before the results.
        messages.append(msg.model_dump(exclude_none=True))

        done = False
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if name == "task_complete":
                print(f"✓ Done: {args.get('summary', '(no summary)')}")
                done = True
                break
            preview = args.get("command") or args.get("path") or ""
            print(f"  ▸ {name}: {preview}")
            result = run_tool(workdir, name, args)
            snippet = result if len(result) < 500 else result[:500] + " …"
            print(f"    {snippet}\n")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        if done:
            break
    else:
        print(f"⚠ Reached the {MAX_TURNS}-turn limit without finishing.")

    cost_str = f" · ~${total_cost:.4f}" if total_cost else " (billed by OpenRouter per model rates)"
    print(f"\n─── {total_in:,} in + {total_out:,} out tokens{cost_str} ───")


if __name__ == "__main__":
    main()
