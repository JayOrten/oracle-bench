from pathlib import Path

import pytest

from oracle_bench.config import RuntimeConfig, load_config
from oracle_bench.prompts import render_prompt

ROOT = Path(__file__).parents[1]


@pytest.fixture
def resolved_config():
    config = load_config(ROOT / "configs/smoke.yaml")
    config.runtime = RuntimeConfig(
        image="example/image",
        source_roots=["app"],
        import_modules=["app"],
        existing_test_globs=["tests"],
    )
    return config


def test_prompt_controls_how_resolved_environment_is_described(resolved_config):
    prompt = render_prompt(
        "Write to ${generated_dir} from ${workdir} using ${project_python}. $$HOME is yours.",
        resolved_config,
    )

    assert prompt == (
        "Write to oracle_tests from /testbed using "
        "/opt/miniconda3/envs/testbed/bin/python. $HOME is yours."
    )


def test_localized_prompt_receives_only_the_sanitized_target(resolved_config):
    prompt = render_prompt(
        "Generate tests for ${test_target}.",
        resolved_config,
        "src/example.py (Example.run)",
    )

    assert prompt == "Generate tests for src/example.py (Example.run)."


@pytest.mark.parametrize("name", ["unit-tests.md", "localized-tests.md", "smoke-tests.md"])
def test_bundled_prompts_render(name, resolved_config):
    prompt = render_prompt((ROOT / "prompts" / name).read_text(), resolved_config, "app/subject.py")

    assert "oracle_tests" in prompt
    assert "/opt/miniconda3/envs/testbed/bin/python" in prompt
