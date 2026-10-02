"""Beyond the price: company quality (SEC XBRL frames), insider buys (Form 4) and short interest, and the
momentum_quality challenger that uses them. Nothing here goes online: the SEC and Yahoo are faked."""
import json
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from aitrader import fundamentals, sec_filings, stock_info
from aitrader.storage import Store
from aitrader.strategies import Momentum, MomentumQuality, current_scores, get_strategy
from test_data_sources import Answer, submissions

NOW = datetime(2026, 10, 2, 11, 0)


def form4(code="P", officer=True, director=False, planned=False, ten_pct=False):
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <issuer><issuerCik>0000000111</issuerCik><issuerTradingSymbol>AAA</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>0000999</rptOwnerCik><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>{int(director)}</isDirector><isOfficer>{int(officer)}</isOfficer>
      <isTenPercentOwner>{int(ten_pct)}</isTenPercentOwner>{"<officerTitle>CEO</officerTitle>" if officer else ""}
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>{int(planned)}</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-09-28</value></transactionDate>
      <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>2000</value></transactionShares>
        <transactionPricePerShare><value>25.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_only_unplanned_open_market_buys_by_officers_or_directors_count():
    buys = fundamentals.form4_buys(form4())
    assert buys == [{"date": "2026-09-28", "shares": 2000.0, "price": 25.5, "value": 51000.0, "who": "Doe Jane (CEO)"}]
    assert fundamentals.form4_buys(form4(officer=False, director=True))[0]["who"] == "Doe Jane (director)"
    assert fundamentals.form4_buys(form4(code="S")) == []                     # a sale
    assert fundamentals.form4_buys(form4(code="A")) == []                     # a grant, not a purchase
    assert fundamentals.form4_buys(form4(planned=True)) == []                 # under a 10b5-1 plan
    assert fundamentals.form4_buys(form4(officer=False, ten_pct=True)) == []  # a big holder, not an insider
    assert fundamentals.form4_buys("not xml") == []


def test_quality_is_gross_profits_over_assets_ranked_against_all_companies():
    gross = {"1": ["2023-12-31", 50.0]}
    revenue = [{"2": ["2023-12-31", 100.0]}, {"3": ["2023-06-30", 80.0]}]
    cost = [{"2": ["2023-12-31", 90.0]}, {"3": ["2023-06-30", 40.0]}]
    assets = {"1": ["2023-12-31", 100.0], "2": ["2023-12-31", 100.0], "3": ["2023-12-31", 100.0], "4": ["2023-12-31", 0]}
    year = fundamentals.quality_year(gross, revenue, cost, assets)
    assert year["1"] == ["2023-12-31", 0.5, 1.0] and year["2"][1] == 0.1 and year["3"][:2] == ["2023-06-30", 0.4]
    assert "4" not in year                                                    # no assets: no ratio


@pytest.fixture
def sec(cfg, monkeypatch):
    cfg["secrets"]["sec_email"] = "owner@example.com"
    cfg["desks"]["swing"]["watchlist"] = ["AAA", "BBB"]
    cfg["desks"]["day"]["watchlist"] = []
    urls = []

    def get(url, headers, timeout):
        urls.append(url)
        if url == sec_filings.TICKERS_URL:
            return Answer({"0": {"cik_str": 111, "ticker": "AAA", "title": "A Co"},
                           "1": {"cik_str": 222, "ticker": "BBB", "title": "B Co"}})
        if "/frames/" in url:
            concept, period = url.split("/")[-3], url.split("/")[-1][:-5]
            year = int(period[2:6])
            if concept == "GrossProfit":
                return Answer({"data": [{"cik": 111, "end": f"{year}-12-31", "val": 60},
                                        {"cik": 222, "end": f"{year}-12-31", "val": 5},
                                        *[{"cik": 900 + i, "end": f"{year}-12-31", "val": 7 * i} for i in range(8)]]})
            if concept == "Assets":
                return Answer({"data": [{"cik": c, "end": f"{year}-12-31", "val": 100} for c in [111, 222, *range(900, 908)]]})
            return Answer({"data": []})
        if url.endswith("/form4.xml"):
            return type("R", (), {"status_code": 200, "text": form4()})()
        if "0000000111" in url:
            return Answer(submissions(form=["4", "4"], filingDate=["2026-09-29", "2026-08-01"],
                                      acceptanceDateTime=["2026-09-29T18:00:00.000Z", "2026-08-01T18:00:00.000Z"],
                                      accessionNumber=["0009-26-000001", "0009-26-000002"],
                                      primaryDocument=["xslF345X05/form4.xml", "xslF345X05/old.xml"], items=["", ""]))
        return Answer(submissions(form=[]))
    monkeypatch.setattr(sec_filings, "_get", get)
    monkeypatch.setattr(sec_filings, "MIN_GAP", 0)
    return urls


