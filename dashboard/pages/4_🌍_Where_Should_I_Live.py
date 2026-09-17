"""Where Should I Live? — MVP prototype page.

Reads no warehouse tables: the MVP runs off a curated seed plus one model file,
so it works before any ingestion exists (docs/liveability-mvp.md).

Run inside the dashboard container, where the sci stack is installed.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import liveability as M  # dashboard/liveability.py — same dir, on sys.path

st.set_page_config(page_title="Where Should I Live?", layout="wide")
st.title("Where should I live?")
st.caption(
    "Compares **staying where you are** against moving to one other country, and finds the "
    "**year** that maximises your net worth at the end of the horizon. Illustrative model "
    "output, not advice."
)

COUNTRIES, _BASE = M._defaults()
NAMES = {iso: c.name for iso, c in sorted(COUNTRIES.items(), key=lambda kv: kv[1].name)}

# ----------------------------------------------------------------- inputs
with st.sidebar:
    st.header("1 · About you")
    age = st.number_input("Your age", 25, 70, 35,
                          help="Sets how long money can compound.")
    home_iso = st.selectbox(
        "Country you live in now", list(NAMES), index=list(NAMES).index("DEU"),
        format_func=lambda i: NAMES[i],
        help="Everything is measured as 'vs staying here'.",
    )

    st.header("2 · Your money (per year)")
    gross = st.number_input("Gross salary (€)", 30_000, 600_000, 120_000, step=5_000,
                            help="Before income tax and social contributions.")
    spend = st.number_input("What you spend (€)", 12_000, 300_000, 55_000, step=1_000,
                            help="Everything you consume in a year, excluding savings and "
                                 "investment. Rises automatically in expensive countries.")
    net_worth = st.number_input("Invested savings today (€)", 0, 10_000_000, 500_000,
                                step=25_000,
                                help="Money that can compound — not your home or pension.")

    st.header("3 · Your situation")
    children = st.slider("Children", 0, 3, 0,
                         help="Childcare is the single most country-sensitive cost. Public "
                              "childcare in Germany is cheap; in Switzerland it is roughly "
                              "40% of a salary.")
    capital_mobile = st.slider(
        "How much of your invested savings could you actually move?", 0.0, 1.0, 1.0, 0.05,
        help="Tax on investment returns follows where **you** live — but only if the money "
             "can move. A pension, a company stake you cannot sell, or an account you will "
             "not restructure keeps earning at your **current** country's tax rate. "
             "100% = purely stocks/funds you could relocate. 0% = locked in place, so "
             "moving country would not change your investment tax at all.",
    )
    needs_job = st.checkbox("I would need to find a local job", True,
                            help="If ticked, the destination's salary level applies. If you "
                                 "work remotely for a foreign employer, untick it — your "
                                 "salary then stays the same wherever you live.")
    horizon = st.slider("Years to plan over", 5, 40, 25,
                        help="How far ahead to project, e.g. to retirement.")

    st.header("4 · The one thing to research")
    others = [i for i in NAMES if i != home_iso]
    focus_iso = st.selectbox("Country you are curious about", others,
                             index=others.index("CHE") if "CHE" in others else 0,
                             format_func=lambda i: NAMES[i])
    focus_wage = st.slider(
        "Your salary there, relative to now", 0.6, 2.2,
        float(_BASE.wage_index.get(focus_iso, 1.0)), 0.05,
        help="This is the model's weakest input and its biggest lever. 1.00 = you would earn "
             "exactly the same gross salary. 1.50 = 50% more. Check it against a real job "
             "advert — it changes the answer more than any tax rate.",
    )

home = COUNTRIES[home_iso]
profile = M.Profile(
    age=int(age), home=home_iso, gross_income=float(gross), net_worth=float(net_worth),
    annual_spend=float(spend), capital_mobile=float(capital_mobile), children=int(children),
    horizon=int(horizon), needs_local_job=bool(needs_job),
    inflation=_BASE.inflation,
    wage_index={**_BASE.wage_index, focus_iso: float(focus_wage)},
)

# ----------------------------------------------------------------- affordability guard
net_now = gross * (1 - home.wedge_mid)
spend_now = spend * home.price_level
save_now = net_now - spend_now

st.subheader("Does the arithmetic even work?")
a1, a2, a3 = st.columns(3)
a1.metric("Take-home in " + home.name, f"€{net_now:,.0f}",
          help="Gross salary minus income tax and social contributions.")
a2.metric("Your spending there", f"€{spend_now:,.0f}",
          help="Spending is scaled by the local price level (1.00 = " + home.name + ").")
a3.metric("Left to invest each year", f"€{save_now:,.0f}")

if save_now <= 0:
    st.error(
        f"**You would be spending more than you earn.** With €{net_now:,.0f} take-home and "
        f"€{spend_now:,.0f} of spending, nothing is left to invest — so your savings would be "
        f"*drawn down* every year and the projection will go negative. That is arithmetically "
        f"correct, not a bug. Lower your spending, raise the salary, or accept that this plan "
        f"means living off capital."
    )

# ----------------------------------------------------------------- results
baseline = M.terminal_wealth(home, profile, profile.horizon, home)
end_age = profile.age + profile.horizon

rows = []
for iso, c in COUNTRIES.items():
    if iso == home_iso:
        continue
    s, w = M.best_switch(c, profile, home)
    moving_wins = s < profile.horizon
    rows.append({
        "Country": c.name,
        "ISO": iso,
        # Only show a destination outcome when moving there actually beats staying.
        "W at horizon": w if moving_wins else baseline,
        "Gain vs staying": (w - baseline) if moving_wins else 0.0,
        "Schedule": f"age {profile.age + s}" if moving_wins else "not worth it",
        "Price level ×": c.price_level,
        "Child cost %": c.child_cost_pct * 100,
        "Confidence": c.confidence,
    })
res = pd.DataFrame(rows).sort_values("Gain vs staying", ascending=False).reset_index(drop=True)

st.subheader("Where these places are")
import json as _json
from pathlib import Path as _Path


@st.cache_data(show_spinner=False)
def _load_geo() -> dict:
    """Filtered, simplified 19-country geometry (~140 KB, 8.9k vertices).

    Source: datasets/geo-countries (Natural Earth derived), filtered to this
    universe, ISO3-normalised (the source ships "-99" for France and Norway),
    and Douglas-Peucker simplified at epsilon=0.05 deg — 15% of the original
    vertices, which is what keeps the browser responsive.
    """
    p = _Path(__file__).resolve().parent.parent / "europe19.geojson"
    return _json.loads(p.read_text())


_map = M.map_points(COUNTRIES, profile)   # model-side, so the data path is tested

figm = go.Figure(go.Choropleth(
    geojson=_load_geo(),
    featureidkey="properties.iso3",
    locations=_map["locations"],
    z=_map["z"],
    customdata=_map["customdata"],
    text=_map["text"],
    # Grey = not worth moving to; a green ramp scaled to the best gain.
    colorscale=[
        [0.0, "#bdbdbd"], [0.02, "#bdbdbd"],
        [0.03, "#c8e6c9"], [0.35, "#66bb6a"], [1.0, "#1b5e20"],
    ],
    zmin=0.0, zmax=_map["top_gain"],
    marker_line_width=0.6, marker_line_color="white",
    colorbar=dict(
        title=dict(text="Gain vs<br>staying put", side="right"),
        tickprefix="€", ticksuffix="", thickness=12, len=0.65, x=1.0,
    ),
    hovertemplate="%{customdata}<extra></extra>",
))
# The home country: outline plus a star, so "you are here" is unmistakable.
figm.add_trace(go.Choropleth(
    geojson=_load_geo(), featureidkey="properties.iso3",
    locations=[_map["home"]["iso3"]], z=[0],
    colorscale=[[0, "rgba(21,101,192,0.35)"], [1, "rgba(21,101,192,0.35)"]],
    showscale=False, marker_line_width=2.2, marker_line_color="#1565c0",
    hovertext=f"<b>{_map['home']['name']} — you are here</b><br>"
              f"your baseline: €{baseline:,.0f} at age {end_age}",
    hoverinfo="text",
))
figm.add_trace(go.Scattergeo(
    lon=[_map["home"]["longitude"]], lat=[_map["home"]["latitude"]],
    mode="markers+text", text=[f"  {_map['home']['name']} (you)"],
    textposition="middle right", hoverinfo="skip", showlegend=False,
    marker=dict(size=14, color="#1565c0", symbol="star",
                line=dict(width=1, color="white")),
))
figm.update_geos(
    scope="europe",
    # Mercator = flat, square-on 2D look. "natural earth" is a globe-like
    # projection that reads as skewed/3D in a small panel.
    projection_type="mercator",
    showland=True, landcolor="#fafafa",
    showocean=True, oceancolor="#eaf3fb",
    # Coastlines/country borders are separate geometry traces and cost render
    # time; the choropleth outlines already delineate every country here.
    showcoastlines=False, showcountries=False, showframe=False,
    lataxis_range=[34, 68], lonaxis_range=[-26, 30],
)
figm.update_layout(
    height=560, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
    # Static after load: no drag-zoom recompute, no phantom modebar entries.
    dragmode=False,
)
st.plotly_chart(figm, use_container_width=True)
st.caption(
    "**Green** = moving there beats staying, shaded by the size of the gain. "
    "**Grey** = no move beats staying. **Hover any country** for its full breakdown: net worth, "
    "gain, best age to move, tax wedge, cost of living, child cost and data confidence."
)

st.subheader("What the model says")
b1, b2, b3 = st.columns(3)
top = res.iloc[0]
b1.metric(f"Stay in {home.name}", f"€{baseline:,.0f}", help=f"Net worth at age {end_age}")
if top["Gain vs staying"] > 0:
    b2.metric(f"Best: {top['Country']}", f"€{top['W at horizon']:,.0f}",
              delta=f"€{top['Gain vs staying']:+,.0f}",
              help="Net worth at the same age if you move at the best time.")
    b3.metric("When to move", top["Schedule"])
else:
    b2.metric("Best alternative", "no move beats staying")
    b3.metric("Verdict", "stay put")

st.caption(
    f"**Net worth at age {end_age}**, in today's euros, after tax on investment returns and "
    f"adjusted for local prices. 'Not worth it' means moving never beat staying at any year."
)

st.dataframe(
    res[["Country", "W at horizon", "Gain vs staying", "Schedule", "Price level ×",
         "Child cost %", "Confidence"]],
    use_container_width=True, hide_index=True,
    column_config={
        "W at horizon": st.column_config.NumberColumn(
            "Net worth at horizon", format="€%.0f",
            help=f"Net worth at age {end_age} if you move at the best time — or your "
                 f"{home.name} outcome when moving is not worth it."),
        "Gain vs staying": st.column_config.NumberColumn(
            "Gain vs staying put", format="€%+.0f",
            help="€0 means no move at any year beat staying."),
        "Schedule": st.column_config.TextColumn(
            "When to move", help="The year that maximises the gain."),
        "Price level ×": st.column_config.NumberColumn(
            "Cost of living", format="%.2f×",
            help=f"Local prices vs {home.name}. 1.62× = 62% more expensive."),
        "Child cost %": st.column_config.NumberColumn(
            "Cost of 1 child", format="%.0f%%",
            help="Annual cost of one child as a share of gross salary: childcare, schooling, "
                 "extra housing and upkeep, net of subsidies."),
        "Confidence": st.column_config.TextColumn(
            "Data confidence", help="How well evidenced this country's tax and cost inputs are."),
    },
)

_zero = res[res["Gain vs staying"] <= 0]
if len(_zero) == len(res):
    st.info(
        f"**No country beats staying in {home.name} on these inputs.** That is a common and "
        "legitimate result: the model only recommends a move when the destination's lower "
        "taxes and prices outweigh its salary level. Try lowering your spending, or check "
        "the 'salary there' slider for a country you are serious about."
    )

st.subheader("Why most countries show €0")
st.caption(
    "Before any compounding, a move has to improve your **annual cash flow**: "
    "`(tax saved) − (extra cost of living)`, then adjusted for what you would earn there. "
    "Only if that is positive can compounding make it grow."
)

_why = []
for _, r in res.iterrows():
    cc = COUNTRIES[r["ISO"]]
    cash = (gross * (home.wedge_mid - cc.wedge_mid)
            - spend * (cc.price_level - home.price_level))
    wage = profile.wage_index.get(r["ISO"], 1.0) if needs_job else 1.0
    _why.append({
        "Country": r["Country"],
        "Tax saved per year": gross * (home.wedge_mid - cc.wedge_mid),
        "Extra living cost per year": -spend * (cc.price_level - home.price_level),
        "Net cash flow": cash,
        "Salary there ÷ now": wage,
        "Cash flow at their salary": (
            gross * wage * (1 - cc.wedge_mid) - spend * cc.price_level
        ) - (gross * (1 - home.wedge_mid) - spend * home.price_level),
        "Verdict": "worth moving" if r["Gain vs staying"] > 0 else "not worth it",
    })
why = pd.DataFrame(_why).sort_values("Cash flow at their salary", ascending=False)
st.dataframe(
    why, use_container_width=True, hide_index=True,
    column_config={
        "Tax saved per year": st.column_config.NumberColumn(format="€%+.0f",
            help="Lower income tax and social contributions on the same gross salary."),
        "Extra living cost per year": st.column_config.NumberColumn(format="€%+.0f",
            help="Negative means the country is more expensive for your spending pattern."),
        "Net cash flow": st.column_config.NumberColumn(format="€%+.0f",
            help="Ignoring what you would earn there. Positive or negative."),
        "Salary there ÷ now": st.column_config.NumberColumn(format="%.2f×",
            help="From the curated profile; override it in the sidebar for a country you care about."),
        "Cash flow at their salary": st.column_config.NumberColumn(format="€%+.0f",
            help="The decisive number. Negative means you would save less every year, "
                 "so no amount of compounding rescues it."),
    },
)
st.caption(
    "**This is the finding, not a bug.** Cheap, low-tax countries (Spain, Portugal, Poland) "
    "show a strongly positive raw cash flow — and it is wiped out entirely by their lower "
    "salaries. Expensive countries (Switzerland, Luxembourg, Norway) show a negative raw "
    "cash flow and are rescued by high salaries. **Only the salary line decides**, which is "
    "why it is the one number worth researching properly."
)

st.subheader("The schedule matters more than the destination")
top3 = res[res["Gain vs staying"] > 0].head(3)
years = list(range(profile.horizon + 1))
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=[profile.age + y for y in years], y=[baseline] * len(years),
    name=f"Stay in {home.name}", line=dict(dash="dash", color="#888"),
))
for _, r in top3.iterrows():
    cc = COUNTRIES[r["ISO"]]
    ws = [M.terminal_wealth(cc, profile, y, home) for y in years]
    fig.add_trace(go.Scatter(
        x=[profile.age + y for y in years], y=ws, name=f"→ {cc.name}",
        mode="lines+markers", marker=dict(size=5),
    ))
fig.update_layout(
    xaxis_title="Age at which you move",
    yaxis_title=f"Net worth at age {end_age} (today's €)",
    hovermode="x unified", height=420, margin=dict(l=10, r=10, t=30, b=10),
)
st.plotly_chart(fig, use_container_width=True)
if top3.empty:
    st.info("No destination beats staying, so there is no schedule to plot.")
else:
    st.caption(
        "Each curve is 'move at this age'. The highest point is the best age to move. "
        "A flat curve means timing does not matter; a falling curve means move sooner."
    )

st.subheader("What would flip the answer")
sens = []
for ratio in [round(x * 0.1, 1) for x in range(6, 23)]:
    pr = M.Profile(**{**profile.__dict__,
                      "wage_index": {**profile.wage_index, focus_iso: ratio}})
    b = M.terminal_wealth(home, pr, pr.horizon, home)
    _, w = M.best_switch(COUNTRIES[focus_iso], pr, home)
    sens.append({"ratio": ratio, "gain": w - b})
sdf = pd.DataFrame(sens)
fig2 = go.Figure(go.Bar(
    x=sdf["ratio"], y=sdf["gain"],
    marker_color=["#2e7d32" if v > 0 else "#c62828" for v in sdf["gain"]],
))
fig2.update_layout(
    xaxis_title=f"Your salary in {NAMES[focus_iso]} ÷ your salary now",
    yaxis_title=f"Gain vs staying in {home.name} (today's €)",
    height=320, margin=dict(l=10, r=10, t=30, b=10),
)
st.plotly_chart(fig2, use_container_width=True)
pos = sdf[sdf["gain"] > 0]
if pos.empty:
    st.warning(
        f"On these inputs **staying in {home.name} beats {NAMES[focus_iso]} at every salary "
        f"level.** Try lowering your spending, or check the child count."
    )
else:
    st.caption(
        f"**Break-even salary ratio: {pos['ratio'].min():.2f}×.** Below that, staying in "
        f"{home.name} wins. Above it, {NAMES[focus_iso]} wins. This is the number worth "
        f"researching about yourself."
    )

st.divider()
st.caption(
    f"Model `dashboard/liveability.py` (canonical `scripts/liveability_model.py`) · "
    f"{len(COUNTRIES)} OECD-core countries · base case, no uncertainty bands yet. "
    "Not modelled: policy changes, market crashes, currency moves, or how much you like "
    "the place."
)
