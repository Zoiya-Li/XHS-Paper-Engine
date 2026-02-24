# Contributing Guide

Thank you for considering contributing to XHS Paper Engine! This guide will help you understand how to participate in project development.

## How to Contribute

### Reporting Issues

If you find a bug or have a new feature suggestion:

1. Search [Issues](https://github.com/yourusername/xhs-paper-engine/issues) to see if a similar issue already exists
2. If not, create a new Issue with detailed description:
   - Problem description
   - Steps to reproduce (if it's a bug)
   - Expected behavior
   - Actual behavior
   - Environment information (OS, Python version, etc.)

### Submitting Code

1. **Fork the repository**
   ```bash
   # Click the Fork button in the upper right corner of GitHub
   ```

2. **Clone to your local machine**
   ```bash
   git clone https://github.com/yourusername/xhs-paper-engine.git
   cd xhs-paper-engine
   ```

3. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Make your changes**
   - Follow existing code style
   - Add necessary tests
   - Update documentation (if needed)

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request**
   - Click "Compare & pull request" on GitHub
   - Fill in the PR description explaining your changes

## Code Standards

### Style Guide

- Use **4 spaces for indentation**
- Maximum line length: **100 characters**
- Use type annotations
- Add docstrings

```python
from typing import Optional, List

def search_papers(
    query: str,
    max_results: int = 20,
    categories: Optional[List[str]] = None
) -> dict:
    """
    Search academic papers

    Args:
        query: Search keyword
        max_results: Maximum number of results
        categories: List of arXiv categories

    Returns:
        Dictionary containing search results
    """
    # Implementation...
    pass
```

### Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation update
- `style`: Code formatting (doesn't affect functionality)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Build/toolchain related

**Example:**
```
feat(tools): add paper summary generation tool

Implemented LLM-based paper summary generation supporting:
- Single paper summary
- Batch summary generation
- Customizable summary length
```

## Development Guide

### Adding a New Tool

Create a new file in `dp_core/tools/`:

```python
from .base import Tool, ToolParameter, ToolResult, register_tool

@register_tool(
    name="my_new_tool",
    description="Tool description",
    parameters=[
        ToolParameter("param1", str, "Parameter 1 description", required=True),
        ToolParameter("param2", int, "Parameter 2 description", required=False, default=10),
    ]
)
class MyNewTool(Tool):
    async def execute(self, **kwargs) -> ToolResult:
        try:
            # Get parameters
            param1 = kwargs.get("param1")
            param2 = kwargs.get("param2", 10)

            # Implement your logic
            result = do_something(param1, param2)

            return ToolResult.success(data={"result": result})
        except Exception as e:
            return ToolResult.error(error=str(e))
```

Then export in `dp_core/tools/__init__.py`:

```python
from .your_file import MyNewTool
```

### Adding a New Publisher

Create a new file in `dp_core/publishers/` and implement a similar interface.

### Running Tests

```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_paper_tools.py

# With coverage report
pytest --cov=dp_core
```

## Release Process

Maintainers will regularly merge PRs and release new versions:

1. Update version number (`pyproject.toml`)
2. Update CHANGELOG.md
3. Create Git tag
4. Publish to PyPI (if applicable)

## Getting Help

If you have questions, you can:
- Submit an Issue
- Discuss in Discussions
- Check the Wiki documentation

## Code of Conduct

Please respect all contributors and maintain friendly and constructive communication.

---

Thank you again for your contribution!
