"""Unit tests for BaseHistGradientBoosting._check_early_stopping_scorer in
sklearn/ensemble/_hist_gradient_boosting/gradient_boosting.py.

The method:
  * appends ``self.scorer_(self, X_binned_small_train, y_small_train)`` to
    ``self.train_score_``;
  * when ``self._use_validation_data`` is True, also appends
    ``self.scorer_(self, X_binned_val, y_val)`` to ``self.validation_score_``
    and returns ``self._should_stop(self.validation_score_)``;
  * otherwise returns ``self._should_stop(self.train_score_)``.
"""

import numpy as np
import pytest

from sklearn.ensemble._hist_gradient_boosting.gradient_boosting import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.metrics import (accuracy_score, check_scoring, log_loss,
                             mean_squared_error)
from sklearn.model_selection import train_test_split


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

class FakeScorer:
    """Scorer double returning canned scores and recording every call.

    The score returned is popped from ``train_values`` when the estimator is
    scored on the (identity-checked) small training set, else from
    ``val_values``.
    """

    def __init__(self, X_small, train_values, val_values=()):
        self.X_small = X_small
        self.train_values = list(train_values)
        self.val_values = list(val_values)
        self.calls = []

    def __call__(self, est, X, y):
        self.calls.append((est, X, y))
        if X is self.X_small:
            return self.train_values.pop(0)
        return self.val_values.pop(0)


def _make_binned_data(n_train=10, n_val=5, n_features=3):
    """Return dummy binned-looking arrays (uint8) and float targets."""
    X_small = np.zeros((n_train, n_features), dtype=np.uint8)
    y_small = np.zeros(n_train, dtype=np.float64)
    X_val = np.ones((n_val, n_features), dtype=np.uint8)
    y_val = np.ones(n_val, dtype=np.float64)
    return X_small, y_small, X_val, y_val


def _make_estimator(cls=HistGradientBoostingRegressor, scorer=None,
                    use_validation_data=True, n_iter_no_change=10, tol=0.):
    """Build an unfitted estimator with the early-stopping state that fit()
    would have set up before calling _check_early_stopping_scorer."""
    est = cls(n_iter_no_change=n_iter_no_change, tol=tol)
    est.scorer_ = scorer
    est.train_score_ = []
    est.validation_score_ = []
    est._use_validation_data = use_validation_data
    return est


def _call_n_times(est, n_calls, X_small, y_small, X_val, y_val):
    """Call _check_early_stopping_scorer n_calls times, return the results."""
    return [est._check_early_stopping_scorer(X_small, y_small, X_val, y_val)
            for _ in range(n_calls)]


def _expected_should_stop(scores, n_iter_no_change, tol):
    """Independent re-implementation of the documented stopping rule:
    stop if the last ``n_iter_no_change`` scores are not better (greater,
    up to ``tol``) than the (n_iter_no_change)-th-to-last score.
    """
    reference_position = n_iter_no_change + 1
    if len(scores) < reference_position:
        return False
    tol = 0 if tol is None else tol
    reference_score = scores[-reference_position] + tol
    return not any(score > reference_score
                   for score in scores[-reference_position + 1:])


def _manual_raw_predict_binned(est, X_binned):
    """Recompute raw predictions on binned data by hand: baseline prediction
    plus the sum of every tree's binned prediction."""
    raw_predictions = np.zeros((est.n_trees_per_iteration_, X_binned.shape[0]),
                               dtype=np.float64)
    raw_predictions += est._baseline_prediction
    missing_values_bin_idx = est.bin_mapper_.missing_values_bin_idx_
    for predictors_of_ith_iteration in est._predictors:
        for k, predictor in enumerate(predictors_of_ith_iteration):
            raw_predictions[k, :] += predictor.predict_binned(
                X_binned, missing_values_bin_idx)
    return raw_predictions


def _prepare_fitted_for_manual_call(est, scoring):
    """Put a fitted estimator in the state fit() uses when it calls
    _check_early_stopping_scorer (scorer_ set, _in_fit True, empty scores)."""
    est._in_fit = True
    est.scorer_ = check_scoring(est, scoring)
    est.train_score_ = []
    est.validation_score_ = []
    est.n_iter_no_change = 2
    return est


