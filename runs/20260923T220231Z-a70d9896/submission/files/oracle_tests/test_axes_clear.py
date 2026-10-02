"""Tests for ``_AxesBase.__clear`` (reached via ``Axes.clear`` / ``Axes.cla``)."""

import warnings

import numpy as np
import pytest

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle


def _clear_methods():
    return ["clear", "cla"]


@pytest.fixture(params=_clear_methods())
def clear(request):
    """Return a callable clearing the given Axes via clear() or cla()."""
    def _clear(ax):
        getattr(ax, request.param)()
    return _clear


# --- Children and bookkeeping -------------------------------------------------

def test_clear_removes_all_children(clear):
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    ax.scatter([1, 2], [3, 4])
    ax.imshow(np.zeros((2, 2)))
    ax.text(0.5, 0.5, "hello")
    ax.add_patch(Rectangle((0, 0), 1, 1))
    ax.bar([1, 2], [3, 4])
    ax.legend(["a"])
    assert ax.get_children()
    clear(ax)
    assert ax._children == []
    assert len(ax.lines) == 0
    assert len(ax.patches) == 0
    assert len(ax.collections) == 0
    assert len(ax.images) == 0
    assert len(ax.texts) == 0
    assert ax.containers == []
    assert ax.legend_ is None
    assert ax.get_legend() is None
    assert ax._current_image is None
    assert ax.child_axes == []
    assert len(ax._mouseover_set) == 0


def test_clear_resets_containers_and_child_axes(clear):
    fig, ax = plt.subplots()
    ax.bar([1, 2], [3, 4])
    ax.errorbar([1, 2], [1, 2], yerr=[0.1, 0.1])
    ax.inset_axes([0.5, 0.5, 0.4, 0.4])
    assert len(ax.containers) == 2
    assert len(ax.child_axes) == 1
    clear(ax)
    assert ax.containers == []
    assert ax.child_axes == []


def test_clear_resets_current_image_and_projection_init(clear):
    fig, ax = plt.subplots()
    im = ax.imshow(np.zeros((3, 3)))
    ax._sci(im)
    assert ax._current_image is im
    ax._projection_init = ("dummy", {})
    clear(ax)
    assert ax._current_image is None
    assert ax._projection_init is None


def test_clear_resets_mouseover_set(clear):
    fig, ax = plt.subplots()
    im = ax.imshow(np.zeros((3, 3)))
    assert im in ax._mouseover_set
    clear(ax)
    assert im not in ax._mouseover_set
    assert list(ax._mouseover_set) == []


def test_clear_is_idempotent_and_marks_stale(clear):
    fig, ax = plt.subplots()
    fig.canvas.draw()
    assert not ax.stale
    clear(ax)
    assert ax.stale
    clear(ax)
    assert ax.stale
    assert ax._children == []
    fig.canvas.draw()  # drawing a cleared axes must work


def test_plot_after_clear_works(clear):
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    clear(ax)
    line, = ax.plot([10, 20], [30, 40])
    assert ax.lines[0] is line
    assert line.axes is ax
    fig.canvas.draw()


# --- Limits, scales, margins and autoscaling ---------------------------------

def test_clear_resets_limits_and_autoscale(clear):
    fig, ax = plt.subplots()
    ax.plot([10, 20], [100, 200])
    ax.set_xlim(-5, 5)
    ax.set_ylim(-7, 7)
    ax.set_autoscale_on(False)
    clear(ax)
    assert ax.get_xlim() == (0, 1)
    assert ax.get_ylim() == (0, 1)
    assert ax.get_autoscalex_on()
    assert ax.get_autoscaley_on()


def test_clear_ignores_existing_data_limits(clear):
    fig, ax = plt.subplots()
    ax.plot([10, 20], [100, 200])
    assert not ax.ignore_existing_data_limits
    clear(ax)
    assert ax.ignore_existing_data_limits
    ax.plot([1, 2], [3, 4])
    ax.margins(0)
    ax.autoscale_view()
    assert ax.get_xlim() == (1, 2)
    assert ax.get_ylim() == (3, 4)


