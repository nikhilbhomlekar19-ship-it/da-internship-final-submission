import numpy as np
import pytest

from customer360.clv import expected_aov, expected_purchases, fit_bgnbd, fit_gg, prob_alive

TRUE = dict(r=0.9, alpha=18.0, a=0.9, b=3.0)


def simulate_bgnbd(n, T=52.0, H=13.0, seed=0):
    rng = np.random.default_rng(seed)
    lam, p = rng.gamma(TRUE["r"], 1 / TRUE["alpha"], n), rng.beta(TRUE["a"], TRUE["b"], n)
    x, tx, future = np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(n):
        t = 0.0
        while True:  # same generative story as lifetimes' generator: drop-out is possible only after a repeat purchase
            t += rng.exponential(1 / lam[i])
            if t > T + H:
                break
            if t <= T:
                x[i], tx[i] = x[i] + 1, t
            else:
                future[i] += 1
            if rng.random() < p[i]:
                break
    return x, tx, np.full(n, T), future


@pytest.fixture(scope="module")
def data():
    return simulate_bgnbd(4000)


def test_bgnbd_recovers_parameters(data):
    x, tx, T, _ = data
    p = fit_bgnbd(x, tx, T, penalizer=0.0)
    for k in ("r", "alpha", "a", "b"):
        assert p[k] == pytest.approx(TRUE[k], rel=0.45), k


def test_bgnbd_forecast_is_calibrated_on_holdout(data):
    x, tx, T, future = data
    p = fit_bgnbd(x, tx, T, penalizer=0.0)
    pred = expected_purchases(13.0, x, tx, T, p)
    assert pred.sum() == pytest.approx(future.sum(), rel=0.12)
    assert np.corrcoef(pred, future)[0, 1] > 0.25


def test_expectation_is_monotone_and_alive_prob_valid(data):
    x, tx, T, _ = data
    p = fit_bgnbd(x, tx, T, penalizer=0.0)
    e13, e26 = expected_purchases(13.0, x, tx, T, p), expected_purchases(26.0, x, tx, T, p)
    assert (e26 >= e13 - 1e-9).all() and (e13 >= 0).all()
    pa = prob_alive(x, tx, T, p)
    assert ((pa >= 0) & (pa <= 1)).all()
    assert (pa[x == 0] == 1).all()  # BG/NBD: no repeat purchase -> no evidence of churn


def test_gamma_gamma_shrinks_towards_population_mean():
    rng = np.random.default_rng(1)
    n = 3000
    nu = rng.gamma(6.0, 1 / 1.0, n)  # customer-level mean spend ~ 6 * ... (heterogeneous)
    x = rng.integers(1, 6, n).astype(float)
    m = np.array([rng.gamma(6.0 * xi, nu_i / (6.0 * xi)) for xi, nu_i in zip(x, nu)])
    g = fit_gg(x, m)
    one, many = expected_aov(np.array([1.0]), np.array([100.0]), g)[0], expected_aov(np.array([5.0]), np.array([100.0]), g)[0]
    pop = g["v"] * g["p"] / (g["q"] - 1)
    assert abs(many - 100) < abs(one - 100) and one > pop  # more repeat orders -> trust the observed mean more