# --------------------------------------------------------------------------
# Scorer invocation / bookkeeping (with a scorer double)
# --------------------------------------------------------------------------

def test_scorer_called_with_estimator_and_both_datasets():
    X_small, y_small, X_val, y_val = _make_binned_data()
    scorer = FakeScorer(X_small, train_values=[0.1], val_values=[0.2])
    est = _make_estimator(scorer=scorer, use_validation_data=True)

    est._check_early_stopping_scorer(X_small, y_small, X_val, y_val)

    assert len(scorer.calls) == 2
    est_arg, X_arg, y_arg = scorer.calls[0]
    assert est_arg is est
    assert X_arg is X_small
    assert y_arg is y_small
    est_arg, X_arg, y_arg = scorer.calls[1]
    assert est_arg is est
    assert X_arg is X_val
    assert y_arg is y_val


def test_scores_appended_to_train_and_validation_lists():
    X_small, y_small, X_val, y_val = _make_binned_data()
    scorer = FakeScorer(X_small, train_values=[0.25], val_values=[0.75])
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=10)

    should_stop = est._check_early_stopping_scorer(X_small, y_small,
                                                   X_val, y_val)

    assert est.train_score_ == [0.25]
    assert est.validation_score_ == [0.75]
    # not enough history to early stop (n_iter_no_change=10)
    assert should_stop is False


def test_scorer_receives_small_trainset_before_validation_set():
    X_small, y_small, X_val, y_val = _make_binned_data()
    scorer = FakeScorer(X_small, train_values=[1.], val_values=[2.])
    est = _make_estimator(scorer=scorer, use_validation_data=True)

    est._check_early_stopping_scorer(X_small, y_small, X_val, y_val)

    # first call is on the training subset, second on validation
    assert scorer.calls[0][1] is X_small
    assert scorer.calls[1][1] is X_val


def test_without_validation_data_only_train_is_scored():
    X_small, y_small, _, _ = _make_binned_data()
    scorer = FakeScorer(X_small, train_values=[0.1, 0.2])
    est = _make_estimator(scorer=scorer, use_validation_data=False,
                          n_iter_no_change=10)

    est._check_early_stopping_scorer(X_small, y_small, None, None)

    assert len(scorer.calls) == 1
    assert scorer.calls[0][1] is X_small
    assert est.train_score_ == [0.1]
    assert est.validation_score_ == []

    est._check_early_stopping_scorer(X_small, y_small, None, None)
    assert est.train_score_ == [0.1, 0.2]
    assert est.validation_score_ == []


def test_scores_accumulate_in_order_over_repeated_calls():
    X_small, y_small, X_val, y_val = _make_binned_data()
    scorer = FakeScorer(X_small, train_values=[0.1, 0.2, 0.3],
                        val_values=[0.4, 0.5, 0.6])
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=100)

    _call_n_times(est, 3, X_small, y_small, X_val, y_val)

    assert est.train_score_ == [0.1, 0.2, 0.3]
    assert est.validation_score_ == [0.4, 0.5, 0.6]


# --------------------------------------------------------------------------
# Early stopping decision logic
# --------------------------------------------------------------------------

def test_return_matches_should_stop_on_validation_history():
    X_small, y_small, X_val, y_val = _make_binned_data()
    val_values = [0.1, 0.5, 0.4, 0.3, 0.35, 0.9, 0.2]
    scorer = FakeScorer(X_small, train_values=[0.] * len(val_values),
                        val_values=val_values)
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=2, tol=0.01)

    for i in range(len(val_values)):
        should_stop = est._check_early_stopping_scorer(X_small, y_small,
                                                       X_val, y_val)
        expected = _expected_should_stop(val_values[:i + 1],
                                         n_iter_no_change=2, tol=0.01)
        assert should_stop == expected
        assert should_stop == est._should_stop(est.validation_score_)


