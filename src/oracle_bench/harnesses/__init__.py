from oracle_bench.harnesses import claude, codex, opencode

HARNESSES = {"claude": claude, "codex": codex, "opencode": opencode}


def require_credentials(config):
    HARNESSES[config.agent.harness].require_credentials(config)


def generate(sandbox, config, run_dir):
    return HARNESSES[config.agent.harness].generate(sandbox, config, run_dir)