def test_insider_buys_come_from_the_form_4s_in_the_filings_check(cfg, sec, tmp_path):
    store = Store(tmp_path / "aitrader.sqlite")
    sec_filings.check(cfg, store, NOW)
    raw = [u for u in sec if u.endswith(".xml")]
    assert raw == ["https://www.sec.gov/Archives/edgar/data/111/000926000001/form4.xml"]   # the raw XML; August is too old
    buys = fundamentals.insider_buys(cfg, "AAA")
    assert len(buys) == 1 and buys[0]["filed"] == "2026-09-29" and buys[0]["value"] == 51000.0
    assert any("[sec] insider buy: Doe Jane (CEO) bought $51,000 of AAA" in m for _, m in store.journal(10))
    sec_filings.check(cfg, store, NOW)
    assert len([u for u in sec if u.endswith(".xml")]) == 1                   # each Form 4 is read once
    table = fundamentals.insider_table(cfg, ["AAA", "BBB"], pd.DatetimeIndex(["2026-09-28", "2026-10-02", "2026-11-15"]))
    assert table["AAA"].tolist() == [False, True, False] and not table["BBB"].any()


def test_quality_history_counts_each_year_only_once_its_report_is_out(cfg, sec):
    fundamentals.refresh(cfg, ["AAA", "BBB"], "2026-10-02")
    frames = [u for u in sec if "/frames/" in u]
    assert "https://data.sec.gov/api/xbrl/frames/us-gaap/GrossProfit/USD/CY2017.json" in frames
    assert "https://data.sec.gov/api/xbrl/frames/us-gaap/Assets/USD/CY2025Q4I.json" in frames
    assert not any("CY2026" in u for u in frames)                             # this year isn't over
    index = pd.DatetimeIndex(["2018-03-01", "2018-04-15", "2026-10-01"])
    q = fundamentals.quality_table(cfg, ["AAA", "BBB", "XLF"], index)
    assert np.isnan(q.loc["2018-03-01", "AAA"])                              # 2017's report wasn't out yet
    assert q.loc["2018-04-15", "AAA"] == 1.0 and q.loc["2018-04-15", "BBB"] <= 0.3
    assert q["XLF"].isna().all()                                             # a fund: no opinion
    n = len([u for u in sec if "/frames/" in u])
    fundamentals.refresh(cfg, ["AAA"], "2026-10-03")
    assert len([u for u in sec if "/frames/" in u]) == n                      # once a week, not every day
    text = fundamentals.card(cfg, "BBB")["quality"]["text"]
    assert text.startswith("gross profits 5% of assets (year to 2025-12-31): better than") and "weak" in text


def test_short_interest_is_saved_daily_and_flags_heavily_shorted_stocks(cfg):
    answers = {"AAA": {"days_to_cover": 9.5, "short_pct_float": 12.0, "shares_short": 1e6, "as_of": "2026-09-15"},
               "BBB": {"days_to_cover": 1.2, "short_pct_float": 3.0, "shares_short": 1e5, "as_of": "2026-09-15"},
               "XLF": {"days_to_cover": None, "short_pct_float": None}}
    calls = []
    fetch = lambda t: calls.append(t) or answers[t]
    fundamentals.refresh_short_interest(cfg, list(answers), "2026-10-01", fetch=fetch)
    fundamentals.refresh_short_interest(cfg, list(answers), "2026-10-01", fetch=fetch)
    assert calls.count("AAA") == 1                                            # once a day
    table = fundamentals.short_table(cfg, ["AAA", "BBB", "XLF"], pd.DatetimeIndex(["2026-09-30", "2026-10-02"]))
    assert table["AAA"].tolist() == [False, True] and not table["BBB"].any() and not table["XLF"].any()
    card = fundamentals.card(cfg, "AAA")["short"]
    assert card["heavy"] and card["text"] == "12.0% of the float sold short, 9.5 days to cover (as of 2026-09-15): heavily shorted"