def test_return_matches_should_stop_on_train_history_without_validation():
    X_small, y_small, _, _ = _make_binned_data()
    train_values = [0.5, 0.4, 0.3, 0.45]
    scorer = FakeScorer(X_small, train_values=train_values)
    est = _make_estimator(scorer=scorer, use_validation_data=False,
                          n_iter_no_change=2, tol=0.)

    for i in range(len(train_values)):
        should_stop = est._check_early_stopping_scorer(X_small, y_small,
                                                       None, None)
        expected = _expected_should_stop(train_values[:i + 1],
                                         n_iter_no_change=2, tol=0.)
        assert should_stop == expected
        assert should_stop == est._should_stop(est.train_score_)


def test_decision_uses_validation_scores_not_train_scores():
    X_small, y_small, X_val, y_val = _make_binned_data()
    # train scores keep improving while validation scores plateau
    scorer = FakeScorer(X_small, train_values=[0.1, 0.2, 0.3],
                        val_values=[0.9, 0.9, 0.9])
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=2, tol=0.)

    returns = _call_n_times(est, 3, X_small, y_small, X_val, y_val)
    assert returns == [False, False, True]


def test_decision_false_when_validation_improves_despite_train_plateau():
    X_small, y_small, X_val, y_val = _make_binned_data()
    # train scores plateau while validation scores keep improving
    scorer = FakeScorer(X_small, train_values=[0.5, 0.5, 0.5],
                        val_values=[0.1, 0.2, 0.3])
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=2, tol=0.)

    returns = _call_n_times(est, 3, X_small, y_small, X_val, y_val)
    assert returns == [False, False, False]


@pytest.mark.parametrize('val_values, expected_returns', [
    # not enough history yet (n_iter_no_change=2 needs 3 scores)
    ([0.5, 0.4], [False, False]),
    # steadily improving
    ([0.1, 0.2, 0.3], [False, False, False]),
    # last score still improves over reference (scores[-3])
    ([0.1, 0.2, 0.2], [False, False, False]),
    # decreasing
    ([0.3, 0.2, 0.1], [False, False, True]),
    # plateau
    ([0.5, 0.5, 0.5], [False, False, True]),
    # reference is the (n_iter_no_change)-th-to-last score (0.9)
    ([0.1, 0.9, 0.5, 0.5], [False, False, False, True]),
    # big jump 2 iterations ago makes 0.95 an improvement over 0.1
    ([0.9, 0.1, 0.95, 0.2], [False, False, False, False]),
    # sliding window: reference moves to 0.4, recent scores don't beat it
    ([0.2, 0.4, 0.3, 0.35], [False, False, False, True]),
])
def test_early_stopping_scenarios(val_values, expected_returns):
    X_small, y_small, X_val, y_val = _make_binned_data()
    scorer = FakeScorer(X_small, train_values=[0.] * len(val_values),
                        val_values=val_values)
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=2, tol=0.)

    returns = _call_n_times(est, len(val_values), X_small, y_small,
                            X_val, y_val)
    assert returns == expected_returns
    assert est.validation_score_ == val_values


@pytest.mark.parametrize('train_values, expected_returns', [
    ([0.5, 0.5], [False, True]),
    ([0.5, 0.51], [False, False]),
    ([0.5, 0.4], [False, True]),
])
def test_early_stopping_scenarios_no_validation(train_values,
                                                expected_returns):
    X_small, y_small, _, _ = _make_binned_data()
    scorer = FakeScorer(X_small, train_values=train_values)
    est = _make_estimator(scorer=scorer, use_validation_data=False,
                          n_iter_no_change=1, tol=0.)

    returns = _call_n_times(est, len(train_values), X_small, y_small,
                            None, None)
    assert returns == expected_returns
    assert est.train_score_ == train_values


