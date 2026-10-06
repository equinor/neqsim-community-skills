import numpy as np
import pandas as pd

from reservoir_history_match.prep import deliverability_history, field_cgr_observations, monthly_rates, shut_in_pressure_observations


def _wells():
    days = pd.date_range("2010-01-01", "2013-12-31", freq="D")
    rows = []
    for wb, tank, base in (("A-1", "Main", 450.0), ("A-2", "Main", 430.0), ("A-3 T2", "Main", 700.0)):
        for i, d in enumerate(days):
            on = 24 if i % 40 else 0
            rows.append(dict(date=d, well=wb.split()[0], wellbore=wb, tank=tank, gas_sm3=on / 24 * 1e6, on_stream_hrs=on, dh_press=base - 0.1 * i if not on else 200.0,
                             whp_barg=30.0))
    return pd.DataFrame(rows)


def test_monthly_rates_and_cgr():
    w = _wells()
    r = monthly_rates(w)
    assert set(r.columns) == {"A-1", "A-2", "A-3"} and (r > 0).all().all()
    g = pd.Series(1e6, index=pd.date_range("2010-01-01", "2013-12-31"))
    c = g * 2e-4
    o = field_cgr_observations(g, c, r.index)
    assert np.allclose(o.value, 200.0) and (o.kind == "cgr").all()


def test_shut_in_observations_use_old_wellbores_and_lower_quartile():
    w = _wells()
    o = shut_in_pressure_observations(w, quantile=0.25, min_days=1)
    assert (o.date > pd.Timestamp("2011-06-01")).all()  # nothing within the first 18 months of a wellbore
    ex = shut_in_pressure_observations(w, exclude={"Main": "A-3"}, min_days=1)
    assert ex.value.max() < o.value.max() + 1e-9  # excluding the high wellbore cannot raise the statistic


def test_deliverability_history_units():
    d = deliverability_history(_wells())
    assert d.q_ksm3d.iloc[0] == 1000.0 and abs(d.whp.iloc[0] - 31.01325) < 1e-9