def trend(start, end, days=400, seed=0):
    rng = np.random.default_rng(seed)
    close = np.geomspace(start, end, days) * (1 + rng.normal(0, 0.002, days))
    idx = pd.bdate_range(end="2026-10-02", periods=days)
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1e6}, index=idx)


def test_momentum_quality_skips_weak_and_shorted_stocks_and_boosts_insider_buys(cfg, sec):
    bars = {"AAA": trend(20, 60), "BBB": trend(20, 58, seed=1), "CCC": trend(20, 50, seed=2),
            "DDD": trend(20, 40, seed=3), "EEE": trend(20, 30, seed=4)}
    market = trend(100, 130, seed=9)
    plain = current_scores(Momentum(), bars, market)
    assert current_scores(MomentumQuality(), bars, market).equals(plain)     # no facts: exactly momentum
    fundamentals.refresh(cfg, list(bars), "2026-10-02")                        # BBB: weak quality
    fundamentals.refresh_short_interest(cfg, ["AAA"], "2026-10-02",
                                        fetch=lambda t: {"days_to_cover": 12.0, "short_pct_float": 30.0})
    q = current_scores(get_strategy("momentum_quality", cfg, "swing"), bars, market)
    assert plain["AAA"] >= Momentum.buy_above and q["AAA"] < Momentum.buy_above   # heavily shorted: not bought
    assert plain["BBB"] >= Momentum.buy_above and q["BBB"] < Momentum.buy_above   # weak quality: not bought
    assert q["BBB"] >= Momentum.sell_below                                    # ...but never forced out
    fundamentals._save(cfg, fundamentals.INSIDER_FILE, {"seen": {}, "buys": [
        {"ticker": "CCC", "filed": "2026-09-30", "date": "2026-09-28", "value": 5e4, "who": "X (CFO)", "url": ""}]})
    q = current_scores(get_strategy("momentum_quality", cfg, "swing"), bars, market)
    assert q["CCC"] == pytest.approx(min(1.0, plain["CCC"] + 0.1))           # an insider just bought


def test_the_stock_card_shows_the_facts_beyond_the_price(cfg, sec, tmp_path):
    store = Store(tmp_path / "aitrader.sqlite")
    sec_filings.check(cfg, store, NOW)
    fundamentals.refresh(cfg, ["AAA"], "2026-10-02")
    beyond = stock_info._beyond_price(cfg, "AAA")
    assert beyond["quality"]["pct"] == 1.0 and beyond["insider_buys"][0]["text"].startswith("Doe Jane (CEO) bought $51,000")
    assert stock_info._beyond_price(cfg, "ZZZ") == {}


def test_the_team_notes_the_facts_and_the_mistake_memory_tags_them(cfg, sec):
    from aitrader.agents import analyst, risk
    from aitrader.brokers import Order
    fundamentals.refresh(cfg, ["AAA", "BBB"], "2026-10-02")
    fundamentals.refresh_short_interest(cfg, ["BBB"], "2026-10-02",
                                        fetch=lambda t: {"days_to_cover": 10.0, "short_pct_float": 5.0})
    facts = fundamentals.tags(cfg, ["AAA", "BBB", "XLF"], "2026-10-02")
    assert facts == {"AAA": ["high quality (top 30% by gross profits)"],
                     "BBB": ["weak quality (bottom 30% by gross profits)", "heavily shorted"]}
    views = analyst({"top": [("BBB", 0.9)], "danger": [], "options_gaps": {}, "holding": [], "beyond": facts},
                    Momentum())
    assert views == ["BBB 0.90: strong; weak quality (bottom 30% by gross profits); heavily shorted"]
    tags = {}
    risk([Order("BBB", "BUY", 1, 20.0, "test")], {}, {}, {}, 1000.0,
         {"correlation_bars": 60, "correlation_limit": 0.8, "risk_vetoes": []}, tags_out=tags, facts_by_ticker=facts)
    assert "heavily shorted" in tags["BBB"] and "weak quality (bottom 30% by gross profits)" in tags["BBB"]
