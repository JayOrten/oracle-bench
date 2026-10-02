"""Tests for BaseHistGradientBoosting._check_early_stopping_scorer."""
import numpy as np
import pytest
from numpy.testing import assert_allclose

from sklearn.experimental import enable_hist_gradient_boosting  # noqa
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.ensemble._hist_gradient_boosting.common import X_BINNED_DTYPE
from sklearn.datasets import make_classification, make_regression
from sklearn.metrics import check_scoring
from sklearn.model_selection import train_test_split
from sklearn.utils import check_random_state


class RecordingScorer:
    """Scorer returning pre-defined scores and recording its calls."""

    def __init__(self, scores):
        self.scores = list(scores)
        self.calls = []

    def __call__(self, est, X, y):
        self.calls.append((est, X, y))
        return self.scores[len(self.calls) - 1]


def _make_regressor(scores, use_validation_data, n_iter_no_change=2,
                    tol=0.):
    """Return a regressor set up as if fit() had initialized early stopping
    with a scorer."""
    est = HistGradientBoostingRegressor(n_iter_no_change=n_iter_no_change,
                                        tol=tol)
    est.scorer_ = RecordingScorer(scores)
    est.train_score_ = []
    est.validation_score_ = []
    est._use_validation_data = use_validation_data
    return est


# ---------------------------------------------------------------------------
# Direct unit tests of the method
# ---------------------------------------------------------------------------

def test_scorer_train_only_appends_train_score():
    est = _make_regressor([0.5], use_validation_data=False)
    X_small, y_small = np.zeros((3, 2)), np.arange(3.)

    should_stop = est._check_early_stopping_scorer(X_small, y_small,
                                                   None, None)

    assert should_stop is False
    assert est.train_score_ == [0.5]
    assert est.validation_score_ == []
    assert len(est.scorer_.calls) == 1
    called_est, called_X, called_y = est.scorer_.calls[0]
    assert called_est is est
    assert called_X is X_small
    assert called_y is y_small


def test_scorer_with_validation_appends_both_scores():
    est = _make_regressor([0.3, 0.7], use_validation_data=True)
    X_small, y_small = np.zeros((3, 2)), np.arange(3.)
    X_val, y_val = np.ones((2, 2)), np.arange(2.)

    should_stop = est._check_early_stopping_scorer(X_small, y_small,
                                                   X_val, y_val)

    assert should_stop is False
    # training data is scored first, then validation data
    assert est.train_score_ == [0.3]
    assert est.validation_score_ == [0.7]
    assert len(est.scorer_.calls) == 2
    assert est.scorer_.calls[0][0] is est
    assert est.scorer_.calls[0][1] is X_small
    assert est.scorer_.calls[0][2] is y_small
    assert est.scorer_.calls[1][0] is est
    assert est.scorer_.calls[1][1] is X_val
    assert est.scorer_.calls[1][2] is y_val


def test_scorer_accumulates_scores_over_calls():
    est = _make_regressor([1., 2., 3.], use_validation_data=False,
                          n_iter_no_change=5)
    X_small, y_small = np.zeros((3, 2)), np.arange(3.)
    for _ in range(3):
        est._check_early_stopping_scorer(X_small, y_small, None, None)
    assert est.train_score_ == [1., 2., 3.]
    assert est.validation_score_ == []


@pytest.mark.parametrize('scores, n_iter_no_change, expected', [
    # not enough scores yet: never stop
    ([1., 1.], 2, [False, False]),
    # constant scores: stop as soon as n_iter_no_change + 1 scores exist
    ([1., 1., 1.], 2, [False, False, True]),
    # strictly increasing scores: never stop
    ([1., 2., 3., 4.], 2, [False, False, False, False]),
    # decreasing scores: stop
    ([3., 2., 1.], 2, [False, False, True]),
    # improvement in the last score only is enough to continue
    ([1., 1., 2.], 2, [False, False, False]),
    # improvement then plateau
    ([1., 2., 2., 2.], 2, [False, False, False, True]),
    ([1., 1.], 1, [False, True]),
])
def test_scorer_train_only_stopping_decision(scores, n_iter_no_change,
                                             expected):
    est = _make_regressor(scores, use_validation_data=False,
                          n_iter_no_change=n_iter_no_change)
    X_small, y_small = np.zeros((3, 2)), np.arange(3.)
    decisions = [est._check_early_stopping_scorer(X_small, y_small,
                                                  None, None)
                 for _ in scores]
    assert decisions == expected
    assert est.train_score_ == scores


