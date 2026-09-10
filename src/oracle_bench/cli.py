import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from oracle_bench.batch import run_batch
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
    batch_parser = sub.add_parser("batch", help="Run or resume an explicit batch")
    batch_parser.add_argument(
        "path", type=Path, help="Batch YAML, or batch directory with --resume"
    )
    batch_parser.add_argument("--resume", action="store_true", help="Resume pending jobs")
    sub.add_parser("evaluate", help="Reevaluate saved tests without calling a model").add_argument(
        "run_dir", type=Path
    )
    sub.add_parser("report", help="Render saved results without executing code").add_argument(
        "run_dir", type=Path
    )
    args = parser.parse_args(argv)
    try:
        if args.command in {"run", "batch"}:
            load_dotenv(Path.cwd() / ".env", override=False, interpolate=False)
        if args.command == "run":
            output = run(load_config(args.config))
        elif args.command == "batch":
            output = run_batch(args.path, resume=args.resume)
        elif args.command == "evaluate":
            output = reevaluate(args.run_dir.resolve())
        else:
            output = report(args.run_dir.resolve())
        print(output)
        if args.command != "report":
            run_dir = output if args.command in {"run", "batch"} else args.run_dir
            if read_json(run_dir / "status.json")["state"] == "completed_with_errors":
                return 2
        return 0
    except KeyboardInterrupt:
        print("oracle-bench: interrupted", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError, OSError, TypeError) as exc:
        print(f"oracle-bench: {exc}", file=sys.stderr)
        return 1