@pytest.mark.parametrize('tol, expected_last_return', [
    # improvement of 0.05 is not > tol=0.1 -> stop
    (0.1, True),
    # improvement of 0.05 is not > tol=0.05 (strict inequality) -> stop
    (0.05, True),
    # improvement of 0.05 is > tol=0.01 -> continue
    (0.01, False),
    (0., False),
])
def test_tol_controls_significant_improvement(tol, expected_last_return):
    X_small, y_small, X_val, y_val = _make_binned_data()
    val_values = [1.0, 1.05]
    scorer = FakeScorer(X_small, train_values=[0.] * 2, val_values=val_values)
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=1, tol=tol)

    returns = _call_n_times(est, 2, X_small, y_small, X_val, y_val)
    assert returns[-1] is expected_last_return


def test_tol_none_is_treated_as_zero():
    X_small, y_small, X_val, y_val = _make_binned_data()
    # a strictly positive improvement, however tiny, counts when tol is None
    val_values = [1.0, 1.0 + 1e-9]
    scorer = FakeScorer(X_small, train_values=[0.] * 2, val_values=val_values)
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=1, tol=None)

    returns = _call_n_times(est, 2, X_small, y_small, X_val, y_val)
    assert returns[-1] is False


def test_tol_none_still_stops_on_exact_plateau():
    X_small, y_small, X_val, y_val = _make_binned_data()
    val_values = [1.0, 1.0]
    scorer = FakeScorer(X_small, train_values=[0.] * 2, val_values=val_values)
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=1, tol=None)

    returns = _call_n_times(est, 2, X_small, y_small, X_val, y_val)
    assert returns[-1] is True


def test_n_iter_no_change_zero_stops_after_first_score():
    X_small, y_small, X_val, y_val = _make_binned_data()
    scorer = FakeScorer(X_small, train_values=[0.1], val_values=[0.2])
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=0, tol=0.)

    assert est._check_early_stopping_scorer(X_small, y_small,
                                            X_val, y_val) is True


def test_returns_are_plain_bools():
    X_small, y_small, X_val, y_val = _make_binned_data()
    scorer = FakeScorer(X_small, train_values=[0.1, 0.1, 0.1],
                        val_values=[0.2, 0.2, 0.2])
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=2, tol=0.)

    for should_stop in _call_n_times(est, 3, X_small, y_small, X_val, y_val):
        assert isinstance(should_stop, bool)


def test_scores_are_recorded_even_when_stopping():
    X_small, y_small, X_val, y_val = _make_binned_data()
    val_values = [0.5, 0.5, 0.5, 0.5]
    scorer = FakeScorer(X_small, train_values=[0.1] * 4, val_values=val_values)
    est = _make_estimator(scorer=scorer, use_validation_data=True,
                          n_iter_no_change=2, tol=0.)

    returns = _call_n_times(est, 4, X_small, y_small, X_val, y_val)
    assert returns == [False, False, True, True]
    # history keeps growing even after the stop signal was raised
    assert est.train_score_ == [0.1] * 4
    assert est.validation_score_ == val_values


# --------------------------------------------------------------------------
# Integration with real scorers on binned data (as called from fit())
# --------------------------------------------------------------------------

@pytest.fixture
def regression_data():
    rng = np.random.RandomState(0)
    X = np.linspace(0, 10, 100).reshape(-1, 1)
    y = np.sin(X.ravel()) + 0.1 * rng.randn(100)
    return train_test_split(X, y, test_size=0.25, random_state=0)


def test_real_scorer_neg_mean_squared_error_with_validation(regression_data):
    Xtr, Xva, ytr, yva = regression_data
    est = HistGradientBoostingRegressor(
        max_iter=3, scoring='loss', n_iter_no_change=None,
        random_state=0).fit(np.vstack([Xtr, Xva]), np.hstack([ytr, yva]))
    _prepare_fitted_for_manual_call(est, 'neg_mean_squared_error')
    est._use_validation_data = True

    Xb_tr = np.ascontiguousarray(est.bin_mapper_.transform(Xtr))
    Xb_va = np.ascontiguousarray(est.bin_mapper_.transform(Xva))

    should_stop = est._check_early_stopping_scorer(Xb_tr, ytr, Xb_va, yva)

    expected_train = -mean_squared_error(
        ytr, _manual_raw_predict_binned(est, Xb_tr).ravel())
    expected_val = -mean_squared_error(
        yva, _manual_raw_predict_binned(est, Xb_va).ravel())

    assert len(est.train_score_) == 1
    assert len(est.validation_score_) == 1
    assert est.train_score_[0] == pytest.approx(expected_train)
    assert est.validation_score_[0] == pytest.approx(expected_val)
    # the scorer went through predict() on binned data (_in_fit is True)
    assert est.train_score_[0] == pytest.approx(
        -mean_squared_error(ytr, est.predict(Xb_tr)))
    assert should_stop is False


