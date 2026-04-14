---
name: Use uv for Python tooling
description: User prefers uv commands for dependency management, not pip
type: feedback
---

Use only native `uv` commands (uv sync, uv add, uv run, etc.) for Python dependency management.

**Why:** User explicitly corrected when pip was used. They have uv set up for this project.

**How to apply:** Always use `uv sync`, `uv add`, `uv run` instead of `pip install`, `pip`, or `python -m pip`.
