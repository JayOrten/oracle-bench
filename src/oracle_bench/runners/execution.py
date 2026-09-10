"""Stage runner settings and interpret execution evidence from a fresh sandbox."""

from oracle_bench.container.lifecycle import preserve_failure
from oracle_bench.io import read_json, write_json
from oracle_bench.runners.pytest import incomplete_result


def run_tests(sandbox, config, targets, directory):
    runtime = config.require_runtime()
    settings = {
        "workdir": runtime.workdir,
        "output": "/tmp/oracle-results",
        "targets": targets,
        "source_roots": runtime.source_roots,
        "import_modules": runtime.import_modules,
    }
    write_json(directory / "runner.json", settings)
    sandbox.upload(directory / "runner.json", "/tmp/oracle-runner.json")
    try:
        execution = sandbox.run(
            [runtime.python, sandbox.helpers + "/pytest_runner.py", "/tmp/oracle-runner.json"],
            timeout=config.limits.evaluation_seconds,
            check=False,
        )
    finally:
        # Collect evidence on every exit, without hiding an execution failure.
        with preserve_failure("Partial runner output could not be collected."):
            sandbox.download("/tmp/oracle-results", directory, contents=True, required=False)
    write_json(directory / "execution.json", vars(execution))
    return read_results(directory, execution)


def read_results(directory, execution):
    """Interpret test evidence only after process execution and collection finish."""
    if execution.timed_out:
        return incomplete_result(directory, "timeout", "Evaluation exceeded its time limit")
    if not (directory / "tests.json").exists():
        return incomplete_result(directory, "runner_error", "Runner did not produce results")
    result = read_json(directory / "tests.json")
    if execution.exit_code and result["status"] == "completed":
        return incomplete_result(directory, "runner_error", "Runner exited unsuccessfully")
    if not (directory / "coverage.json").exists():
        write_json(
            directory / "coverage.json",
            {
                "status": "unavailable",
                "reason": "Runner did not produce coverage output",
            },
        )
    return result
