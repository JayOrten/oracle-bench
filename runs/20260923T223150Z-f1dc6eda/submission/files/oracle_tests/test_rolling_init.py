"""Unit tests for the ``__init__`` methods in xarray/core/rolling.py.

Covers ``Rolling.__init__``, ``DataArrayRolling.__init__`` and
``DatasetRolling.__init__``, exercised both directly and through the public
``DataArray.rolling`` / ``Dataset.rolling`` entry points.
"""
import numpy as np
import pytest

import xarray as xr
from xarray.core.rolling import DataArrayRolling, DatasetRolling, Rolling
from xarray.tests import assert_identical


@pytest.fixture
def da():
    return xr.DataArray(
        np.arange(12.0).reshape(3, 4),
        dims=["x", "y"],
        coords={"x": [0, 1, 2], "y": [10, 20, 30, 40]},
    )


@pytest.fixture
def ds():
    return xr.Dataset(
        {
            "v": (["time", "x"], np.zeros((4, 3))),
            "w": (["time"], np.ones(4)),
            "z": (["y"], np.zeros(2)),
        },
        coords={"time": np.arange(4), "x": np.arange(3), "t2": ("t2", [0, 1])},
    )


class TestRollingInit:
    def test_basic_attributes(self, da):
        r = da.rolling(x=3)
        assert isinstance(r, DataArrayRolling)
        assert r.dim == ["x"]
        assert r.window == [3]
        assert r.center == [False]
        assert r.min_periods == 3
        assert r.obj is da

    def test_min_periods_default_is_product_of_windows(self, da):
        r = da.rolling(x=2, y=3)
        assert r.window == [2, 3]
        assert r.min_periods == 6

    def test_min_periods_explicit_is_preserved(self, da):
        r = da.rolling(x=3, min_periods=2)
        assert r.min_periods == 2

        # min_periods may even exceed the window size; __init__ stores as-is
        r = da.rolling(x=3, min_periods=10)
        assert r.min_periods == 10

    def test_center_scalar_broadcast_to_all_dims(self, da):
        r = da.rolling(x=2, y=3, center=True)
        assert r.center == [True, True]

    def test_center_dict_per_dim_with_false_default(self, da):
        r = da.rolling(x=2, y=3, center={"y": True})
        assert r.dim == ["x", "y"]
        assert r.center == [False, True]

    def test_center_dict_extra_keys_ignored(self, da):
        r = da.rolling(x=2, y=3, center={"y": True, "not_a_dim": True})
        assert r.center == [False, True]

    def test_center_dict_single_dim(self, da):
        r = da.rolling(x=3, center={"x": True})
        assert r.center == [True]

    def test_windows_mapping_order_preserved(self, da):
        r = da.rolling({"y": 2, "x": 3})
        assert r.dim == ["y", "x"]
        assert r.window == [2, 3]
        assert r.min_periods == 6

    @pytest.mark.parametrize("window", [0, -1, -3])
    def test_nonpositive_window_raises(self, da, window):
        with pytest.raises(ValueError, match="window must be > 0"):
            da.rolling(x=window)

    @pytest.mark.parametrize("min_periods", [0, -1])
    def test_nonpositive_min_periods_raises(self, da, min_periods):
        with pytest.raises(
            ValueError, match="min_periods must be greater than zero or None"
        ):
            da.rolling(x=3, min_periods=min_periods)

    def test_window_error_raised_before_min_periods_error(self, da):
        with pytest.raises(ValueError, match="window must be > 0"):
            da.rolling(x=0, min_periods=0)

    def test_empty_windows_mapping(self, da):
        r = Rolling(da, {})
        assert r.dim == []
        assert r.window == []
        assert r.center == []
        # math.prod([]) == 1
        assert r.min_periods == 1
        assert r.ndim == 0

    def test_base_rolling_does_not_validate_dims(self, da):
        # the base class accepts dimensions absent from the object
        r = Rolling(da, {"zz": 2})
        assert r.dim == ["zz"]
        assert r.window == [2]

    def test_ndim_matches_number_of_rolling_dims(self, da):
        assert da.rolling(x=2).ndim == 1
        assert da.rolling(x=2, y=3).ndim == 2

    def test_slots_restrict_attributes(self, da):
        r = da.rolling(x=2)
        with pytest.raises(AttributeError):
            r.foo = 1


