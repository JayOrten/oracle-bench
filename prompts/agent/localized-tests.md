Generate unit tests for the following area of this repository:

`${test_target}`

Do not modify the application code.

Place new tests and fixtures under `${generated_dir}/`. Do not edit existing files
outside that directory.

The project Python is `${project_python}`. Run the generated tests with:

```sh
${project_python} -m pytest -o addopts= ${generated_dir}
```
