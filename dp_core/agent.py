"""
XHS Paper Engine Agent

By default the agent uses the model's **native function calling** (tools are
passed via the API's ``tools`` parameter and executed from ``tool_calls``). If
the provider/model does not support tools, it transparently falls back to a
text-based ReAct (Reasoning + Acting) loop that parses Thought/Action/Observation.
Toggle with the ``use_function_calling`` flag on the agent.
"""

import json
import re
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from .tools.base import ToolRegistry, default_registry
from . import tools as _tools  # Ensure tool registration side effects run
from .api_client import APIClient
from .config import config


def _print_flush(*args, **kwargs):
    """Print and immediately flush to ensure output is visible"""
    print(*args, **kwargs)
    sys.stdout.flush()


@dataclass
class AgentStep:
    """A single step executed by the Agent"""
    step_num: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[str] = None


@dataclass
class AgentTrace:
    """Agent execution trace"""
    task: str
    steps: List[AgentStep] = field(default_factory=list)
    success: bool = False
    error: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None


class ReActAgent:
    """
    ReAct Agent - Using DeepSeek as the reasoning engine

    Workflow:
    1. Receive user task
    2. Thought: Think about what to do next
    3. Action: Decide which tool to call
    4. Observation: Get tool execution result
    5. Repeat 2-4 until task is complete
    6. Return final answer
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        max_steps: int = 20,  # Increase step count to support complete publishing workflow
        verbose: bool = True,
        work_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
        session_id: Optional[str] = None,
        use_function_calling: bool = True,
    ):
        self.registry = tool_registry or default_registry
        self.api_client = APIClient()
        self.max_steps = max_steps
        self.verbose = verbose
        # Prefer the model's native tool calling; fall back to text ReAct parsing.
        self.use_function_calling = use_function_calling

        # Session ID: used to distinguish each run, format YYYYMMDD_HHMMSS
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Working directory (for storing traces, etc.)
        self.work_dir = Path(work_dir) if work_dir else Path("./work")
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Base output directory
        base_output = Path(output_dir) if output_dir else Path("./output")

        # Session directory: each run's output is placed in a separate time folder
        # Format: ./output/20260129_070000/
        self.session_dir = base_output / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectory structure
        self.papers_dir = self.session_dir / "papers"      # Downloaded paper PDFs
        self.markdown_dir = self.session_dir / "markdown"  # Converted Markdown
        self.figures_dir = self.session_dir / "figures"    # Extracted figures
        self.posts_dir = self.session_dir / "posts"        # Generated posts

        # Create all subdirectories
        for d in [self.papers_dir, self.markdown_dir, self.figures_dir, self.posts_dir]:
            d.mkdir(parents=True, exist_ok=True)

        if self.verbose:
            print(f"   Session directory: {self.session_dir}")

    def _build_system_prompt(self, function_calling: bool = False) -> str:
        """Build system prompt.

        When ``function_calling`` is True, the tools are supplied to the model
        via the API's native ``tools`` parameter, so the text-based
        Thought/Action/Observation protocol is omitted.
        """
        # In function-calling mode the model receives tool schemas natively, so
        # we don't need to enumerate tools in the prompt or teach a text protocol.
        tools_desc = "" if function_calling else self.registry.get_tool_descriptions()

        if function_calling:
            protocol_block = """Working mode:
Use the tools available to you (provided via the API) to complete the task. Call
tools as needed; the system returns each tool's result. When the task is
finished, reply with a normal message that summarizes the outcome (do not call a
tool in that final message).

Notes:
- You decide which data source to use and what keywords to search.
- Use the specified output directories above for all generated files.
- If tool execution fails, analyze the reason and try a different approach.
- Prefer `optimize_xiaohongshu_with_vision` to pick images; if no vision model is available, pass the extracted images directly to `publish_xiaohongshu`.
- If `extract_figures` returns no figures, this paper is unsuitable — go back and select a different paper instead of publishing page screenshots.
"""
        else:
            protocol_block = """Working mode (ReAct mode):