def test_scorer_decision_uses_validation_scores_when_available():
    # train scores keep improving but validation scores stagnate: stop
    train = [1., 2., 3.]
    val = [5., 5., 5.]
    interleaved = [s for pair in zip(train, val) for s in pair]
    est = _make_regressor(interleaved, use_validation_data=True)
    X_small, y_small = np.zeros((3, 2)), np.arange(3.)
    X_val, y_val = np.ones((2, 2)), np.arange(2.)

    decisions = [est._check_early_stopping_scorer(X_small, y_small,
                                                  X_val, y_val)
                 for _ in train]

    assert decisions == [False, False, True]
    assert est.train_score_ == train
    assert est.validation_score_ == val


def test_scorer_decision_ignores_train_scores_when_validating():
    # train scores stagnate but validation scores keep improving: continue
    train = [5., 5., 5.]
    val = [1., 2., 3.]
    interleaved = [s for pair in zip(train, val) for s in pair]
    est = _make_regressor(interleaved, use_validation_data=True)
    X_small, y_small = np.zeros((3, 2)), np.arange(3.)
    X_val, y_val = np.ones((2, 2)), np.arange(2.)

    decisions = [est._check_early_stopping_scorer(X_small, y_small,
                                                  X_val, y_val)
                 for _ in train]

    assert decisions == [False, False, False]
    assert est.train_score_ == train
    assert est.validation_score_ == val


@pytest.mark.parametrize('tol, expected_last', [
    (0., False),   # 1.5 > 1. + 0. is an improvement
    (0.4, False),  # 1.5 > 1. + 0.4 is an improvement
    (0.5, True),   # 1.5 > 1. + 0.5 is not an improvement
    (1., True),
])
def test_scorer_respects_tol(tol, expected_last):
    scores = [1., 1.2, 1.5]
    est = _make_regressor(scores, use_validation_data=False,
                          n_iter_no_change=2, tol=tol)
    X_small, y_small = np.zeros((3, 2)), np.arange(3.)
    decisions = [est._check_early_stopping_scorer(X_small, y_small,
                                                  None, None)
                 for _ in scores]
    assert decisions == [False, False, expected_last]


def test_scorer_error_propagates():
    def failing_scorer(est, X, y):
        raise RuntimeError("scorer failure")

    est = _make_regressor([], use_validation_data=False)
    est.scorer_ = failing_scorer
    with pytest.raises(RuntimeError, match="scorer failure"):
        est._check_early_stopping_scorer(np.zeros((3, 2)), np.arange(3.),
                                         None, None)
    assert est.train_score_ == []


# ---------------------------------------------------------------------------
# Tests through fit()
# ---------------------------------------------------------------------------

def _constant_scorer(est, X, y):
    return 1.


@pytest.mark.parametrize('validation_fraction', [None, 0.2])
@pytest.mark.parametrize('n_iter_no_change', [1, 3, 5])
def test_fit_constant_scorer_stops_after_n_iter_no_change(
        validation_fraction, n_iter_no_change):
    X, y = make_regression(n_samples=100, n_features=4, random_state=0)
    est = HistGradientBoostingRegressor(
        max_iter=50, n_iter_no_change=n_iter_no_change,
        scoring=_constant_scorer, validation_fraction=validation_fraction,
        random_state=0)
    est.fit(X, y)

    assert est.n_iter_ == n_iter_no_change
    assert isinstance(est.train_score_, np.ndarray)
    assert isinstance(est.validation_score_, np.ndarray)
    assert_allclose(est.train_score_, np.ones(n_iter_no_change + 1))
    if validation_fraction is None:
        assert est.validation_score_.shape == (0,)
    else:
        assert_allclose(est.validation_score_,
                        np.ones(n_iter_no_change + 1))


