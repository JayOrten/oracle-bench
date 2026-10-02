"""
Unit tests for the private ``_AxesBase.__clear`` implementation
(lib/matplotlib/axes/_base.py).

``__clear`` holds the actual clearing logic; ``Axes.clear`` and ``Axes.cla``
are only adapters that delegate to it (directly, or via a subclass ``cla``
override).  Because the method is name-mangled, it is reachable from tests
as ``ax._AxesBase__clear``.
"""

import numpy as np
import pytest

import matplotlib as mpl
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib import cbook
from matplotlib.axes import Axes
from matplotlib.text import Text
from matplotlib.ticker import AutoMinorLocator, NullLocator


def _new_axes(**kwargs):
    fig = plt.figure()
    return fig.add_subplot(**kwargs)


def _populate(ax):
    """Add a grab-bag of artists/state to *ax* so clearing has work to do."""
    ax.plot([1, 2, 3], [4, 5, 6], label="data")
    ax.scatter([1, 2], [2, 1])
    ax.imshow(np.random.rand(3, 3))
    ax.fill_between([0, 1], [0, 1])
    ax.text(0.5, 0.5, "hello")
    ax.bar([0.25, 0.75], [1, 2])
    ax.legend()
    ax.set_title("center title")
    ax.set_title("left title", loc="left")
    ax.set_title("right title", loc="right")
    ax.set_xlabel("x label")
    ax.set_ylabel("y label")
    ax.set_xlim(-5, 100)
    ax.set_ylim(-5, 100)
    ax.set_xscale("log")
    ax.set_yscale("symlog")
    ax.grid(True)
    ax.margins(0.4, 0.6)


# ---------------------------------------------------------------------------
# dispatch: clear()/cla() -> __clear
# ---------------------------------------------------------------------------

def test_clear_implementation_exists_and_is_private():
    ax = _new_axes()
    assert hasattr(ax, "_AxesBase__clear")
    assert callable(ax._AxesBase__clear)
    assert not hasattr(ax, "__clear")  # name-mangled, not public


def test_clear_and_cla_both_delegate_to_private_clear():
    ax = _new_axes()
    assert ax._subclass_uses_cla is False

    calls = []
    original = ax._AxesBase__clear

    def counting_clear():
        calls.append(1)
        original()

    ax._AxesBase__clear = counting_clear
    ax.clear()
    ax.cla()
    assert len(calls) == 2


def test_private_clear_can_be_called_directly():
    ax = _new_axes()
    ax.plot([1, 2, 3], [1, 2, 3])
    ax._AxesBase__clear()
    assert len(ax.lines) == 0
    assert ax.get_xlim() == (0, 1)
    assert ax.get_ylim() == (0, 1)


def test_subclass_overriding_cla_warns_and_is_used_by_clear():
    with pytest.warns(PendingDeprecationWarning,
                      match=r"Overriding `Axes\.cla`"):
        class LegacyAxes(Axes):
            name = "legacytestaxes"

            def cla(self):
                super().cla()
                self.cla_calls = getattr(self, "cla_calls", 0) + 1

    assert LegacyAxes._subclass_uses_cla is True

    fig = plt.figure()
    ax = LegacyAxes(fig, [0, 0, 1, 1])
    fig.add_axes(ax)
    # __init__ goes through clear() -> cla() -> __clear() once.
    assert ax.cla_calls == 1

    ax.plot([1, 2], [3, 4])
    ax.clear()
    assert ax.cla_calls == 2
    assert len(ax.lines) == 0  # __clear() actually ran

    ax.plot([1, 2], [3, 4])
    ax.cla()
    assert ax.cla_calls == 3
    assert len(ax.lines) == 0


def test_plain_subclass_does_not_use_cla():
    class PlainSubclass(Axes):
        name = "plainsubclassaxes"

    assert PlainSubclass._subclass_uses_cla is False

    fig = plt.figure()
    ax = PlainSubclass(fig, [0, 0, 1, 1])
    fig.add_axes(ax)
    ax.plot([1, 2], [3, 4])
    ax.clear()
    assert len(ax.lines) == 0


# ---------------------------------------------------------------------------
# artists / children reset
# ---------------------------------------------------------------------------

def test_clear_removes_all_artists():
    ax = _new_axes()
    _populate(ax)
    assert ax.lines and ax.collections and ax.images
    assert ax.texts and ax.patches and ax.containers

    ax.clear()

    assert ax._children == []
    assert len(ax.lines) == 0
    assert len(ax.collections) == 0
    assert len(ax.images) == 0
    assert len(ax.texts) == 0
    assert len(ax.patches) == 0
    assert len(ax.tables) == 0
    assert ax.containers == []