You need to complete tasks following the "thought-action-observation" cycle.

**Important: You can only output Thought and Action, never output Observation!**
Observation is the result automatically returned by the system after executing the tool, you must wait for the system to return.

Each time you only need to output:
```
Thought: [Your thinking process]
Action: {"tool": "tool_name", "args": {parameters}}
```

Then stop and wait for the system to return Observation.

**Strictly prohibited behaviors:**
- Do not fabricate Observation yourself
- Do not add "---" or other separators after Action
- Do not guess what results the tool will return
- Do not output multiple Actions in one response

When the task is complete, output:
```
Thought: [Summary]
Final Answer: [Final answer]
```

Notes:
- Only execute one Action at a time, then wait for results
- Action must be valid JSON format
- If tool execution fails, analyze the reason and try other methods
- **You have full autonomy to decide which data source to use and what keywords to search**
- Keep concise, do not repeat known information
- Please use the above specified directories for all output files
- **Image selection**: prefer `optimize_xiaohongshu_with_vision`; if no vision model is configured, pass the extracted images directly to `publish_xiaohongshu`
- If `extract_figures` returns empty `all_images`, the paper is unsuitable — go back to selection and choose a different paper (never publish full-page screenshots)
"""

        # Get research area configuration
        rc = getattr(self, '_get_research_config', lambda: {
            "keywords": ["LLM"],
            "categories": ["cs.AI"],
            "sources": ["arxiv"],
            "days": 3
        })()

        return f"""You are XHS Paper Engine Agent, an intelligent paper recommendation and content creation assistant.

Your capabilities:
1. Search and discover the latest academic papers
2. Analyze and filter valuable papers
3. Write paper interpretation articles (blog, Xiaohongshu)
4. Automatically publish content to Xiaohongshu

**Available data sources (you can choose the most suitable one)**:
- arxiv: Preprint server, latest AI/ML/CS papers, fast updates
- semantic: Semantic Scholar, with citation data, suitable for finding high-impact papers (requires S2_API_KEY; disabled if not configured)

**Data source selection suggestions (for reference only, you can judge independently)**:
- Find latest AI/ML papers → Prioritize arxiv
- Find highly cited papers or surveys → Prioritize semantic (only if S2_API_KEY is configured)
- If one source doesn't have results, broaden the time range or try different keywords

**Current user research areas**:
- Keywords: {', '.join(rc['keywords'])}
- arXiv categories: {', '.join(rc['categories'])}

**Publishing workflow (important)**:
When publishing content, follow these steps:

1. Xiaohongshu publishing:
   - Call `login_xiaohongshu` to trigger QR code login if needed (user needs to scan with phone)
   - After login, call `publish_xiaohongshu` to publish content
   - After successful publishing, call `record_publish` to record publish history

Note: `record_publish` only records history, not actual publishing! Must call `publish_xiaohongshu` first to actually publish.

**Image extraction and selection workflow**:
1. First use `extract_figures` to extract images from PDF
2. Check the `all_images` array in the result:
   - If empty (this paper has no recognizable figures/tables), it is NOT suitable for an
     image-heavy Xiaohongshu post. Do NOT publish full-page screenshots — they look bad.
     Go back to paper selection and pick a different unpublished paper, then retry.
3. Selecting which images to publish:
   - Preferred: `optimize_xiaohongshu_with_vision` — a vision model looks at the images and
     picks the 3-5 most informative ones (and aligns the post text to them).
   - If no vision model is configured (some providers have none), just pass the extracted
     images directly to `publish_xiaohongshu` (it accepts up to 18; send the first few).
4. **Xiaohongshu publishing**: pass the selected images to `publish_xiaohongshu`

{tools_desc}

Output directories (this session):
- Paper PDFs: {self.papers_dir}
- Markdown: {self.markdown_dir}
- Images: {self.figures_dir}
- Posts: {self.posts_dir}