def test_fit_scorer_receives_binned_data_and_estimator():
    X, y = make_regression(n_samples=200, n_features=4, random_state=0)
    calls = []

    def scorer(est, X, y):
        calls.append((est, X.dtype, X.shape, y.shape))
        return 1.

    est = HistGradientBoostingRegressor(
        max_iter=10, n_iter_no_change=2, scoring=scorer,
        validation_fraction=0.25, random_state=0)
    est.fit(X, y)

    # initial scoring + one per iteration, each on train and val data
    assert len(calls) == 2 * (est.n_iter_ + 1)
    for i, (called_est, dtype, shape, y_shape) in enumerate(calls):
        assert called_est is est
        assert dtype == X_BINNED_DTYPE
        expected_n = 150 if i % 2 == 0 else 50
        assert shape == (expected_n, 4)
        assert y_shape == (expected_n,)


def test_fit_scorer_uses_small_trainset_for_large_data():
    X, y = make_regression(n_samples=10500, n_features=2, random_state=0)
    shapes = []

    def scorer(est, X, y):
        shapes.append(X.shape[0])
        return 1.

    est = HistGradientBoostingRegressor(
        max_iter=3, max_leaf_nodes=3, n_iter_no_change=1, scoring=scorer,
        validation_fraction=None, random_state=0)
    est.fit(X, y)

    assert shapes == [10000] * (est.n_iter_ + 1)


def test_fit_regressor_train_scores_match_scorer_on_training_data():
    X, y = make_regression(n_samples=200, n_features=4, noise=10,
                           random_state=0)
    est = HistGradientBoostingRegressor(
        max_iter=15, n_iter_no_change=100, scoring='neg_mean_squared_error',
        validation_fraction=None, random_state=0)
    est.fit(X, y)

    assert est.n_iter_ == 15
    assert est.train_score_.shape == (16,)
    assert est.validation_score_.shape == (0,)
    # scores are negative MSE, hence non-positive and improving on train data
    assert np.all(est.train_score_ <= 0)
    assert est.train_score_[-1] > est.train_score_[0]
    scorer = check_scoring(est, 'neg_mean_squared_error')
    assert_allclose(est.train_score_[-1], scorer(est, X, y))


def test_fit_regressor_validation_scores_match_scorer_on_validation_data():
    X, y = make_regression(n_samples=200, n_features=4, noise=10,
                           random_state=0)
    random_state = 42
    est = HistGradientBoostingRegressor(
        max_iter=15, n_iter_no_change=100, scoring='r2',
        validation_fraction=0.2, random_state=random_state)
    est.fit(X, y)

    assert est.train_score_.shape == (16,)
    assert est.validation_score_.shape == (16,)

    # reproduce the train / validation split done in fit
    seed = check_random_state(random_state).randint(1024)
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=seed)
    assert_allclose(est.train_score_[-1], est.score(X_train, y_train))
    assert_allclose(est.validation_score_[-1], est.score(X_val, y_val))
    # before any tree, the model predicts the training mean
    assert_allclose(est.train_score_[0], 0., atol=1e-12)


def test_fit_scoring_none_uses_estimator_score():
    X, y = make_regression(n_samples=200, n_features=4, noise=10,
                           random_state=0)
    est = HistGradientBoostingRegressor(
        max_iter=10, n_iter_no_change=100, scoring=None,
        validation_fraction=None, random_state=0)
    est.fit(X, y)
    assert est.scorer_ is not None
    assert_allclose(est.train_score_[-1], est.score(X, y))


def test_fit_early_stops_with_large_tol():
    X, y = make_regression(n_samples=200, n_features=4, noise=10,
                           random_state=0)
    est = HistGradientBoostingRegressor(
        max_iter=100, n_iter_no_change=3, scoring='r2', tol=10.,
        validation_fraction=None, random_state=0)
    est.fit(X, y)
    # r2 can never improve by more than 10
    assert est.n_iter_ == 3
    assert est.train_score_.shape == (4,)


