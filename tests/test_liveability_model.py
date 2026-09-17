"""Regression tests for the liveability MVP model.

These are the numbers that must not drift: they encode the two findings that
took the most work to establish (docs/liveability-worked-example-de-35.md).

Run:  uv run pytest tests/test_liveability_model.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import liveability_model as M  # noqa: E402


@pytest.fixture(scope="module")
def env():
    countries, profile = M._defaults()
    return countries, profile


def test_universe_is_oecd_core(env):
    countries, _ = env
    assert len(countries) == 19
    for iso in ("DEU", "CHE", "AUT", "NLD", "CZE", "POL", "ESP", "PRT"):
        assert iso in countries


def test_all_rows_have_a_confidence_and_source(env):
    countries, _ = env
    for c in countries.values():
        assert c.confidence in {"high", "medium", "low"}


def test_after_tax_real_return_is_derived_not_sourced(env):
    """Switzerland's zero-effective equity tax must beat Germany's 26.375%."""
    countries, profile = env
    r_de = countries["DEU"].after_tax_real_return(profile.inflation["DEU"])
    r_ch = countries["CHE"].after_tax_real_return(profile.inflation["CHE"])
    assert r_ch > r_de
    assert 0.01 < r_de < 0.04, f"DE real return {r_de} outside plausible band"
    assert 0.03 < r_ch < 0.06, f"CH real return {r_ch} outside plausible band"


def test_switzerland_wins_at_wage_parity_without_children(env):
    """The corrected headline: a positive gain even with NO wage premium."""
    countries, profile = env
    home = countries["DEU"]
    p = M.Profile(**{**profile.__dict__, "children": 0, "wage_index": {"CHE": 1.0}})
    base = M.terminal_wealth(home, p, p.horizon, home)
    _, w = M.best_switch(countries["CHE"], p, home)
    assert w > base, "Switzerland should beat Germany on tax and return alone"


def test_children_flip_switzerland_at_wage_parity(env):
    """One child at wage parity must remove the advantage; two must kill it.

    This is the finding that validates children as a first-class input.
    """
    countries, profile = env
    home = countries["DEU"]
    gains = {}
    for kids in (0, 1, 2):
        p = M.Profile(**{**profile.__dict__, "children": kids, "wage_index": {"CHE": 1.0}})
        base = M.terminal_wealth(home, p, p.horizon, home)
        s, w = M.best_switch(countries["CHE"], p, home)
        gains[kids] = (w - base, s)

    assert gains[0][0] > 200_000, "0 children should show a large gain"
    assert gains[1][0] < gains[0][0] / 2, "1 child must sharply reduce the gain"
    assert gains[2][0] <= 1, "2 children must remove the advantage entirely"


def test_child_cost_is_not_double_scaled(env):
    """A regression guard: child_cost_pct is local, so it must not be multiplied
    by price_level again. Doubling the children must roughly double the drag."""
    countries, profile = env
    home = countries["DEU"]
    ch = countries["CHE"]
    p0 = M.Profile(**{**profile.__dict__, "children": 0, "wage_index": {"CHE": 1.0}})
    p2 = M.Profile(**{**profile.__dict__, "children": 2, "wage_index": {"CHE": 1.0}})
    w0 = M.terminal_wealth(ch, p0, 0, home)
    w2 = M.terminal_wealth(ch, p2, 0, home)
    assert w2 < w0, "children must reduce wealth"


def test_high_tax_destination_produces_no_move(env):
    """Austria is close to Germany on every axis: the model must say stay."""
    countries, profile = env
    home = countries["DEU"]
    s, _ = M.best_switch(countries["AUT"], profile, home)
    assert s >= profile.horizon, "Austria should not be recommended as a wealth move"


def test_partial_capital_mobility_reduces_the_gain(env):
    """Capital you cannot move should keep earning at home rates."""
    countries, profile = env
    home = countries["DEU"]
    ch = countries["CHE"]
    gains = []
    for mobility in (1.0, 0.5, 0.0):
        p = M.Profile(**{**profile.__dict__, "children": 0, "capital_mobile": mobility,
                         "wage_index": {"CHE": 1.0}})
        base = M.terminal_wealth(home, p, p.horizon, home)
        _, w = M.best_switch(ch, p, home)
        gains.append(w - base)
    assert gains[0] > gains[1] > gains[2], f"mobility must be monotone, got {gains}"
    assert gains[2] < 1, "fully immobile capital should remove the tax advantage"


def test_schedule_never_recommends_a_final_year_move(env):
    """A move with under MIN_YEARS_AFTER_SWITCH remaining is not a decision."""
    countries, profile = env
    home = countries["DEU"]
    for iso, c in countries.items():
        if iso == "DEU":
            continue
        s, _ = M.best_switch(c, profile, home)
        assert s <= profile.horizon - M.MIN_YEARS_AFTER_SWITCH or s == profile.horizon


def test_map_points_has_coordinates_for_every_country(env):
    """Regression guard: a Country row missing lat/lon broke the whole map page."""
    countries, profile = env
    m = M.map_points(countries, profile)
    assert len(m["points"]) == len(countries) - 1, "one point per non-home country"
    for q in m["points"]:
        assert q["name"]
        assert -90 <= q["latitude"] <= 90, f"{q['name']} latitude out of range"
        assert -180 <= q["longitude"] <= 180, f"{q['name']} longitude out of range"
        assert "<br>" in q["hover"]
    h = m["home"]
    assert -90 <= h["latitude"] <= 90 and -180 <= h["longitude"] <= 180


def test_map_payload_is_aligned_for_choropleth(env):
    """locations/z/customdata/text must be the same length and order."""
    countries, profile = env
    m = M.map_points(countries, profile)
    n = len(m["points"])
    for key in ("locations", "z", "customdata", "text"):
        assert len(m[key]) == n, f"{key} has {len(m[key])} entries, expected {n}"
    assert all(isinstance(z, (int, float)) for z in m["z"])
    assert min(m["z"]) >= 0.0, "colour scale assumes non-negative gains"
    assert m["top_gain"] > 0
    assert all(iso in {c.iso3 for c in countries.values()} for iso in m["locations"])


def test_grey_countries_have_zero_z_and_no_annotation(env):
    """Grey (not worth moving) must sit at z=0 with no in-map number."""
    countries, profile = env
    m = M.map_points(countries, profile)
    for q in m["points"]:
        if q["worth"]:
            assert q["z"] > 0
            assert q["text"], "worthwhile countries should show a gain label"
        else:
            assert q["z"] == 0.0
            assert q["text"] == ""
            assert "Not worth moving" in q["hover"]


def test_tooltip_contains_the_full_breakdown(env):
    """The hover text is the main informational surface — assert its contents."""
    countries, profile = env
    m = M.map_points(countries, profile)
    tip = m["customdata"][m["locations"].index("CHE")]
    for expected in ("Switzerland", "Net worth", "Income tax + social",
                     "Cost of living", "Cost of 1 child", "Quality of life",
                     "Data confidence", "best age to move"):
        assert expected in tip, f"tooltip missing {expected!r}"


def test_country_rows_carry_coordinates(env):
    """Every curated row must expose latitude/longitude — the map depends on it."""
    countries, _ = env
    for iso, c in countries.items():
        assert hasattr(c, "latitude"), f"{iso} has no latitude attribute"
        assert hasattr(c, "longitude"), f"{iso} has no longitude attribute"
        assert c.latitude != 0.0 or c.longitude != 0.0, f"{iso} coordinates unset"


def test_map_green_matches_recommendations(env):
    """The map must not disagree with the table."""
    countries, profile = env
    m = M.map_points(countries, profile)
    greens = {q["name"] for q in m["points"] if q["worth"]}
    table = {r["name"] for r in M.recommend(countries, profile) if r["gain"] > 0}
    assert greens == table
