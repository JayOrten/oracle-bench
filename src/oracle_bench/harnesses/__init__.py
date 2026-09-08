from oracle_bench.harnesses import claude, codex


def require_credentials(config):
    harness = claude if config.agent.harness == "claude" else codex
    harness.require_credentials(config)


def generate(docker, container, run_dir):
    harness = claude if docker.config.agent.harness == "claude" else codex
    return harness.generate(docker, container, run_dir)