class TestDataArrayRollingInit:
    def test_direct_construction_matches_rolling_method(self, da):
        direct = DataArrayRolling(da, {"x": 3}, min_periods=2, center=True)
        via_method = da.rolling(x=3, min_periods=2, center=True)
        assert direct.dim == via_method.dim
        assert direct.window == via_method.window
        assert direct.center == via_method.center
        assert direct.min_periods == via_method.min_periods
        assert direct.obj is via_method.obj

    def test_window_labels_from_coordinate(self, da):
        r = da.rolling(x=2)
        assert_identical(r.window_labels, da["x"])

    def test_window_labels_dim_without_coordinate(self):
        da = xr.DataArray(np.arange(4.0), dims="x")
        r = da.rolling(x=2)
        assert_identical(r.window_labels, da["x"])
        np.testing.assert_array_equal(r.window_labels.values, np.arange(4))

    def test_window_larger_than_dim_allowed(self):
        da = xr.DataArray(np.arange(3.0), dims="x")
        r = da.rolling(x=10)
        assert r.window == [10]
        assert r.min_periods == 10
        assert len(r) == 3

    def test_len_is_product_of_rolling_dim_sizes(self, da):
        assert len(da.rolling(x=2)) == 3
        assert len(da.rolling(x=2, y=3)) == 3 * 4

    def test_obj_not_modified(self, da):
        expected = da.copy(deep=True)
        da.rolling(x=3, center=True, min_periods=2)
        assert_identical(da, expected)

    def test_repr_single_dim(self, da):
        assert repr(da.rolling(x=3)) == "DataArrayRolling [x->3]"

    def test_repr_center(self, da):
        assert repr(da.rolling(x=3, center=True)) == "DataArrayRolling [x->3(center)]"

    def test_repr_multi_dim_mixed_center(self, da):
        r = da.rolling({"x": 2, "y": 3}, center={"x": True})
        assert repr(r) == "DataArrayRolling [x->2(center),y->3]"

    def test_base_rolling_repr(self, da):
        assert repr(Rolling(da, {"x": 2})) == "Rolling [x->2]"


class TestDatasetRollingInit:
    def test_basic_attributes(self, ds):
        r = ds.rolling({"x": 3, "time": 2}, min_periods=4, center={"time": True})
        assert isinstance(r, DatasetRolling)
        assert r.dim == ["x", "time"]
        assert r.window == [3, 2]
        assert r.center == [False, True]
        assert r.min_periods == 4
        assert r.obj is ds

    def test_min_periods_default_is_product_of_windows(self, ds):
        r = ds.rolling({"x": 3, "time": 2})
        assert r.min_periods == 6

    def test_missing_dim_raises_keyerror(self, ds):
        with pytest.raises(KeyError) as excinfo:
            ds.rolling(zz=3)
        assert excinfo.value.args[0] == ["zz"]

    def test_base_validation_errors_apply(self, ds):
        with pytest.raises(ValueError, match="window must be > 0"):
            ds.rolling(x=0)
        with pytest.raises(
            ValueError, match="min_periods must be greater than zero or None"
        ):
            ds.rolling(x=3, min_periods=0)

    def test_rollings_only_for_dependent_variables(self, ds):
        r = ds.rolling(x=3)
        # "w" (time only) and "z" (y only) do not depend on "x"
        assert set(r.rollings) == {"v"}
        assert isinstance(r.rollings["v"], DataArrayRolling)

    def test_rollings_empty_for_coord_only_dim(self, ds):
        # "t2" is in ds.dims (coordinate dimension) but no data_var uses it
        r = ds.rolling(t2=2)
        assert r.dim == ["t2"]
        assert r.rollings == {}

    def test_per_variable_windows_and_center(self, ds):
        r = ds.rolling({"x": 3, "time": 2}, center={"x": True})
        assert set(r.rollings) == {"v", "w"}

        v = r.rollings["v"]
        assert v.dim == ["x", "time"]
        assert v.window == [3, 2]
        assert v.center == [True, False]

        w = r.rollings["w"]
        assert w.dim == ["time"]
        assert w.window == [2]
        assert w.center == [False]

    def test_sub_rolling_obj_matches_data_var(self, ds):
        r = ds.rolling(x=3)
        assert_identical(r.rollings["v"].obj, ds["v"])

    def test_min_periods_shared_with_sub_rollings(self, ds):
        # explicit min_periods is passed through to every sub-rolling
        r = ds.rolling({"x": 3, "time": 2}, min_periods=1)
        for key in ("v", "w"):
            assert r.rollings[key].min_periods == 1

    def test_min_periods_default_recomputed_per_variable(self, ds):
        # with min_periods=None each sub-rolling defaults to the product of
        # the windows of the dims it actually depends on
        r = ds.rolling({"x": 3, "time": 2})
        assert r.min_periods == 6
        assert r.rollings["v"].min_periods == 6  # x * time
        assert r.rollings["w"].min_periods == 2  # time only

    def test_repr(self, ds):
        r = ds.rolling({"x": 3, "time": 2}, center={"x": True})
        assert repr(r) == "DatasetRolling [x->3(center),time->2]"

    def test_direct_construction_matches_rolling_method(self, ds):
        direct = DatasetRolling(ds, {"x": 3}, min_periods=2, center=True)
        via_method = ds.rolling(x=3, min_periods=2, center=True)
        assert direct.dim == via_method.dim
        assert direct.window == via_method.window
        assert direct.center == via_method.center
        assert direct.min_periods == via_method.min_periods
        assert set(direct.rollings) == set(via_method.rollings)