def test_clear_resets_scale_to_linear(clear):
    fig, ax = plt.subplots()
    ax.set_xscale("log")
    ax.set_yscale("symlog")
    clear(ax)
    assert ax.get_xscale() == "linear"
    assert ax.get_yscale() == "linear"
    # transScale must be updated consistently with the new linear scale.
    np.testing.assert_allclose(
        ax.transScale.transform([[2.0, 3.0]]), [[2.0, 3.0]])


def test_clear_resets_margins_from_rcparams(clear):
    fig, ax = plt.subplots()
    ax.margins(0.3, 0.4)
    mpl.rcParams["axes.xmargin"] = 0.11
    mpl.rcParams["axes.ymargin"] = 0.22
    clear(ax)
    assert ax.margins() == (0.11, 0.22)


def test_clear_resets_tight_and_sticky_edges(clear):
    fig, ax = plt.subplots()
    ax.use_sticky_edges = False
    ax.autoscale(tight=True)
    assert ax._tight
    clear(ax)
    assert ax._tight is None
    assert ax.use_sticky_edges is True


# --- Callbacks ---------------------------------------------------------------

def test_clear_replaces_callback_registry(clear):
    fig, ax = plt.subplots()
    calls = []
    ax.callbacks.connect("xlim_changed", lambda a: calls.append("x"))
    ax.callbacks.connect("ylim_changed", lambda a: calls.append("y"))
    old = ax.callbacks
    clear(ax)
    assert ax.callbacks is not old
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    assert calls == []


def test_clear_callback_registry_signals(clear):
    fig, ax = plt.subplots()
    clear(ax)
    for sig in ["xlim_changed", "ylim_changed", "zlim_changed"]:
        ax.callbacks.connect(sig, lambda a: None)
    with pytest.raises(ValueError):
        ax.callbacks.connect("not_a_signal", lambda a: None)
    calls = []
    ax.callbacks.connect("xlim_changed", lambda a: calls.append(a))
    ax.set_xlim(2, 3)
    assert calls == [ax]


# --- Ticks / minor locators --------------------------------------------------

def test_clear_minor_locator_follows_rcparams(clear):
    fig, ax = plt.subplots()
    assert not isinstance(ax.xaxis.get_minor_locator(),
                          mticker.AutoMinorLocator)
    mpl.rcParams["xtick.minor.visible"] = True
    mpl.rcParams["ytick.minor.visible"] = False
    clear(ax)
    assert isinstance(ax.xaxis.get_minor_locator(), mticker.AutoMinorLocator)
    assert not isinstance(ax.yaxis.get_minor_locator(),
                          mticker.AutoMinorLocator)

    mpl.rcParams["xtick.minor.visible"] = False
    mpl.rcParams["ytick.minor.visible"] = True
    clear(ax)
    assert not isinstance(ax.xaxis.get_minor_locator(),
                          mticker.AutoMinorLocator)
    assert isinstance(ax.yaxis.get_minor_locator(), mticker.AutoMinorLocator)


def test_clear_resets_custom_locators_and_formatters(clear):
    fig, ax = plt.subplots()
    ax.xaxis.set_major_locator(mticker.FixedLocator([0.1, 0.2]))
    ax.xaxis.set_major_formatter(mticker.NullFormatter())
    clear(ax)
    assert isinstance(ax.xaxis.get_major_locator(), mticker.AutoLocator)
    assert isinstance(ax.xaxis.get_major_formatter(), mticker.ScalarFormatter)


def test_clear_resets_axis_labels(clear):
    fig, ax = plt.subplots()
    ax.set_xlabel("xlabel")
    ax.set_ylabel("ylabel")
    clear(ax)
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""


# --- Grid --------------------------------------------------------------------

def _gridlines_visible(axis, which="major"):
    ticks = axis.get_major_ticks() if which == "major" \
        else axis.get_minor_ticks()
    return [t.gridline.get_visible() for t in ticks]


