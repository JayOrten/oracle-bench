import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _mpl_state():
    with matplotlib.rc_context():
        matplotlib.rcdefaults()
        yield
    plt.close("all")
