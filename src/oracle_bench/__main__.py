"""Lets you run `python -m oracle_bench`. The `oracle-bench` command skips this."""

from oracle_bench.cli import main

raise SystemExit(main())