def test_clear_keeps_only_structural_children():
    ax = _new_axes()
    old_children = ax._children
    _populate(ax)

    ax.clear()

    assert ax._children is not old_children
    children = ax.get_children()
    assert ax.title in children
    assert ax._left_title in children
    assert ax._right_title in children
    assert ax.patch in children
    assert ax.xaxis in children
    assert ax.yaxis in children
    for spine in ax.spines.values():
        assert spine in children


def test_clear_resets_current_image():
    ax = _new_axes()
    im = ax.imshow(np.random.rand(4, 4))
    ax._sci(im)
    assert ax._gci() is im

    ax.clear()

    assert ax._gci() is None
    assert ax._current_image is None


def test_clear_resets_legend():
    ax = _new_axes()
    ax.plot([1, 2], [1, 2], label="line")
    leg = ax.legend()
    assert ax.legend_ is leg

    ax.clear()

    assert ax.legend_ is None
    assert ax.get_legend() is None


def test_clear_resets_child_axes_and_projection_init():
    ax = _new_axes()
    ax.child_axes.append(_new_axes())
    ax._projection_init = ("polar", {})

    ax.clear()

    assert ax.child_axes == []
    assert ax._projection_init is None


def test_clear_resets_mouseover_set():
    ax = _new_axes()
    (line,) = ax.plot([1, 2], [1, 2])
    line.set_mouseover(True)
    assert len(ax._mouseover_set) == 1
    old_set = ax._mouseover_set

    ax.clear()

    assert ax._mouseover_set is not old_set
    assert len(ax._mouseover_set) == 0


# ---------------------------------------------------------------------------
# limits, scale, autoscale
# ---------------------------------------------------------------------------

def test_clear_resets_view_limits_and_autoscale():
    ax = _new_axes()
    _populate(ax)
    ax.set_autoscale_on(False)

    ax.clear()

    assert ax.get_xlim() == (0, 1)
    assert ax.get_ylim() == (0, 1)
    assert ax.get_autoscale_on() is True
    assert ax.get_autoscalex_on() is True
    assert ax.get_autoscaley_on() is True


def test_clear_resets_scales_to_linear():
    ax = _new_axes()
    ax.set_xscale("log")
    ax.set_yscale("symlog")

    ax.clear()

    assert ax.get_xscale() == "linear"
    assert ax.get_yscale() == "linear"
    assert ax.xaxis._scale == "linear"
    assert ax.yaxis._scale == "linear"


def test_clear_sets_ignore_existing_data_limits():
    ax = _new_axes()
    ax.plot([100, 200], [300, 400])
    ax.figure.canvas.draw()  # make stale data limits "real"
    ax.clear()

    assert ax.ignore_existing_data_limits is True

    # Old data must not influence the view limits of freshly added data.
    ax.plot([0, 1], [0, 1])
    assert ax.get_xlim() == pytest.approx((-0.05, 1.05))
    assert ax.get_ylim() == pytest.approx((-0.05, 1.05))


def test_clear_resets_margins_to_rcparams():
    ax = _new_axes()
    ax.margins(0.4, 0.6)
    assert ax._xmargin == 0.4
    assert ax._ymargin == 0.6

    ax.clear()

    assert ax._xmargin == mpl.rcParams["axes.xmargin"]
    assert ax._ymargin == mpl.rcParams["axes.ymargin"]


def test_clear_reads_margins_from_rcparams():
    with mpl.rc_context({"axes.xmargin": 0.1, "axes.ymargin": 0.2}):
        ax = _new_axes()
        ax.margins(0.5, 0.5)
        ax.clear()
        assert ax._xmargin == 0.1
        assert ax._ymargin == 0.2


def test_clear_resets_tight_and_sticky_edges_flags():
    ax = _new_axes()
    ax._tight = True
    ax._use_sticky_edges = False

    ax.clear()

    assert ax._tight is None
    assert ax._use_sticky_edges is True


# ---------------------------------------------------------------------------
# callbacks
# ---------------------------------------------------------------------------

def test_clear_replaces_callback_registry_and_drops_listeners():
    ax = _new_axes()
    old_callbacks = ax.callbacks
    calls = []
    ax.callbacks.connect("xlim_changed", lambda a: calls.append("x"))
    ax.callbacks.connect("ylim_changed", lambda a: calls.append("y"))

    ax.clear()

    assert isinstance(ax.callbacks, cbook.CallbackRegistry)
    assert ax.callbacks is not old_callbacks

    ax.set_xlim(0, 5)
    ax.set_ylim(0, 5)
    assert calls == []


