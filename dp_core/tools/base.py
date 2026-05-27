"""
Base Tool Infrastructure
Defines Tool base class and ToolRegistry
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
import json


@dataclass
class ToolResult:
    """Tool execution result"""
    success: bool
    data: Any = None
    error: Optional[str] = None

    def to_observation(self) -> str:
        """Convert to Agent-readable observation result"""
        if self.success:
            if isinstance(self.data, (dict, list)):
                return json.dumps(self.data, ensure_ascii=False, indent=2)
            return str(self.data)
        else:
            return f"Error: {self.error}"


@dataclass
class ToolParameter:
    """Tool parameter definition"""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None


class Tool(ABC):
    """Tool base class - All tools must inherit from this class"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (English, used for calling)"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description (Chinese, tells LLM what this tool does)"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> List[ToolParameter]:
        """Tool parameter list"""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute tool"""
        pass

    def get_schema(self) -> Dict[str, Any]:
        """Get JSON Schema of tool (for LLM function calling)"""
        properties = {}
        required = []

        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            }
        }

    def __str__(self) -> str:
        params_str = ", ".join(
            f"{p.name}: {p.type}" + ("?" if not p.required else "")
            for p in self.parameters
        )
        return f"{self.name}({params_str}) - {self.description}"


class ToolRegistry:
    """Tool registration center"""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register tool"""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def register_class(self, tool_class: Type[Tool]) -> None:
        """Register tool class (will automatically instantiate)"""
        tool = tool_class()
        self.register(tool)

    def get(self, name: str) -> Optional[Tool]:
        """Get tool"""
        return self._tools.get(name)

    def get_all(self) -> List[Tool]:
        """Get all tools"""
        return list(self._tools.values())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get Schema of all tools (for LLM)"""
        return [tool.get_schema() for tool in self._tools.values()]

    def get_tool_descriptions(self) -> str:
        """Get tool description text (for prompt)"""
        lines = ["Available tools:", ""]
        for tool in self._tools.values():
            lines.append(f"- {tool.name}: {tool.description}")
            for param in tool.parameters:
                req = "Required" if param.required else "Optional"
                lines.append(f"    - {param.name} ({param.type}, {req}): {param.description}")
            lines.append("")
        return "\n".join(lines)

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute specified tool"""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool not found: {tool_name}"
            )

        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            # Surface the traceback instead of silently swallowing it. Hiding it
            # here is exactly how a NameError in a tool could stay invisible.
            import traceback
            print(f"⚠️ Tool '{tool_name}' raised an exception:\n{traceback.format_exc()}")
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {type(e).__name__}: {e}"
            )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# Global tool registry
default_registry = ToolRegistry()


def register_tool(tool_class: Type[Tool]) -> Type[Tool]:
    """Decorator: Register tool to global registry"""
    default_registry.register_class(tool_class)
    return tool_class
