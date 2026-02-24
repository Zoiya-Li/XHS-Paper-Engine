"""
XHS Paper Engine ReAct Agent
A ReAct (Reasoning + Acting) Agent powered by DeepSeek
"""

import json
import re
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import asyncio

from .tools.base import ToolRegistry, ToolResult, default_registry
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "steps": [
                {
                    "step": s.step_num,
                    "thought": s.thought,
                    "action": s.action,
                    "action_input": s.action_input,
                    "observation": s.observation[:500] if s.observation else None,
                    "is_final": s.is_final,
                    "final_answer": s.final_answer
                }
                for s in self.steps
            ],
            "success": self.success,
            "error": self.error,
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.end_time else None
        }


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
        session_id: Optional[str] = None
    ):
        self.registry = tool_registry or default_registry
        self.api_client = APIClient()
        self.max_steps = max_steps
        self.verbose = verbose

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

    def _build_system_prompt(self) -> str:
        """Build system prompt"""
        tools_desc = self.registry.get_tool_descriptions()

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
- semantic: Semantic Scholar, with citation data, suitable for finding high-impact papers
- pubmed: Biomedical paper database
- biorxiv: Biology preprint server

**Data source selection suggestions (for reference only, you can judge independently)**:
- Find latest AI/ML papers → Prioritize arxiv
- Find highly cited papers or surveys → Prioritize semantic
- Find medical/biological related → pubmed or biorxiv
- If one source doesn't have results, try other sources

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

**Image extraction and filtering workflow**:
1. First use `extract_figures` to extract images from PDF
2. Check the `all_images` array in the result:
   - If there are images, use `select_best_images` to intelligently filter best images
   - If empty (extraction failed), use `capture_pdf_pages` to screenshot paper pages as images
3. Image filtering tool descriptions:
   - `analyze_images`: Analyze detailed information of all images in directory (dimensions, size, etc.)
   - `select_best_images`: Automatically select most suitable images for publishing (recommended)
4. **Xiaohongshu publishing**: Select 5-9 high-quality images, pass directly to `publish_xiaohongshu`

{tools_desc}

Output directories (this session):
- Paper PDFs: {self.papers_dir}
- Markdown: {self.markdown_dir}
- Images: {self.figures_dir}
- Posts: {self.posts_dir}

Working mode (ReAct mode):
You need to complete tasks following the "thought-action-observation" cycle.

**Important: You can only output Thought and Action, never output Observation!**
Observation is the result automatically returned by the system after executing the tool, you must wait for the system to return.

Each time you only need to output:
```
Thought: [Your thinking process]
Action: {{"tool": "tool_name", "args": {{parameters}}}}
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
- **Be sure to use `select_best_images` to filter images before publishing**: Xiaohongshu supports multiple images, select 5-9 most valuable ones
- If `extract_figures` returns empty `all_images`, must use `capture_pdf_pages` to get images
"""

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

    async def run(self, task: str) -> AgentTrace:
        """
        Execute task

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
                    # Download papers -> papers directory
                    if action_name == "download_paper":
                        if "output_dir" not in action_args:
                            action_args["output_dir"] = str(self.papers_dir)

                    # Extract images -> figures directory
                    if action_name == "extract_figures":
                        if "output_dir" not in action_args:
                            action_args["output_dir"] = str(self.figures_dir)

                    # Capture PDF pages -> figures directory
                    if action_name == "capture_pdf_pages":
                        if "output_dir" not in action_args:
                            action_args["output_dir"] = str(self.figures_dir)

                    # PDF to Markdown -> markdown directory
                    if action_name == "convert_pdf_to_markdown":
                        if "output_path" not in action_args:
                            pdf_path = action_args.get("pdf_path", "paper.pdf")
                            md_name = Path(pdf_path).stem + ".md"
                            action_args["output_path"] = str(self.markdown_dir / md_name)

                    # Writing tools -> posts directory
                    if action_name in ["write_xiaohongshu", "write_blog"]:
                        if "output_path" not in action_args:
                            suffix_map = {
                                "write_xiaohongshu": "xiaohongshu",
                                "write_blog": "blog"
                            }
                            suffix = suffix_map.get(action_name, "output")
                            action_args["output_path"] = str(self.posts_dir / f"{suffix}.md")

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

    def run_sync(self, task: str) -> AgentTrace:
        """Synchronously execute task"""
        return asyncio.run(self.run(task))


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

    async def find_and_publish_paper(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        platform: str = "xiaohongshu"
    ) -> AgentTrace:
        """
        Search for papers and publish to specified platform

        Args:
            query: Search keywords (if not specified, Agent decides independently)
            category: arXiv category (if not specified, Agent decides independently)
            platform: Publishing platform (xiaohongshu only)
        """
        rc = self._get_research_config()
        days = rc["days"]

        # Build task description
        query_hint = f'Keyword "{query}"' if query else f'Keywords (reference: {", ".join(rc["keywords"][:3])})'
        category_hint = f'Category {category}' if category else f'Category (reference: {", ".join(rc["categories"][:3])})'

        # Publishing platform instructions (Xiaohongshu only)
        publish_instructions = """
**Publish to Xiaohongshu**:
- Call login_xiaohongshu to let user scan QR if needed
- After login, call publish_xiaohongshu to publish"""

        task = f"""Please complete the following task:

Search conditions (for reference, you can adjust independently):
- {query_hint}
- {category_hint}
- Time range: Last {days} days

Execution steps:
1. Independently select data source and search strategy to find relevant papers
2. Check which papers have not been published yet
3. From unpublished papers, select the one with most science communication value
4. Download this paper and extract images
5. Write content (Xiaohongshu post)
{publish_instructions}
6. After successful publishing, call record_publish to record publish history

Note: record_publish is only for recording, not publishing! Must actually publish first before recording.

Please start executing."""

        return await self.run(task)

    async def generate_daily_content(self) -> AgentTrace:
        """Generate daily content and publish to platforms"""
        rc = self._get_research_config()

        keywords_str = ", ".join(rc["keywords"][:3])  # Take at most 3 keywords
        categories_str = ", ".join(rc["categories"][:3])
        days = rc["days"]

        task = f"""Please complete today's paper recommendation and publishing task:

User's research areas of interest:
- Keywords: {keywords_str}
- arXiv categories: {categories_str}
- Time range: Last {days} days

Execution steps:
1. Select appropriate data source to search papers (arxiv/semantic/pubmed/biorxiv)
2. Check deduplication, filter out already published papers
3. Select the most valuable paper
4. Download paper and extract images
5. Write Xiaohongshu post

**Publish to Xiaohongshu (must execute)**:
6. Publish to Xiaohongshu:
   - Call login_xiaohongshu to let user scan QR login if needed
   - After login, call publish_xiaohongshu to publish post
7. Record publish history (record_publish)

Note: record_publish is only for recording, not publishing! Must call publish_xiaohongshu first to actually publish.

Please start executing."""

        return await self.run(task)

    async def analyze_paper(self, arxiv_id: str) -> AgentTrace:
        """Analyze specified paper"""
        task = f"""Please analyze paper arXiv:{arxiv_id}:

1. Download this paper
2. Extract figures and tables from the paper
3. Write a detailed technical blog article
4. Summarize the paper's core contributions and innovations

Please start executing."""

        return await self.run(task)


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
