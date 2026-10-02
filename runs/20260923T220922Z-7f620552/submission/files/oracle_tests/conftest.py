import matplotlib

matplotlib.use("agg")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_rcparams():
    original = dict(matplotlib.rcParams)
    yield
    matplotlib.rcParams.update(original)


@pytest.fixture(autouse=True)
def _close_all_figures():
    yield
    import matplotlib.pyplot as plt
    plt.close("all")