{protocol_block}"""

    def _parse_response(self, response: str) -> Tuple[str, Optional[str], Optional[Dict], Optional[str]]:
        """
        Parse LLM response

        Returns:
            (thought, action_name, action_args, final_answer)
        """
        thought = ""
        action_name = None
        action_args = None
        final_answer = None

        # Detect and warn about fake Observations generated by LLM
        # LLM should not generate Observation, this is returned by the system
        obs_pos = response.find('Observation:')
        sep_pos = response.find('\n---')  # Only match separator after newline

        truncate_pos = -1
        if obs_pos > 0 and sep_pos > 0:
            truncate_pos = min(obs_pos, sep_pos)
        elif obs_pos > 0:
            truncate_pos = obs_pos
        elif sep_pos > 0:
            truncate_pos = sep_pos

        if truncate_pos > 0:
            response = response[:truncate_pos].strip()
            print("⚠️ Detected LLM generated fake Observation or separator, ignored")

        # Extract Thought
        thought_match = re.search(r'Thought:\s*(.+?)(?=Action:|Final Answer:|$)', response, re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()

        # Check if there's Final Answer
        final_match = re.search(r'Final Answer:\s*(.+?)$', response, re.DOTALL)
        if final_match:
            final_answer = final_match.group(1).strip()
            return thought, None, None, final_answer

        # Extract Action - need to correctly handle nested JSON
        action_match = re.search(r'Action:\s*(\{.*\})', response, re.DOTALL)
        if action_match:
            action_str = action_match.group(1).strip()
            # Find matching right brace
            brace_count = 0
            end_pos = 0
            for i, char in enumerate(action_str):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break

            if end_pos > 0:
                action_str = action_str[:end_pos]

            try:
                action_json = json.loads(action_str)
                action_name = action_json.get("tool")
                action_args = action_json.get("args", {})
            except json.JSONDecodeError:
                # Try to fix common JSON issues
                action_str = action_str.replace("'", '"')
                try:
                    action_json = json.loads(action_str)
                    action_name = action_json.get("tool")
                    action_args = action_json.get("args", {})
                except:
                    pass

        return thought, action_name, action_args, final_answer

    def _apply_output_paths(self, action_name: str, action_args: Dict[str, Any]) -> None:
        """Auto-fill session output paths when the tool call omits them."""
        if action_args is None:
            return

        # Download papers -> papers directory
        if action_name == "download_paper":
            action_args.setdefault("output_dir", str(self.papers_dir))

        # Extract figures -> session dir (the tool creates figures/ and tables/
        # subdirs inside it). Force it (not setdefault): the model otherwise passes
        # the figures_dir it sees in the prompt, producing figures/figures nesting.
        if action_name == "extract_figures":
            action_args["output_dir"] = str(self.session_dir)

        # PDF to Markdown -> markdown directory
        if action_name == "convert_pdf_to_markdown" and "output_path" not in action_args:
            pdf_path = action_args.get("pdf_path", "paper.pdf")
            action_args["output_path"] = str(self.markdown_dir / (Path(pdf_path).stem + ".md"))

        # Writing tools -> posts directory
        if action_name in ("write_xiaohongshu", "write_blog") and "output_path" not in action_args:
            suffix = {"write_xiaohongshu": "xiaohongshu", "write_blog": "blog"}.get(action_name, "output")
            action_args["output_path"] = str(self.posts_dir / f"{suffix}.md")

    async def run(self, task: str) -> AgentTrace:
        """Execute a task, using native function calling when enabled."""
        if self.use_function_calling:
            try:
                return await self._run_function_calling(task)
            except Exception as e:
                # If the provider/model doesn't support tools, fall back to text ReAct.
                if self.verbose:
                    print(f"\n⚠️ Function-calling run failed ({e}); falling back to text ReAct mode.")
        return await self._run_text(task)

    async def _run_function_calling(self, task: str) -> AgentTrace:
        """Agent loop driven by the model's native tool/function calling.

        API/transport errors (e.g. a provider that doesn't support ``tools``)
        propagate to ``run()``, which then falls back to text ReAct mode.
        """
        trace = AgentTrace(task=task)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._build_system_prompt(function_calling=True)},
            {"role": "user", "content": f"Task: {task}"},
        ]
        tools = self.registry.get_schemas()

        step_num = 0
        while step_num < self.max_steps:
            step_num += 1
            if self.verbose:
                print(f"\n{'='*60}\nStep {step_num}\n{'='*60}")

            message = self.api_client.call_chat_with_tools(messages, tools=tools)
            messages.append(message)

            tool_calls = message.get("tool_calls") or []

            # No tool calls -> the model's content is the final answer.
            if not tool_calls:
                final_answer = message.get("content") or ""
                trace.steps.append(AgentStep(
                    step_num=step_num, thought="", is_final=True, final_answer=final_answer
                ))
                trace.success = True
                if self.verbose:
                    print(f"\n✅ Task completed!\nFinal Answer: {final_answer}")
                break

            # Execute every requested tool call and feed results back.
            for tool_call in tool_calls:
                fn = tool_call.get("function", {})
                action_name = fn.get("name")
                raw_args = fn.get("arguments") or "{}"
                try:
                    action_args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except json.JSONDecodeError:
                    action_args = {}

                if self.verbose:
                    _print_flush(f"\n🔧 Execute tool: {action_name}")
                    _print_flush(f"   Parameters: {json.dumps(action_args, ensure_ascii=False)}")

                self._apply_output_paths(action_name, action_args)
                result = await self.registry.execute(action_name, **action_args)
                observation = result.to_observation()

                if self.verbose:
                    obs_display = observation[:800] + "..." if len(observation) > 800 else observation
                    _print_flush(f"\n{'─'*40}\n📋 Tool result:\n{'─'*40}\n{obs_display}\n{'─'*40}")
                    if not result.success:
                        _print_flush(f"⚠️ Tool execution failed: {result.error}")

                trace.steps.append(AgentStep(
                    step_num=step_num, thought="", action=action_name,
                    action_input=action_args, observation=observation,
                ))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id"),
                    "content": observation,
                })
        else:
            trace.error = f"Reached maximum steps ({self.max_steps}), task not completed"
            if self.verbose:
                print(f"\n⚠️ {trace.error}")

        trace.end_time = datetime.now()
        return trace

    async def _run_text(self, task: str) -> AgentTrace:
        """
        Execute task (text-based ReAct fallback).

        Args:
            task: User task description

        Returns:
            AgentTrace: Execution trace
        """
        trace = AgentTrace(task=task)

        # Build initial messages
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": f"Task: {task}"}
        ]

        step_num = 0
        last_action = None  # Used to detect duplicate calls
        repeat_count = 0

        try:
            while step_num < self.max_steps:
                step_num += 1

                if self.verbose:
                    print(f"\n{'='*60}")
                    print(f"Step {step_num}")
                    print(f"{'='*60}")

                # Call SiliconFlow API
                response = self.api_client.call_chat(
                    messages,
                    max_tokens=2000,
                    temperature=0.3
                )

                if self.verbose:
                    print(f"\n🤖 Agent response:\n{response}")

                # Parse response
                thought, action_name, action_args, final_answer = self._parse_response(response)

                # Debug info
                if self.verbose:
                    _print_flush(f"\n📝 Parse result:")
                    _print_flush(f"   action_name: {action_name}")
                    _print_flush(f"   has_args: {action_args is not None}")
                    _print_flush(f"   final_answer: {'Yes' if final_answer else 'No'}")

                # Detect duplicate calls
                current_action = (action_name, json.dumps(action_args, sort_keys=True) if action_args else None)
                if current_action == last_action and action_name:
                    repeat_count += 1
                    if repeat_count >= 3:
                        _print_flush(f"\n⚠️ Detected Agent calling same tool {repeat_count} times: {action_name}")
                        _print_flush("   Force interrupt loop, add hint to let Agent try other methods...")
                        messages.append({"role": "assistant", "content": response})
                        messages.append({
                            "role": "user",
                            "content": f"⚠️ System warning: You have called {action_name} tool {repeat_count} times in a row, please do not repeat! The last call has returned results. Please proceed to the next step based on existing results, or try other methods. If the task is completed, please output Final Answer."
                        })
                        repeat_count = 0
                        last_action = None
                        continue
                else:
                    repeat_count = 0
                    last_action = current_action

                # Create step record
                step = AgentStep(
                    step_num=step_num,
                    thought=thought,
                    action=action_name,
                    action_input=action_args
                )

                # Check if completed
                if final_answer:
                    step.is_final = True
                    step.final_answer = final_answer
                    trace.steps.append(step)
                    trace.success = True

                    if self.verbose:
                        print(f"\n✅ Task completed!")
                        print(f"Final Answer: {final_answer}")

                    break

                # Execute Action
                if action_name:
                    if self.verbose:
                        _print_flush(f"\n🔧 Execute tool: {action_name}")
                        _print_flush(f"   Parameters: {json.dumps(action_args, ensure_ascii=False)}")

                    # Auto-fill output paths (using session directory)
                    self._apply_output_paths(action_name, action_args)

                    # Execute tool
                    _print_flush(f"\n   ⏳ Executing tool...")
                    result = await self.registry.execute(action_name, **action_args)
                    observation = result.to_observation()

                    step.observation = observation

                    if self.verbose:
                        _print_flush(f"\n{'─'*40}")
                        _print_flush(f"📋 Real tool return result (not LLM generated):")
                        _print_flush(f"{'─'*40}")
                        obs_display = observation[:800] + "..." if len(observation) > 800 else observation
                        _print_flush(obs_display)
                        _print_flush(f"{'─'*40}")

                        # If tool execution failed, special prompt
                        if not result.success:
                            _print_flush(f"⚠️ Tool execution failed: {result.error}")

                    # Add results to message history
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": f"Observation: {observation}"})

                else:
                    # No valid Action, prompt Agent
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": "Please continue executing the task. If you need to use a tool, please output Action in the correct format. If the task is completed, please output Final Answer."
                    })

                trace.steps.append(step)

            else:
                # Reached maximum steps
                trace.error = f"Reached maximum steps ({self.max_steps}), task not completed"
                if self.verbose:
                    print(f"\n⚠️ {trace.error}")

        except Exception as e:
            trace.error = str(e)
            trace.success = False
            if self.verbose:
                print(f"\n❌ Execution error: {e}")

        trace.end_time = datetime.now()
        return trace


class XHSPaperEngineAgent(ReActAgent):
    """
    XHS Paper Engine specific Agent

    Pre-configured with convenient methods for common tasks
    """

    def _get_research_config(self) -> Dict[str, Any]:
        """Get research area configuration"""
        return {
            "keywords": config.get("research.keywords", ["LLM", "RAG"]),
            "categories": config.get("research.categories", ["cs.AI", "cs.CL", "cs.LG"]),
            "sources": config.get("research.sources", ["arxiv", "semantic"]),
            "days": config.get("research.days", 3)
        }


# Convenience functions
def create_agent(
    work_dir: Optional[str] = None,
    verbose: bool = True
) -> XHSPaperEngineAgent:
    """Create XHS Paper Engine Agent instance"""
    return XHSPaperEngineAgent(
        work_dir=work_dir,
        verbose=verbose
    )


async def run_task(task: str, work_dir: Optional[str] = None) -> AgentTrace:
    """Convenience function to run task"""
    agent = create_agent(work_dir=work_dir)
    return await agent.run(task)