def test_real_scorer_neg_mean_squared_error_without_validation(
        regression_data):
    Xtr, Xva, ytr, yva = regression_data
    est = HistGradientBoostingRegressor(
        max_iter=3, scoring='loss', n_iter_no_change=None,
        random_state=0).fit(np.vstack([Xtr, Xva]), np.hstack([ytr, yva]))
    _prepare_fitted_for_manual_call(est, 'neg_mean_squared_error')
    est._use_validation_data = False

    Xb_tr = np.ascontiguousarray(est.bin_mapper_.transform(Xtr))

    should_stop = est._check_early_stopping_scorer(Xb_tr, ytr, None, None)

    expected_train = -mean_squared_error(
        ytr, _manual_raw_predict_binned(est, Xb_tr).ravel())
    assert est.train_score_ == [pytest.approx(expected_train)]
    assert est.validation_score_ == []
    assert should_stop is False


def test_real_scorer_binary_classifier_accuracy():
    rng = np.random.RandomState(1)
    X = rng.randn(120, 3)
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    est = HistGradientBoostingClassifier(
        max_iter=3, scoring='loss', n_iter_no_change=None,
        random_state=0).fit(X, y)
    _prepare_fitted_for_manual_call(est, 'accuracy')
    est._use_validation_data = True

    Xb = np.ascontiguousarray(est.bin_mapper_.transform(X))

    should_stop = est._check_early_stopping_scorer(Xb, y, Xb[:30], y[:30])

    proba = est.loss_.predict_proba(_manual_raw_predict_binned(est, Xb))
    expected_acc = accuracy_score(y, est.classes_[np.argmax(proba, axis=1)])

    assert est.train_score_ == [pytest.approx(expected_acc)]
    assert est.validation_score_ == [pytest.approx(
        accuracy_score(y[:30], est.classes_[np.argmax(
            est.loss_.predict_proba(
                _manual_raw_predict_binned(est, Xb[:30])), axis=1)]))]
    assert should_stop is False


def test_real_scorer_multiclass_classifier_neg_log_loss():
    rng = np.random.RandomState(2)
    y = rng.randint(0, 3, size=150)
    X = rng.randn(150, 3) + y.reshape(-1, 1)
    est = HistGradientBoostingClassifier(
        max_iter=3, scoring='loss', n_iter_no_change=None,
        random_state=0).fit(X, y)
    _prepare_fitted_for_manual_call(est, 'neg_log_loss')
    est._use_validation_data = True

    Xb = np.ascontiguousarray(est.bin_mapper_.transform(X))

    should_stop = est._check_early_stopping_scorer(Xb, y, Xb[:40], y[:40])

    proba = est.loss_.predict_proba(_manual_raw_predict_binned(est, Xb))
    expected = -log_loss(y, proba)

    assert est.n_trees_per_iteration_ == 3
    assert est.train_score_ == [pytest.approx(expected)]
    assert len(est.validation_score_) == 1
    assert should_stop is False