def test_clear_callback_registry_declares_expected_signals():
    ax = _new_axes()
    ax.clear()

    # Signals handled by the fresh registry (no listeners: must not raise).
    for signal in ("xlim_changed", "ylim_changed", "zlim_changed"):
        ax.callbacks.process(signal, ax)

    with pytest.raises(ValueError, match="zlim_changed"):
        ax.callbacks.process("not_a_real_signal", ax)


# ---------------------------------------------------------------------------
# titles
# ---------------------------------------------------------------------------

def test_clear_resets_title_and_label_texts():
    ax = _new_axes()
    _populate(ax)

    ax.clear()

    assert ax.get_title() == ""
    assert ax.get_title(loc="left") == ""
    assert ax.get_title(loc="right") == ""
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""
    assert ax.xaxis.label.get_text() == ""
    assert ax.yaxis.label.get_text() == ""


def test_clear_recreates_title_text_objects():
    ax = _new_axes()
    old_title = ax.title
    old_left = ax._left_title
    old_right = ax._right_title

    ax.clear()

    assert ax.title is not old_title
    assert ax._left_title is not old_left
    assert ax._right_title is not old_right
    for title in (ax.title, ax._left_title, ax._right_title):
        assert isinstance(title, Text)
        assert title.get_text() == ""
        assert title.get_verticalalignment() == "baseline"
        assert title.axes is ax
        assert title.figure is ax.figure
        assert title.get_clip_box() is None
    assert ax.title.get_position() == (0.5, 1.0)
    assert ax.title.get_horizontalalignment() == "center"
    assert ax._left_title.get_position() == (0.0, 1.0)
    assert ax._left_title.get_horizontalalignment() == "left"
    assert ax._right_title.get_position() == (1.0, 1.0)
    assert ax._right_title.get_horizontalalignment() == "right"


def test_clear_titley_default_is_auto():
    assert mpl.rcParams["axes.titley"] is None
    ax = _new_axes()
    ax.clear()
    assert ax._autotitlepos is True
    assert ax.title.get_position()[1] == 1.0


def test_clear_titley_from_rcparams():
    with mpl.rc_context({"axes.titley": 0.5}):
        ax = _new_axes()
        ax.clear()
        assert ax._autotitlepos is False
        assert ax.title.get_position() == (0.5, 0.5)
        assert ax._left_title.get_position() == (0.0, 0.5)
        assert ax._right_title.get_position() == (1.0, 0.5)


def test_clear_title_fontproperties_from_rcparams():
    with mpl.rc_context({"axes.titlesize": 22, "axes.titleweight": "bold"}):
        ax = _new_axes()
        ax.set_title("small default", size=5)
        ax.clear()
        for title in (ax.title, ax._left_title, ax._right_title):
            assert title.get_size() == 22
            assert title.get_weight() == "bold"


def test_clear_resets_title_offset_from_rcparams():
    ax = _new_axes()
    ax.set_title("T", pad=50)
    assert ax.titleOffsetTrans._t == (0.0, 50 / 72)

    ax.clear()

    assert ax.titleOffsetTrans._t == (0.0, mpl.rcParams["axes.titlepad"] / 72)

    with mpl.rc_context({"axes.titlepad": 12.0}):
        ax.clear()
        assert ax.titleOffsetTrans._t == (0.0, 12.0 / 72)


# ---------------------------------------------------------------------------
# patch
# ---------------------------------------------------------------------------

def test_clear_regenerates_axes_patch():
    ax = _new_axes(facecolor="red")
    old_patch = ax.patch
    old_patch.set_visible(True)

    ax.clear()

    assert ax.patch is not old_patch
    assert ax.patch.figure is ax.figure
    assert ax.patch.get_facecolor() == mcolors.to_rgba(ax._facecolor)
    assert mcolors.same_color(ax.patch.get_facecolor(), "red")
    assert ax.patch.get_edgecolor() == mcolors.to_rgba("none")
    assert ax.patch.get_linewidth() == 0
    np.testing.assert_allclose(
        ax.patch.get_transform().get_matrix(), ax.transAxes.get_matrix())


def test_clear_axes_clip_uses_new_patch():
    ax = _new_axes()
    ax.clear()
    patch_transform = ax.patch.get_transform()
    for axis in (ax.xaxis, ax.yaxis):
        clipbox = axis.get_clipbox()
        assert clipbox is not None
        np.testing.assert_allclose(clipbox.get_points(), [[0, 0], [1, 1]])
        np.testing.assert_allclose(
            clipbox._transform.get_matrix(), patch_transform.get_matrix())


