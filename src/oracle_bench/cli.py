import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from oracle_bench.config import load_config
from oracle_bench.io import read_json
from oracle_bench.report import report
from oracle_bench.run import reevaluate, run


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate tests and evaluate buggy/golden outcomes"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Run one configured instance").add_argument("config", type=Path)
    sub.add_parser("evaluate", help="Reevaluate saved tests without calling a model").add_argument(
        "run_dir", type=Path
    )
    sub.add_parser("report", help="Render saved results without executing code").add_argument(
        "run_dir", type=Path
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            load_dotenv(Path.cwd() / ".env", override=False, interpolate=False)
            output = run(load_config(args.config))
        elif args.command == "evaluate":
            output = reevaluate(args.run_dir.resolve())
        else:
            output = report(args.run_dir.resolve())
        print(output)
        if args.command != "report":
            run_dir = output if args.command == "run" else args.run_dir
            if read_json(run_dir / "status.json")["state"] == "completed_with_errors":
                return 2
        return 0
    except KeyboardInterrupt:
        print("oracle-bench: interrupted", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError, OSError, TypeError) as exc:
        print(f"oracle-bench: {exc}", file=sys.stderr)
        return 1
