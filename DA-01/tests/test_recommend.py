import numpy as np

from customer360.recommend import allocate, shrink


def test_allocation_is_budget_neutral_and_respects_bands():
    S = np.array([100.0, 100.0, 100.0])
    R = np.array([[400.0, 200.0, 100.0]])
    B = np.array([[0.6, 0.6, 0.6]])
    band = np.array([0.35, 0.35, 0.10])
    x = allocate(S, R, B, band)
    assert np.isclose(x.sum(), S.sum(), rtol=1e-6)
    assert (x >= (1 - band) * S - 1e-6).all() and (x <= (1 + band) * S + 1e-6).all()
    assert x[0] > S[0] and x[1] < x[0]  # money flows to the best marginal return


def test_equal_campaigns_get_equal_money():
    x = allocate(np.array([50.0, 50.0]), np.array([[100.0, 100.0]]), np.array([[0.7, 0.7]]), np.array([0.35, 0.35]))
    assert np.allclose(x, 50.0, atol=1e-3)


def test_noisy_elasticity_shrinks_to_prior():
    assert abs(shrink(1.4, se=1.0) - 0.65) < 0.05  # very noisy -> prior
    assert abs(shrink(0.9, se=0.05) - 0.9) < 0.1  # precise -> trust the data
