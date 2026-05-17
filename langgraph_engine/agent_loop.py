"""Tool-using agent loop.

A role node (PO / Engineer / QA) is a single call to `run_agent` with:
- the role's SKILLS.md content as system prompt
- a user prompt that frames the task and references on-disk inputs
- the workspace-scoped tool set

The loop dispatches every tool call the model emits and feeds results back until
the model returns an assistant message with no tool calls. That terminal
message is the agent's final report. A max-iterations safety cap prevents
runaway loops.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import AzureChatOpenAI


@dataclass
class AgentResult:
    final_message: str
    iterations: int
    tool_calls_made: int
    truncated: bool


# Tools that advance the work by mutating files. If an agent goes many
# iterations without invoking any of these, it is likely stuck in a
# debug/inspect loop and we inject a reassessment nudge.
PROGRESS_TOOLS = {"edit_file", "write_file", "copy_path"}
STUCK_WARN_AFTER = 10
STUCK_HARD_STOP_AFTER = 25


def run_agent(
    *,
    llm: AzureChatOpenAI,
    tools: list,
    system_prompt: str,
    user_prompt: str,
    max_iterations: int = 200,
    verbose: bool = True,
) -> AgentResult:
    """Run a tool-using agent loop until the model emits no tool calls."""
    bound = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    messages: list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    tool_calls_made = 0
    iteration = 0
    truncated = False
    consecutive_no_progress = 0
    warned_about_stuck = False

    while iteration < max_iterations:
        iteration += 1
        response: AIMessage = bound.invoke(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            return AgentResult(
                final_message=_extract_text(response.content),
                iterations=iteration,
                tool_calls_made=tool_calls_made,
                truncated=False,
            )

        if verbose:
            print(f"[agent iter {iteration}] {len(tool_calls)} tool call(s): "
                  + ", ".join(tc["name"] for tc in tool_calls))

        for tc in tool_calls:
            tool_calls_made += 1
            name = tc["name"]
            args = tc.get("args", {}) or {}
            tool = tool_map.get(name)
            if tool is None:
                tool_result: dict = {"ok": False, "error": f"unknown tool: {name}"}
            else:
                try:
                    tool_result = tool.invoke(args)
                except Exception as exc:  # noqa: BLE001
                    tool_result = {"ok": False, "error": f"tool raised: {exc!r}"}
            messages.append(ToolMessage(
                content=_serialize_tool_result(tool_result),
                tool_call_id=tc["id"],
                name=name,
            ))

        # Stuck-loop detection: count iterations with no mutating tool calls.
        if any(tc["name"] in PROGRESS_TOOLS for tc in tool_calls):
            consecutive_no_progress = 0
            warned_about_stuck = False
        else:
            consecutive_no_progress += 1

        if consecutive_no_progress >= STUCK_HARD_STOP_AFTER:
            if verbose:
                print(f"[agent loop] hard-stopping after {consecutive_no_progress} "
                      f"iterations with no edit/write/copy progress")
            truncated = True
            return AgentResult(
                final_message=(
                    f"Agent loop hard-stopped after {consecutive_no_progress} consecutive "
                    f"non-progress iterations. Last activity at iteration {iteration}. "
                    f"Tool calls made: {tool_calls_made}."
                ),
                iterations=iteration,
                tool_calls_made=tool_calls_made,
                truncated=True,
            )

        if consecutive_no_progress >= STUCK_WARN_AFTER and not warned_about_stuck:
            warned_about_stuck = True
            messages.append(HumanMessage(content=(
                f"STOP. You have run {consecutive_no_progress} consecutive iterations with no "
                "`edit_file`, `write_file`, or `copy_path` — only inspect/run tools. This is a "
                "stuck-loop signature.\n\n"
                "Before issuing another tool call, answer in plain text:\n"
                "1. Is the failure you are investigating inside the scope of the CURRENT backlog item, "
                "or is it pre-existing noise from a prior cycle's tooling/verifiers?\n"
                "2. If it is prior-cycle noise (e.g., a `verify_blNNNN.py` for some other BL is failing), "
                "STOP debugging it. That is not your responsibility this cycle.\n"
                "3. If you cannot make forward progress on the current BL in the next 3 iterations, "
                "commit the best implementation you have and write the final report.\n\n"
                "Do NOT issue another bash/read/list call without first writing or editing a file, "
                "unless you are running the final verification commands listed in your work packet."
            )))

    truncated = True
    return AgentResult(
        final_message=_extract_text(messages[-1].content) if messages else "",
        iterations=iteration,
        tool_calls_made=tool_calls_made,
        truncated=truncated,
    )


def _extract_text(content) -> str:
    """Coerce assistant content to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for chunk in content:
            if isinstance(chunk, dict):
                parts.append(chunk.get("text", ""))
            else:
                parts.append(str(chunk))
        return "".join(parts)
    return str(content)


def _serialize_tool_result(result) -> str:
    """Tool results are serialized to a JSON-like string for the model."""
    import json
    try:
        return json.dumps(result, default=str)
    except Exception:  # noqa: BLE001
        return str(result)