def test_clear_turns_off_grid_by_default(clear):
    fig, ax = plt.subplots()
    ax.grid(True)
    assert all(_gridlines_visible(ax.xaxis))
    clear(ax)
    assert ax._gridOn is False
    assert not any(_gridlines_visible(ax.xaxis))
    assert not any(_gridlines_visible(ax.yaxis))


def test_clear_grid_follows_rcparams(clear):
    fig, ax = plt.subplots()
    mpl.rcParams["axes.grid"] = True
    mpl.rcParams["axes.grid.axis"] = "y"
    mpl.rcParams["axes.grid.which"] = "major"
    clear(ax)
    assert ax._gridOn is True
    assert not any(_gridlines_visible(ax.xaxis))
    assert all(_gridlines_visible(ax.yaxis))


def test_clear_grid_rcparams_both_axes(clear):
    fig, ax = plt.subplots()
    mpl.rcParams["axes.grid"] = True
    mpl.rcParams["axes.grid.axis"] = "both"
    clear(ax)
    assert all(_gridlines_visible(ax.xaxis))
    assert all(_gridlines_visible(ax.yaxis))


# --- Titles ------------------------------------------------------------------

def test_clear_resets_titles(clear):
    fig, ax = plt.subplots()
    ax.set_title("center")
    ax.set_title("left", loc="left")
    ax.set_title("right", loc="right")
    old_title = ax.title
    clear(ax)
    assert ax.title is not old_title
    assert ax.get_title() == ""
    assert ax.get_title(loc="left") == ""
    assert ax.get_title(loc="right") == ""
    assert ax.title.get_horizontalalignment() == "center"
    assert ax._left_title.get_horizontalalignment() == "left"
    assert ax._right_title.get_horizontalalignment() == "right"
    for t in (ax.title, ax._left_title, ax._right_title):
        assert t.get_verticalalignment() == "baseline"
        assert t.axes is ax
        assert t.figure is fig
        assert t.get_clip_box() is None
    assert ax.title.get_position()[0] == 0.5
    assert ax._left_title.get_position()[0] == 0.0
    assert ax._right_title.get_position()[0] == 1.0


def test_clear_title_font_from_rcparams(clear):
    fig, ax = plt.subplots()
    mpl.rcParams["axes.titlesize"] = 21
    mpl.rcParams["axes.titleweight"] = "bold"
    clear(ax)
    for t in (ax.title, ax._left_title, ax._right_title):
        assert t.get_fontsize() == 21
        assert t.get_fontweight() == "bold"
    # left/right titles get independent copies of the font properties.
    assert ax._left_title.get_fontproperties() is not \
        ax.title.get_fontproperties()
    assert ax._right_title.get_fontproperties() is not \
        ax.title.get_fontproperties()
    ax._left_title.set_fontsize(5)
    assert ax.title.get_fontsize() == 21
    assert ax._right_title.get_fontsize() == 21


def test_clear_title_autopos_default(clear):
    fig, ax = plt.subplots()
    assert mpl.rcParams["axes.titley"] is None
    clear(ax)
    assert ax._autotitlepos is True
    for t in (ax.title, ax._left_title, ax._right_title):
        assert t.get_position()[1] == 1.0


def test_clear_title_y_from_rcparams(clear):
    fig, ax = plt.subplots()
    mpl.rcParams["axes.titley"] = 1.2
    clear(ax)
    assert ax._autotitlepos is False
    for t in (ax.title, ax._left_title, ax._right_title):
        assert t.get_position()[1] == 1.2


def test_clear_title_pad_from_rcparams(clear):
    fig, ax = plt.subplots()
    ax.set_title("t", pad=50)
    mpl.rcParams["axes.titlepad"] = 36
    clear(ax)
    # 36 points == 0.5 inch
    expected = fig.dpi_scale_trans.transform((0, 0.5)) \
        - fig.dpi_scale_trans.transform((0, 0))
    got = ax.titleOffsetTrans.transform((0, 0))
    np.testing.assert_allclose(got, expected)
    for t in (ax.title, ax._left_title, ax._right_title):
        np.testing.assert_allclose(
            t.get_transform().transform((0.5, 1.0)),
            (ax.transAxes + ax.titleOffsetTrans).transform((0.5, 1.0)))


