from oracle_bench.datasets import swebench


def resolve_source(config):
    if config.kind == "swebench":
        return swebench.resolve(config)
    raise ValueError(f"Unsupported source adapter {config.kind!r}")
