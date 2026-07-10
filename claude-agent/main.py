"""Claude Agent — an autonomous agent that runs on your own machine.

Give it a task via the AGENT_TASK env var; it works the task to completion
using a bash tool and file read/write tools, then calls task_complete with a
summary. The full transcript — every message, tool call, and cost — streams to
stdout so you can watch it live in Berth's log viewer.

Runs on infrastructure you control (your Mac, your VPS), with your own API key.
Nothing about the task or its output leaves your machine except the calls to
the Claude API.

Required env vars:
  ANTHROPIC_API_KEY   API key from console.anthropic.com
  AGENT_TASK          What you want the agent to do (a plain-English task)

Optional env vars:
  AGENT_MODEL         Claude model id (default: claude-opus-4-8)
  AGENT_MAX_TURNS     Safety cap on agent loop iterations (default: 40)
  AGENT_WORKDIR       Directory the agent may read/write (default: ./workspace)
"""

import os
import subprocess
import sys
from pathlib import Path

import anthropic

MODEL = os.environ.get("AGENT_MODEL", "claude-opus-4-8").strip()
MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "40"))
# Prices per million tokens (input, output) for cost display. Defaults to
# Opus 4.8; override via env if you point AGENT_MODEL elsewhere.
PRICE_IN = float(os.environ.get("AGENT_PRICE_IN", "5.0"))
PRICE_OUT = float(os.environ.get("AGENT_PRICE_OUT", "25.0"))


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


TOOLS = [
    {
        "name": "bash",
        "description": (
            "Run a shell command in the workspace directory and return its "
            "combined stdout and stderr. Use for anything the file tools don't "
            "cover: running scripts, installing packages, git, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run"}
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the workspace and return its contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the workspace"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file in the workspace with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the workspace"},
                "content": {"type": "string", "description": "The full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "task_complete",
        "description": (
            "Call this when the task is finished. Provide a concise summary of "
            "what you did and where the results are. This ends the run."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What was accomplished"}
            },
            "required": ["summary"],
        },
    },
]


def run_tool(workdir: Path, name: str, tool_input: dict) -> tuple[str, bool]:
    """Execute a tool. Returns (result_text, is_error)."""
    try:
        if name == "bash":
            cmd = tool_input["command"]
            proc = subprocess.run(
                cmd, shell=True, cwd=workdir, capture_output=True,
                text=True, timeout=300,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            out = out.strip() or f"(no output, exit code {proc.returncode})"
            return out[:20000], proc.returncode != 0
        if name == "read_file":
            path = confine(workdir, tool_input["path"])
            return path.read_text()[:20000], False
        if name == "write_file":
            path = confine(workdir, tool_input["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(tool_input["content"])
            return f"wrote {len(tool_input['content'])} bytes to {path.name}", False
        return f"unknown tool: {name}", True
    except subprocess.TimeoutExpired:
        return "command timed out after 300s", True
    except Exception as e:  # surface the error to the model so it can adapt
        return f"{type(e).__name__}: {e}", True


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        die("ANTHROPIC_API_KEY not set — get one at https://console.anthropic.com")
    task = os.environ.get("AGENT_TASK", "").strip()
    if not task:
        die("AGENT_TASK not set — describe what you want the agent to do")

    workdir = resolve_workdir()
    client = anthropic.Anthropic()

    print(f"═══ Claude Agent ({MODEL}) ═══")
    print(f"Workspace: {workdir}")
    print(f"Task: {task}\n")

    system = (
        "You are an autonomous agent running on the user's own machine. Work "
        "the given task to completion using your tools, then call task_complete "
        "with a summary. Act decisively — you can run commands and read/write "
        "files without asking for confirmation. When you have enough information "
        "to act, act. Keep going until the task is done or you are genuinely "
        "blocked, then explain the blocker in task_complete."
    )
    messages = [{"role": "user", "content": task}]

    total_in = total_out = 0
    for turn in range(1, MAX_TURNS + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=system,
            thinking={"type": "adaptive", "display": "summarized"},
            tools=TOOLS,
            messages=messages,
        )
        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens

        for block in response.content:
            if block.type == "thinking" and block.thinking:
                print(f"  💭 {block.thinking.strip()}\n")
            elif block.type == "text" and block.text.strip():
                print(f"{block.text.strip()}\n")

        if response.stop_reason == "end_turn":
            # Model stopped without calling a tool — nudge it to finish.
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": "Continue, or call task_complete if you're done.",
            })
            continue

        messages.append({"role": "assistant", "content": response.content})
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        results = []
        done = False
        for tu in tool_uses:
            if tu.name == "task_complete":
                summary = tu.input.get("summary", "(no summary)")
                print(f"✓ Done: {summary}")
                done = True
                break
            preview = tu.input.get("command") or tu.input.get("path") or ""
            print(f"  ▸ {tu.name}: {preview}")
            result_text, is_error = run_tool(workdir, tu.name, tu.input)
            snippet = result_text if len(result_text) < 500 else result_text[:500] + " …"
            print(f"    {snippet}\n")
            results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_text,
                "is_error": is_error,
            })

        if done:
            break
        if results:
            messages.append({"role": "user", "content": results})
    else:
        print(f"⚠ Reached the {MAX_TURNS}-turn limit without finishing.")

    cost = total_in / 1e6 * PRICE_IN + total_out / 1e6 * PRICE_OUT
    print(f"\n─── {total_in:,} in + {total_out:,} out tokens · ~${cost:.3f} ───")


if __name__ == "__main__":
    main()