def test_clear_resets_patch_visibility_when_unshared():
    ax = _new_axes()
    ax.patch.set_visible(False)
    ax.xaxis.set_visible(False)

    ax.clear()

    # A fresh patch is visible again; visibility is only preserved for
    # shared axes.
    assert ax.patch.get_visible() is True
    assert ax.xaxis.get_visible() is False  # axis.clear() keeps visibility


# ---------------------------------------------------------------------------
# axis state
# ---------------------------------------------------------------------------

def test_clear_turns_axis_on():
    ax = _new_axes()
    ax.set_axis_off()
    assert ax.axison is False

    ax.clear()

    assert ax.axison is True


def test_clear_resets_axis_units_and_converter():
    ax = _new_axes()
    ax.plot(["a", "b", "c"], [1, 2, 3])
    assert ax.xaxis.converter is not None
    assert ax.xaxis.units is not None

    ax.clear()

    assert ax.xaxis.converter is None
    assert ax.xaxis.units is None
    assert ax.yaxis.converter is None
    assert ax.yaxis.units is None


def test_clear_resets_axis_labels_via_axis_clear():
    ax = _new_axes()
    ax.set_xlabel("x")
    ax.xaxis.set_label_coords(0.9, 0.9)
    ax.xaxis.labelpad = 42

    ax.clear()

    assert ax.get_xlabel() == ""
    assert ax.xaxis.labelpad == mpl.rcParams["axes.labelpad"]


def test_clear_resets_spines():
    ax = _new_axes()
    ax.spines["left"].set_position(("outward", 10))
    ax.spines["bottom"].set_visible(False)

    ax.clear()

    # Spine.clear() drops the custom position; the default is re-established.
    assert ax.spines["left"].get_position() == ("outward", 0.0)
    assert set(ax.spines) == {"left", "right", "bottom", "top"}
    assert ax.spines["left"].axis is ax.yaxis
    assert ax.spines["bottom"].axis is ax.xaxis


def test_clear_minor_locators_default_to_null():
    ax = _new_axes()
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.yaxis.set_minor_locator(AutoMinorLocator())

    ax.clear()

    assert isinstance(ax.xaxis.get_minor_locator(), NullLocator)
    assert isinstance(ax.yaxis.get_minor_locator(), NullLocator)


def test_clear_minor_locators_from_rcparams():
    with mpl.rc_context({"xtick.minor.visible": True,
                         "ytick.minor.visible": False}):
        ax = _new_axes()
        ax.clear()
        assert isinstance(ax.xaxis.get_minor_locator(), AutoMinorLocator)
        assert isinstance(ax.yaxis.get_minor_locator(), NullLocator)

    with mpl.rc_context({"xtick.minor.visible": False,
                         "ytick.minor.visible": True}):
        ax = _new_axes()
        ax.clear()
        assert isinstance(ax.xaxis.get_minor_locator(), NullLocator)
        assert isinstance(ax.yaxis.get_minor_locator(), AutoMinorLocator)


# ---------------------------------------------------------------------------
# grid
# ---------------------------------------------------------------------------

def test_clear_disables_grid_with_default_rcparams():
    assert mpl.rcParams["axes.grid"] is False
    ax = _new_axes()
    ax.grid(True)

    ax.clear()

    assert ax._gridOn is False
    assert not ax.xaxis._major_tick_kw["gridOn"]
    assert not ax.xaxis._minor_tick_kw["gridOn"]
    assert not ax.yaxis._major_tick_kw["gridOn"]
    assert not ax.yaxis._minor_tick_kw["gridOn"]
    assert not any(t.gridline.get_visible()
                   for t in ax.xaxis.get_major_ticks())


def test_clear_applies_grid_rcparams_major_x_only():
    with mpl.rc_context({"axes.grid": True,
                         "axes.grid.which": "major",
                         "axes.grid.axis": "x"}):
        ax = _new_axes()
        ax.clear()

        assert ax._gridOn is True
        assert ax.xaxis._major_tick_kw["gridOn"] is True
        assert ax.xaxis._minor_tick_kw["gridOn"] is False
        assert ax.yaxis._major_tick_kw["gridOn"] is False
        assert ax.yaxis._minor_tick_kw["gridOn"] is False


def test_clear_applies_grid_rcparams_both_axes():
    with mpl.rc_context({"axes.grid": True, "axes.grid.which": "both"}):
        ax = _new_axes()
        ax.clear()

        assert ax._gridOn is True
        for axis in (ax.xaxis, ax.yaxis):
            assert axis._major_tick_kw["gridOn"] is True
            assert axis._minor_tick_kw["gridOn"] is True


