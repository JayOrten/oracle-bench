from oracle_bench.harnesses import claude, codex


def require_credentials(config):
    harness = claude if config.agent.harness == "claude" else codex
    harness.require_credentials(config)


def generate(sandbox, config, run_dir):
    harness = claude if config.agent.harness == "claude" else codex
    return harness.generate(sandbox, config, run_dir)