def test_real_scorer_stops_on_plateau_across_manual_calls(regression_data):
    Xtr, Xva, ytr, yva = regression_data
    est = HistGradientBoostingRegressor(
        max_iter=3, scoring='loss', n_iter_no_change=None,
        random_state=0).fit(np.vstack([Xtr, Xva]), np.hstack([ytr, yva]))
    _prepare_fitted_for_manual_call(est, 'neg_mean_squared_error')
    est._use_validation_data = True

    Xb_tr = np.ascontiguousarray(est.bin_mapper_.transform(Xtr))
    Xb_va = np.ascontiguousarray(est.bin_mapper_.transform(Xva))

    # the model does not change between calls, so validation scores are
    # constant: with n_iter_no_change=2 the third call must trigger stopping
    returns = [est._check_early_stopping_scorer(Xb_tr, ytr, Xb_va, yva)
               for _ in range(3)]
    assert returns == [False, False, True]
    assert len(est.train_score_) == 3
    assert len(est.validation_score_) == 3
    assert np.allclose(est.validation_score_, est.validation_score_[0])


# --------------------------------------------------------------------------
# End-to-end: the method as driven by fit()
# --------------------------------------------------------------------------

def test_full_fit_scorer_early_stopping_regressor():
    rng = np.random.RandomState(42)
    X = rng.randn(300, 5)
    y = rng.randn(300)  # pure noise: validation score cannot keep improving
    est = HistGradientBoostingRegressor(
        max_iter=30, learning_rate=0.1, scoring='neg_mean_squared_error',
        n_iter_no_change=2, validation_fraction=0.2, tol=1e-7,
        random_state=0)
    est.fit(X, y)

    assert est.scorer_ is not None
    assert est.n_iter_ < est.max_iter  # early stopping actually kicked in
    # 1 score for the initial model + 1 per iteration
    assert len(est.train_score_) == est.n_iter_ + 1
    assert len(est.validation_score_) == est.n_iter_ + 1
    assert np.all(np.isfinite(est.train_score_))
    assert np.all(np.isfinite(est.validation_score_))
    # the last check is what triggered the stop
    assert est._should_stop(est.validation_score_) is True
    assert est._should_stop(est.validation_score_.tolist()) is True


def test_full_fit_scorer_early_stopping_classifier():
    rng = np.random.RandomState(42)
    X = rng.randn(300, 5)
    y = (rng.randn(300) > 0).astype(int)  # labels unrelated to X
    est = HistGradientBoostingClassifier(
        max_iter=30, learning_rate=0.1, scoring='accuracy',
        n_iter_no_change=2, validation_fraction=0.2, tol=1e-7,
        random_state=0)
    est.fit(X, y)

    assert est.scorer_ is not None
    assert est.n_iter_ < est.max_iter
    assert len(est.train_score_) == est.n_iter_ + 1
    assert len(est.validation_score_) == est.n_iter_ + 1
    assert np.all((est.train_score_ >= 0) & (est.train_score_ <= 1))
    assert np.all((est.validation_score_ >= 0) & (est.validation_score_ <= 1))
    assert est._should_stop(est.validation_score_) is True


def test_full_fit_scorer_without_validation_fraction_uses_train_scores():
    rng = np.random.RandomState(42)
    X = rng.randn(200, 4)
    y = rng.randn(200)
    est = HistGradientBoostingRegressor(
        max_iter=10, scoring='neg_mean_squared_error', n_iter_no_change=2,
        validation_fraction=None, random_state=0)
    est.fit(X, y)

    assert est._use_validation_data is False
    assert len(est.validation_score_) == 0
    assert len(est.train_score_) == est.n_iter_ + 1


def test_full_fit_warm_start_keeps_appending_scores():
    rng = np.random.RandomState(42)
    X = rng.randn(200, 4)
    y = rng.randn(200)
    est = HistGradientBoostingRegressor(
        max_iter=3, scoring='neg_mean_squared_error', n_iter_no_change=10,
        validation_fraction=0.2, warm_start=True, random_state=0)
    est.fit(X, y)
    n_scores_first_fit = len(est.train_score_)
    assert n_scores_first_fit == est.n_iter_ + 1 == 4
    assert len(est.validation_score_) == n_scores_first_fit

    est.max_iter = 6
    est.fit(X, y)

    assert est.n_iter_ == 6
    # warm start continues the score history instead of resetting it
    assert len(est.train_score_) == est.n_iter_ + 1 == 7
    assert len(est.validation_score_) == est.n_iter_ + 1 == 7