# --- Patch -------------------------------------------------------------------

def test_clear_regenerates_patch(clear):
    fig, ax = plt.subplots(facecolor="none")
    ax.set_facecolor("red")
    old_patch = ax.patch
    clear(ax)
    assert ax.patch is not old_patch
    assert isinstance(ax.patch, Rectangle)
    assert ax.patch.figure is fig
    # facecolor is retained across clear
    assert mpl.colors.same_color(ax.patch.get_facecolor(), "red")
    assert mpl.colors.same_color(ax.get_facecolor(), "red")
    assert ax.patch.get_edgecolor()[3] == 0
    assert ax.patch.get_linewidth() == 0
    assert ax.patch.get_data_transform() is ax.transAxes


def test_clear_uses_initial_facecolor_kwarg(clear):
    fig = plt.figure()
    ax = fig.add_subplot(facecolor="yellow")
    clear(ax)
    assert mpl.colors.same_color(ax.patch.get_facecolor(), "yellow")


def test_clear_unshared_patch_visibility_reset(clear):
    fig, ax = plt.subplots()
    ax.patch.set_visible(False)
    clear(ax)
    assert ax.patch.get_visible()


def test_clear_uses_gen_axes_patch():
    class MyAxes(Axes):
        name = "oracle_my_axes_patch"
        n_calls = 0

        def _gen_axes_patch(self):
            type(self).n_calls += 1
            return Rectangle((0.1, 0.1), 0.5, 0.5)

    fig = plt.figure()
    ax = MyAxes(fig, [0.1, 0.1, 0.8, 0.8])
    fig.add_axes(ax)
    before = MyAxes.n_calls
    ax.clear()
    assert MyAxes.n_calls == before + 1
    assert ax.patch.get_xy() == (0.1, 0.1)
    assert ax.patch.get_width() == 0.5


def test_clear_turns_axis_on(clear):
    fig, ax = plt.subplots()
    ax.set_axis_off()
    assert not ax.axison
    clear(ax)
    assert ax.axison


def test_clear_axis_clipped_to_patch(clear):
    fig, ax = plt.subplots()
    clear(ax)
    np.testing.assert_allclose(ax.xaxis.get_clip_box().bounds,
                               ax.bbox.bounds)
    np.testing.assert_allclose(ax.yaxis.get_clip_box().bounds,
                               ax.bbox.bounds)


def test_clear_spines_survive(clear):
    fig, ax = plt.subplots()
    spines = dict(ax.spines)
    clear(ax)
    assert set(ax.spines.keys()) == {"left", "right", "top", "bottom"}
    for name, spine in ax.spines.items():
        assert spine is spines[name]
    fig.canvas.draw()


# --- Property cycle ----------------------------------------------------------

def test_clear_resets_property_cycle(clear):
    fig, ax = plt.subplots()
    colors = mpl.rcParams["axes.prop_cycle"].by_key()["color"]
    l1, = ax.plot([1, 2])
    l2, = ax.plot([1, 2])
    assert mpl.colors.same_color(l2.get_color(), colors[1])
    clear(ax)
    l3, = ax.plot([1, 2])
    assert mpl.colors.same_color(l3.get_color(), colors[0])


def test_clear_resets_fill_cycle(clear):
    fig, ax = plt.subplots()
    colors = mpl.rcParams["axes.prop_cycle"].by_key()["color"]
    ax.fill([0, 1, 1], [0, 0, 1])
    p2, = ax.fill([0, 1, 1], [0, 0, 1])
    assert mpl.colors.same_color(p2.get_facecolor(), colors[1])
    clear(ax)
    p3, = ax.fill([0, 1, 1], [0, 0, 1])
    assert mpl.colors.same_color(p3.get_facecolor(), colors[0])