def test_fit_warm_start_keeps_appending_scores():
    X, y = make_regression(n_samples=200, n_features=4, noise=10,
                           random_state=0)
    est = HistGradientBoostingRegressor(
        max_iter=5, n_iter_no_change=100, scoring='r2',
        validation_fraction=0.2, warm_start=True, random_state=0)
    est.fit(X, y)
    train_scores = est.train_score_.copy()
    val_scores = est.validation_score_.copy()
    assert train_scores.shape == (6,)

    est.set_params(max_iter=8)
    est.fit(X, y)
    assert est.n_iter_ == 8
    assert est.train_score_.shape == (9,)
    assert est.validation_score_.shape == (9,)
    assert_allclose(est.train_score_[:6], train_scores)
    assert_allclose(est.validation_score_[:6], val_scores)


@pytest.mark.parametrize('validation_fraction', [None, 0.2])
def test_fit_classifier_accuracy_scores(validation_fraction):
    X, y = make_classification(n_samples=300, n_features=5,
                               n_informative=3, random_state=0)
    est = HistGradientBoostingClassifier(
        max_iter=20, n_iter_no_change=100, scoring='accuracy',
        validation_fraction=validation_fraction, random_state=0)
    est.fit(X, y)

    assert est.train_score_.shape == (21,)
    assert np.all((est.train_score_ >= 0) & (est.train_score_ <= 1))
    if validation_fraction is None:
        assert est.validation_score_.shape == (0,)
        assert_allclose(est.train_score_[-1], est.score(X, y))
    else:
        assert est.validation_score_.shape == (21,)
        assert np.all((est.validation_score_ >= 0) &
                      (est.validation_score_ <= 1))


# The scorer compares ``est.predict(X)`` (which returns original class
# labels) with the targets it is given, so the targets passed to the scorer
# must be expressed in terms of the original class labels as well.

def test_fit_classifier_scorer_with_non_encoded_integer_labels():
    X, y = make_classification(n_samples=300, n_features=5,
                               n_informative=3, random_state=0)
    y = y + 1  # labels are {1, 2}
    est = HistGradientBoostingClassifier(
        max_iter=10, n_iter_no_change=100, scoring='accuracy',
        validation_fraction=None, random_state=0)
    est.fit(X, y)
    assert_allclose(est.train_score_[-1], est.score(X, y))


@pytest.mark.parametrize('validation_fraction', [None, 0.2])
def test_fit_classifier_scorer_with_string_labels(validation_fraction):
    X, y = make_classification(n_samples=300, n_features=5,
                               n_informative=3, random_state=0)
    y = np.array(['neg', 'pos'], dtype=object)[y]
    est = HistGradientBoostingClassifier(
        max_iter=10, n_iter_no_change=100, scoring='accuracy',
        validation_fraction=validation_fraction, random_state=0)
    est.fit(X, y)
    assert est.train_score_.shape == (11,)
    assert np.all((est.train_score_ >= 0) & (est.train_score_ <= 1))
    if validation_fraction is None:
        assert_allclose(est.train_score_[-1], est.score(X, y))


def test_fit_classifier_scorer_receives_original_labels():
    X, y = make_classification(n_samples=200, n_features=5,
                               n_informative=3, n_classes=3,
                               random_state=0)
    labels = np.array(['a', 'b', 'c'], dtype=object)
    y = labels[y]
    received = []

    def scorer(est, X, y):
        received.append(set(np.unique(y)))
        return 1.

    est = HistGradientBoostingClassifier(
        max_iter=10, n_iter_no_change=2, scoring=scorer,
        validation_fraction=0.3, random_state=0)
    est.fit(X, y)

    assert len(received) == 2 * (est.n_iter_ + 1)
    for label_set in received:
        assert label_set == {'a', 'b', 'c'}
