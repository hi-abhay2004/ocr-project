"""
ai/preprocessing.py (L1) — synthetic fixtures with a known injected skew and
known noise level, so the assertions are about the algorithm, not about
whether a real scan happens to look clean.
"""

from ai.preprocessing import estimate_skew, preprocess, quality_score, to_gray
from tests.unit.cv_fixtures import add_noise, blur, clean_answer_block, rotate


def _gray_page():
    img, _ = clean_answer_block(["BCNF is a normal form for relational schemas."])
    return to_gray(img)


def test_quality_score_is_high_for_clean_text():
    assert quality_score(_gray_page()) > 0.5


def test_quality_score_drops_for_blurred_noisy_text():
    img, _ = clean_answer_block(["BCNF is a normal form for relational schemas."])
    degraded = to_gray(add_noise(blur(img, k=9), sigma=25))
    assert quality_score(degraded) < quality_score(_gray_page())


def test_estimate_skew_recovers_a_known_rotation():
    # The sign here is an internal convention, not an external "positive
    # means counterclockwise" contract: estimate_skew()'s angle is only ever
    # consumed by deskew(), which applies cv2.getRotationMatrix2D with that
    # SAME angle — see test_preprocess_deskews_a_rotated_page for the
    # property that actually matters (deskew(img, estimate_skew(img))
    # reduces residual skew).
    gray = _gray_page()
    rotated = to_gray(rotate(gray[..., None].repeat(3, axis=2), 6.0))
    angle = estimate_skew(rotated)
    assert -9.0 < angle < -3.0  # roughly the injected magnitude, opposite sign


def test_estimate_skew_is_near_zero_for_an_upright_page():
    assert abs(estimate_skew(_gray_page())) < 1.0


def test_estimate_skew_recovers_a_large_real_world_rotation():
    # A real phone photo can be tilted far more than a scanner bed ever
    # would be — the old minAreaRect-based estimate was never validated
    # past small angles. Multiple lines give the row-profile search a
    # real peak to find (see the module comment in ai/preprocessing.py).
    img, _ = clean_answer_block(
        [
            "BCNF is a normal form for relational schemas.",
            "It removes redundancy from the schema design.",
            "A relation is in BCNF if every determinant is a superkey.",
        ]
    )
    rotated = rotate(img, 25.0)
    angle = estimate_skew(to_gray(rotated))
    assert -30.0 < angle < -20.0  # roughly the injected magnitude, opposite sign


def test_estimate_skew_is_robust_to_real_world_noise_on_a_nearly_upright_page():
    # The actual bug this replaced a minAreaRect-based estimate for
    # (verified 2026-08-27 against a real upload): shadows, paper wrinkles
    # and compression artifacts on a genuinely near-upright photographed
    # page pulled the OLD estimate to a false ~30 degrees, and deskew()
    # then rotated an already-fine page into a badly tilted mess — a false
    # positive is worse than no correction at all. Blur+noise here stand
    # in for that real-world messiness.
    img, _ = clean_answer_block(
        [
            "BCNF is a normal form for relational schemas.",
            "It removes redundancy from the schema design.",
            "A relation is in BCNF if every determinant is a superkey.",
        ]
    )
    noisy = add_noise(blur(img, k=3), sigma=15)
    angle = estimate_skew(to_gray(noisy))
    assert abs(angle) < 5.0


def test_estimate_skew_does_not_explode_on_a_blank_crop():
    import numpy as np

    blank = np.full((200, 400), 255, dtype=np.uint8)
    assert estimate_skew(blank) == 0.0


def test_preprocess_deskews_a_rotated_page():
    img, _ = clean_answer_block(["Deskew target line of text here."])
    rotated = rotate(img, 5.0)
    result = preprocess(rotated)
    # After correction, the residual skew of the *processed* image should be
    # much smaller than the angle it detected and corrected for.
    residual = estimate_skew(result.image)
    assert abs(residual) < abs(result.skew_angle)


def test_preprocess_binary_output_is_two_valued():
    result = preprocess(_gray_page())
    unique = set(result.binary.flatten().tolist())
    assert unique <= {0, 255}