def test_clear_discards_custom_prop_cycle(clear):
    fig, ax = plt.subplots()
    ax.set_prop_cycle(color=["magenta"])
    l1, = ax.plot([1, 2])
    assert mpl.colors.same_color(l1.get_color(), "magenta")
    clear(ax)
    l2, = ax.plot([1, 2])
    assert mpl.colors.same_color(
        l2.get_color(), mpl.rcParams["axes.prop_cycle"].by_key()["color"][0])


# --- Shared axes -------------------------------------------------------------

def test_clear_shared_x_keeps_sharing(clear):
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    ax1.plot([0, 10], [0, 1])
    clear(ax2)
    assert ax2._sharex is ax1
    assert ax2.get_shared_x_axes().joined(ax1, ax2)
    assert ax2.get_xlim() == ax1.get_xlim()
    ax1.set_xlim(3, 4)
    assert ax2.get_xlim() == (3, 4)
    ax2.set_xlim(5, 6)
    assert ax1.get_xlim() == (5, 6)
    assert ax2.xaxis.major is ax1.xaxis.major
    assert ax2.xaxis.minor is ax1.xaxis.minor


def test_clear_shared_y_keeps_sharing(clear):
    fig, (ax1, ax2) = plt.subplots(1, 2, sharey=True)
    ax1.set_ylim(-3, 3)
    clear(ax2)
    assert ax2._sharey is ax1
    assert ax2.get_ylim() == (-3, 3)
    ax2.set_ylim(1, 2)
    assert ax1.get_ylim() == (1, 2)
    assert ax2.yaxis.major is ax1.yaxis.major


def test_clear_shared_keeps_scale_of_leader(clear):
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    ax1.set_xscale("log")
    ax1.set_xlim(1, 100)
    clear(ax2)
    assert ax2.get_xscale() == "log"
    assert ax2.get_xlim() == (1, 100)


def test_clear_shared_preserves_axis_visibility(clear):
    fig, (ax1, ax2) = plt.subplots(2, sharex=True, sharey=True)
    ax2.xaxis.set_visible(False)
    ax2.yaxis.set_visible(False)
    clear(ax2)
    assert not ax2.xaxis.get_visible()
    assert not ax2.yaxis.get_visible()


def test_clear_shared_preserves_visible_axis(clear):
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    assert ax2.xaxis.get_visible()
    clear(ax2)
    assert ax2.xaxis.get_visible()


@pytest.mark.parametrize("share", ["sharex", "sharey"])
def test_clear_shared_preserves_patch_visibility(clear, share):
    fig, (ax1, ax2) = plt.subplots(2, **{share: True})
    ax2.patch.set_visible(False)
    old_patch = ax2.patch
    clear(ax2)
    assert ax2.patch is not old_patch
    assert not ax2.patch.get_visible()


def test_clear_twinx_preserves_patch_invisible(clear):
    fig, ax = plt.subplots()
    ax2 = ax.twiny()  # shares y with ax; its patch is hidden
    assert not ax2.patch.get_visible()
    clear(ax2)
    assert not ax2.patch.get_visible()
    assert ax2._sharey is ax


def test_clear_leader_of_shared_axes(clear):
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    ax2.set_xlim(3, 4)
    clear(ax1)
    assert ax1._sharex is None
    assert ax1.get_xlim() == (0, 1)
    assert ax2.get_xlim() == (0, 1)
    ax1.set_xlim(5, 6)
    assert ax2.get_xlim() == (5, 6)


def test_clear_shared_autoscale_picks_up_sibling_data(clear):
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    ax1.plot([10, 20], [0, 1])
    clear(ax2)
    ax2.plot([0, 1], [0, 1])
    ax1.margins(0)
    ax2.margins(0)
    ax2.autoscale_view()
    assert ax2.get_xlim() == (0, 20)
    assert ax1.get_xlim() == (0, 20)


def test_clear_after_removing_shared_sibling(clear):
    fig, (ax1, ax2) = plt.subplots(2, sharex=True)
    ax3 = fig.add_subplot(3, 1, 3, sharex=ax1)
    ax3.remove()
    clear(ax1)
    siblings = ax1.get_shared_x_axes().get_siblings(ax1)
    assert ax1 in siblings and ax2 in siblings
    assert ax3 not in siblings
    ax1.set_xlim(2, 3)
    assert ax2.get_xlim() == (2, 3)


