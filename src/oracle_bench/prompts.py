"""Render agent-authored prompts with resolved workspace information."""

from string import Template

from oracle_bench.config import RunConfig


def render_prompt(text: str, config: RunConfig) -> str:
    """Fill the small environment contract available to prompt authors."""
    runtime = config.require_runtime()
    return Template(text).substitute(
        generated_dir=config.task.generated_dir,
        project_python=runtime.python,
        workdir=runtime.workdir,
    )