# ---------------------------------------------------------------------------
# property cycle
# ---------------------------------------------------------------------------

def test_clear_resets_property_cycle_helpers():
    ax = _new_axes()
    old_get_lines = ax._get_lines
    old_get_patches = ax._get_patches_for_fill
    (line1,) = ax.plot([1], [1])
    (line2,) = ax.plot([2], [2])
    assert line1.get_color() != line2.get_color()

    ax.clear()

    assert ax._get_lines is not old_get_lines
    assert ax._get_patches_for_fill is not old_get_patches
    (line3,) = ax.plot([3], [3])
    assert line3.get_color() == line1.get_color()


# ---------------------------------------------------------------------------
# staleness
# ---------------------------------------------------------------------------

def test_clear_marks_axes_stale():
    ax = _new_axes()
    ax.figure.canvas.draw()
    assert ax.stale is False

    ax.clear()

    assert ax.stale is True


# ---------------------------------------------------------------------------
# shared axes
# ---------------------------------------------------------------------------

def test_clear_preserves_visibility_on_shared_x():
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    assert ax2._sharex is ax1
    ax2.xaxis.set_visible(False)
    ax2.patch.set_visible(False)

    ax2.clear()

    assert not ax2.xaxis.get_visible()
    assert not ax2.patch.get_visible()
    # The master axes is untouched.
    assert ax1.xaxis.get_visible()
    assert ax1.patch.get_visible()


def test_clear_preserves_visibility_on_shared_y():
    fig, (ax1, ax2) = plt.subplots(1, 2, sharey=True)
    assert ax2._sharey is ax1
    ax2.yaxis.set_visible(False)
    ax2.patch.set_visible(False)

    ax2.clear()

    assert not ax2.yaxis.get_visible()
    assert not ax2.patch.get_visible()
    assert ax1.yaxis.get_visible()
    assert ax1.patch.get_visible()


def test_clear_keeps_visible_state_on_shared_axes():
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)

    ax2.clear()

    assert ax2.xaxis.get_visible()
    assert ax2.patch.get_visible()


def test_clear_resyncs_shared_x_limits_and_scale():
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    ax1.set_xscale("log")
    ax1.set_xlim(1, 100)

    ax2.clear()

    assert ax2._sharex is ax1
    assert ax2.get_xscale() == "log"
    assert ax2.get_xlim() == (1, 100)
    assert ax1 in ax2._shared_axes["x"].get_siblings(ax2)
    assert ax2 in ax1._shared_axes["x"].get_siblings(ax1)


def test_clear_resyncs_shared_y_limits():
    fig, (ax1, ax2) = plt.subplots(1, 2, sharey=True)
    ax1.set_ylim(-3, 7)

    ax2.clear()

    assert ax2._sharey is ax1
    assert ax2.get_ylim() == (-3, 7)
    assert ax1 in ax2._shared_axes["y"].get_siblings(ax2)


def test_clear_unshared_axes_resets_to_default_limits():
    fig, ax = plt.subplots()
    assert ax._sharex is None
    assert ax._sharey is None
    ax.set_xlim(10, 20)
    ax.set_ylim(30, 40)

    ax.clear()

    assert ax.get_xlim() == (0, 1)
    assert ax.get_ylim() == (0, 1)


def test_clear_keeps_master_axes_limits_on_shared_pair():
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    ax1.set_xlim(2, 8)

    # ax1 is the master (its _sharex is None): clearing it resets limits.
    ax1.clear()
    assert ax1.get_xlim() == (0, 1)

    # Clearing the follower instead re-syncs from the master.
    ax1.set_xlim(2, 8)
    ax2.clear()
    assert ax2.get_xlim() == (2, 8)


# ---------------------------------------------------------------------------
# idempotency / repeatability
# ---------------------------------------------------------------------------

def test_clear_is_idempotent():
    ax = _new_axes()
    ax.clear()
    first_children = list(ax.get_children())
    xlim, ylim = ax.get_xlim(), ax.get_ylim()

    ax.clear()

    assert ax.get_xlim() == xlim
    assert ax.get_ylim() == ylim
    assert len(ax.get_children()) == len(first_children)
    assert len(ax.lines) == 0


def test_clear_allows_replotting():
    ax = _new_axes()
    for _ in range(3):
        ax.plot([0, 1, 2], [0, 1, 2])
        ax.set_title("t")
        ax.clear()

    ax.plot([0, 10], [0, 10])
    ax.figure.canvas.draw()
    assert len(ax.lines) == 1
    assert ax.get_xlim() == pytest.approx((-0.5, 10.5))
    assert ax.get_ylim() == pytest.approx((-0.5, 10.5))
