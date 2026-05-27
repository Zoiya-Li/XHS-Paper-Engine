"""Tests for the tool base layer: ToolResult rendering and registry execution."""

import pytest

from dp_core.tools.base import Tool, ToolParameter, ToolResult, ToolRegistry


def test_to_observation_success_dict():
    obs = ToolResult(success=True, data={"k": "v"}).to_observation()
    assert '"k"' in obs and '"v"' in obs


def test_to_observation_success_scalar():
    assert ToolResult(success=True, data="hello").to_observation() == "hello"


def test_to_observation_error():
    assert ToolResult(success=False, error="bad").to_observation() == "Error: bad"


class _EchoTool(Tool):
    @property
    def name(self):
        return "echo"

    @property
    def description(self):
        return "echo back"

    @property
    def parameters(self):
        return [ToolParameter("msg", "string", "message", required=True)]

    async def execute(self, msg, **kwargs):
        return ToolResult(success=True, data={"echo": msg})


class _BoomTool(_EchoTool):
    @property
    def name(self):
        return "boom"

    async def execute(self, **kwargs):
        raise RuntimeError("kaboom")


@pytest.mark.asyncio
async def test_registry_executes_tool():
    reg = ToolRegistry()
    reg.register_class(_EchoTool)
    result = await reg.execute("echo", msg="hi")
    assert result.success and result.data == {"echo": "hi"}


@pytest.mark.asyncio
async def test_registry_unknown_tool():
    reg = ToolRegistry()
    result = await reg.execute("missing")
    assert not result.success and "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_registry_wraps_tool_exception():
    reg = ToolRegistry()
    reg.register_class(_BoomTool)
    result = await reg.execute("boom")
    assert not result.success
    assert "RuntimeError" in result.error and "kaboom" in result.error


def test_get_schema_shape():
    tool = _EchoTool()
    schema = tool.get_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "echo"
    assert "msg" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["msg"]
