"""Tests for the native function-calling agent loop and its text fallback."""

import pytest

from dp_core.agent import ReActAgent
from dp_core.tools.base import Tool, ToolParameter, ToolResult, ToolRegistry


class _EchoTool(Tool):
    @property
    def name(self):
        return "echo"

    @property
    def description(self):
        return "echo back the message"

    @property
    def parameters(self):
        return [ToolParameter("msg", "string", "message", required=True)]

    async def execute(self, msg, **kwargs):
        return ToolResult(success=True, data={"echo": msg})


@pytest.fixture
def fc_agent(tmp_path):
    reg = ToolRegistry()
    reg.register_class(_EchoTool)
    return ReActAgent(
        tool_registry=reg,
        work_dir=str(tmp_path / "w"),
        output_dir=str(tmp_path / "o"),
        verbose=False,
    )


@pytest.mark.asyncio
async def test_fc_executes_tool_then_finalizes(fc_agent):
    calls = {"n": 0}

    def fake_call(messages, tools=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": '{"msg": "hi"}'},
                }],
            }
        return {"role": "assistant", "content": "done"}

    fc_agent.api_client.call_chat_with_tools = fake_call

    trace = await fc_agent.run("do it")

    assert trace.success
    assert trace.steps[-1].final_answer == "done"
    assert any(s.action == "echo" and '"echo": "hi"' in (s.observation or "") for s in trace.steps)


@pytest.mark.asyncio
async def test_fc_falls_back_to_text_when_tools_unsupported(fc_agent):
    def boom(messages, tools=None):
        raise RuntimeError("tools not supported by provider")

    fc_agent.api_client.call_chat_with_tools = boom
    # Text-mode call returns a final answer immediately.
    fc_agent.api_client.call_chat = lambda messages, **kw: "Thought: done\nFinal Answer: text-mode"

    trace = await fc_agent.run("do it")

    assert trace.success
    assert trace.steps[-1].final_answer == "text-mode"


@pytest.mark.asyncio
async def test_fc_stops_at_max_steps(fc_agent):
    # Always request a tool -> never finalizes -> must stop at max_steps.
    def always_tool(messages, tools=None):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "c", "type": "function",
                "function": {"name": "echo", "arguments": '{"msg": "x"}'},
            }],
        }

    fc_agent.api_client.call_chat_with_tools = always_tool
    fc_agent.max_steps = 3

    trace = await fc_agent.run("loop forever")

    assert not trace.success
    assert "maximum steps" in (trace.error or "")