# --- clear()/cla() dispatching to __clear ------------------------------------

def test_clear_and_cla_are_equivalent():
    fig, (ax1, ax2) = plt.subplots(2)
    for ax in (ax1, ax2):
        ax.plot([1, 2, 3])
        ax.set_title("x")
        ax.set_xscale("log")
    ax1.clear()
    ax2.cla()
    for ax in (ax1, ax2):
        assert ax._children == []
        assert ax.get_title() == ""
        assert ax.get_xscale() == "linear"
        assert ax.get_xlim() == (0, 1)


def test_subclass_overriding_clear_is_called_by_cla():
    calls = []

    class ClearAxes(Axes):
        name = "oracle_clear_axes"

        def clear(self):
            calls.append("clear")
            super().clear()

    assert not ClearAxes._subclass_uses_cla
    fig = plt.figure()
    ax = ClearAxes(fig, [0.1, 0.1, 0.8, 0.8])
    calls.clear()
    ax.plot([1, 2])
    ax.cla()
    assert calls == ["clear"]
    assert ax._children == []
    calls.clear()
    ax.clear()
    assert calls == ["clear"]


def test_subclass_overriding_cla_is_called_by_clear():
    calls = []

    with pytest.warns(PendingDeprecationWarning, match="Overriding `Axes.cla`"):
        class ClaAxes(Axes):
            name = "oracle_cla_axes"

            def cla(self):
                calls.append("cla")
                super().cla()

    assert ClaAxes._subclass_uses_cla
    fig = plt.figure()
    ax = ClaAxes(fig, [0.1, 0.1, 0.8, 0.8])
    calls.clear()
    ax.plot([1, 2])
    ax.set_title("t")
    ax.clear()
    assert calls == ["cla"]
    assert ax._children == []
    assert ax.get_title() == ""
    calls.clear()
    ax.cla()
    assert calls == ["cla"]


def test_grandchild_of_cla_subclass_inherits_cla_dispatch():
    calls = []

    with pytest.warns(PendingDeprecationWarning):
        class ClaAxes(Axes):
            name = "oracle_cla_axes_parent"

            def cla(self):
                calls.append("cla")
                super().cla()

    with warnings.catch_warnings():
        warnings.simplefilter("error")

        class GrandChild(ClaAxes):
            name = "oracle_cla_axes_grandchild"

    assert GrandChild._subclass_uses_cla
    fig = plt.figure()
    ax = GrandChild(fig, [0.1, 0.1, 0.8, 0.8])
    calls.clear()
    ax.plot([1])
    ax.clear()
    assert calls == ["cla"]
    assert ax._children == []


def test_plain_subclass_does_not_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error")

        class Plain(Axes):
            name = "oracle_plain_axes"

    assert not Plain._subclass_uses_cla
    fig = plt.figure()
    ax = Plain(fig, [0.1, 0.1, 0.8, 0.8])
    ax.plot([1, 2])
    ax.clear()
    assert ax._children == []


# --- Integration with Figure / pyplot ----------------------------------------

def test_figure_clear_then_new_axes():
    fig, ax = plt.subplots()
    ax.plot([1, 2])
    fig.clear()
    ax2 = fig.add_subplot()
    assert ax2.get_xlim() == (0, 1)
    assert ax2._children == []


def test_pyplot_cla_clears_current_axes():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    ax.set_title("title")
    plt.cla()
    assert ax._children == []
    assert ax.get_title() == ""
    assert plt.gca() is ax


def test_polar_axes_clear():
    fig = plt.figure()
    ax = fig.add_subplot(projection="polar")
    ax.plot([0, 1], [1, 2])
    ax.set_title("polar")
    ax.clear()
    assert ax._children == []
    assert ax.get_title() == ""
    assert ax.get_xlim() == pytest.approx((0, 2 * np.pi))
    fig.canvas.draw()
