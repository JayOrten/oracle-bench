Generate a small set of unit tests for this repository. Do not modify application code.

You are working in a disposable container. The current working directory is the
repository root. Keep repository exploration within this directory; do not inspect
parent or system directories. The generated-test directory already exists and may
be empty. Work only from the visible repository snapshot; prior Git history is
intentionally unavailable.

This is a pipeline smoke check with a small request budget. Work directly without
subagents. Read one small production module, choose one or two public behaviors,
and write 2–4 focused pytest tests in a single new file. Avoid network-dependent
tests and broad repository exploration. Write the tests promptly, run them once,
and finish with a short summary.

Place new tests and fixtures under `${generated_dir}/`. Do not edit existing files
outside that directory.

The project Python is `${project_python}`. Run the generated tests with:

```sh
${project_python} -m pytest -o addopts= ${generated_dir}
```
