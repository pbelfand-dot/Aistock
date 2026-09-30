"""Trading "in its head" while studying, and the trade report (the same for in its head, paper and real)."""
import pandas as pd

import run
from aitrader import dashboard, report
from aitrader.brokers.base import Fill
from aitrader.phases import Phase, current_phase
from aitrader.storage import Store
from test_lifecycle import FakeData


def test_each_trade_shows_what_it_spent_what_it_got_back_and_win_or_loss():
    fills = pd.DataFrame([
        {"date": "2026-09-01", "ticker": "AAA", "side": "BUY", "qty": 2, "price": 50.0, "realized_pnl": 0.0, "reason": "momentum score 0.9"},
        {"date": "2026-09-02", "ticker": "AAA", "side": "BUY", "qty": 2, "price": 60.0, "realized_pnl": 0.0, "reason": "momentum score 0.9"},
        {"date": "2026-09-10", "ticker": "AAA", "side": "SELL", "qty": 3, "price": 66.0, "realized_pnl": 33.0, "reason": "exit"},
        {"date": "2026-09-11", "ticker": "AAA", "side": "SELL", "qty": 1, "price": 44.0, "realized_pnl": -11.0, "reason": "stop-loss"},
    ])
    last, first = report.trades(fills, "swing")                      # newest first
    assert (first["spent"], first["got_back"], first["gain"], first["gain_pct"]) == (165.0, 198.0, 33.0, 20.0)
    assert first["result"] == "win" and first["days_held"] == 9 and first["bought_on"] == "2026-09-01"
    assert (last["spent"], last["gain"], last["gain_pct"], last["result"]) == (55.0, -11.0, -20.0, "loss")

    totals = report.totals([last, first], [], 1000.0, 1022.0, benchmark_return_pct=1.5, days=8)
    assert totals["trades_closed"] == 2 and totals["wins"] == 1 and totals["losses"] == 1
    assert totals["win_rate_pct"] == 50.0 and totals["spent_total"] == 220.0 and totals["realized_gain"] == 22.0
    assert totals["return_pct"] == 2.2 and totals["beat_benchmark"] is True
    assert totals["best"]["ticker"] == "AAA" and totals["worst"]["gain_pct"] == -20.0

    days = report.daily(pd.Series([1010.0, 1022.0], index=pd.to_datetime(["2026-09-01", "2026-09-02"])), 1000.0)
    assert days[0] == {"date": "2026-09-02", "value": 1022.0, "change": 12.0, "change_pct": 1.19}
    assert days[1]["change_pct"] == 1.0                                 # the first day vs the starting money


def test_while_studying_both_desks_trade_in_their_head_and_report_it(cfg, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run, "MarketData", FakeData)
    store = Store(tmp_path / "aitrader.sqlite")
    data = FakeData()
    days = FakeData.intraday[1].index.normalize().unique()
    for day in days[:3]:
        for bar_time in FakeData.intraday[1].index[FakeData.intraday[1].index.normalize() == day]:
            now = bar_time.to_pydatetime()
            FakeData.now = now
            run.trade_desk(cfg, store, data, "day", now)
            if (now.hour, now.minute) == (15, 45):
                run.trade_desk(cfg, store, data, "swing", now)
        run.report_days(cfg, store, day.strftime("%Y-%m-%d"))
        assert store.get("study-day_ledger")["positions"] == {}, "in its head, the day desk still never holds overnight"

    assert current_phase(store, "day") == current_phase(store, "swing") == Phase.STUDY     # still studying
    assert len(store.equity_curve("study-day")) == 3 and len(store.equity_curve("study-swing")) == 3
    assert len(store.fills("study-day")) > 0
    assert not len(store.fills("paper-day")) and not len(store.fills("paper-swing"))      # nothing on paper
    journal = " ".join(m for _, m in store.journal(2000))
    assert "[study-day] BUY" in journal and "(spent $" in journal
    assert "[study-day]" in journal and "today" in journal and "since the start" in journal   # the daily line

    run.cmd_status(cfg, store, None)                                    # the Terminal status shows it too

    printed = capsys.readouterr().out
    assert "study-day: $" in printed and "since the start" in printed and ("WIN $" in printed or "LOSS $" in printed)

    snap_account = dashboard._account(cfg, store, "study")
    assert snap_account["active"] and snap_account["daily"] and snap_account["totals"]["days"] == 3
    assert snap_account["totals"]["trades_closed"] == len(snap_account["trades"]) > 0
    t = snap_account["trades"][0]
    assert {"spent", "got_back", "gain", "gain_pct", "result", "bought_on", "sold_on"} <= set(t)


def test_moving_up_to_paper_closes_the_pretend_positions(cfg, tmp_path, monkeypatch):
    from aitrader import scanner
    monkeypatch.setattr(scanner, "trade_candidates", lambda cfg: [])
    store = Store(dashboard.data_path(cfg, "aitrader.sqlite"))
    store.set("study-swing_ledger", {"cash": 400.0, "unsettled": {}, "pending": [], "positions": {
        "AAA": {"ticker": "AAA", "qty": 2, "avg_cost": 50.0, "opened_on": "2026-09-23", "stop_order_id": ""}}})
    monkeypatch.setattr(dashboard, "quote", lambda cfg, t: {"ticker": t, "last": 55.0, "change_pct": None, "trail": []})
    run.start_stage1(cfg, store)
    assert current_phase(store, "swing") == Phase.PAPER
    assert store.get("study-swing_ledger")["positions"] == {}
    sold = store.fills("study-swing").iloc[-1]
    assert sold.side == "SELL" and sold.ticker == "AAA" and "moved on to paper" in sold.reason
    assert store.equity_curve("study-swing").iloc[-1] > 500                # 400 cash + 2 x ~$55


def test_you_can_switch_in_its_head_trading_off(cfg, tmp_path):
    cfg["study"]["in_its_head"] = False
    store = Store(tmp_path / "aitrader.sqlite")
    now = FakeData.intraday[1].index[40].to_pydatetime()
    assert "not trading yet" in run.trade_desk(cfg, store, FakeData(), "day", now)


def test_paper_and_real_money_get_the_same_report(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "_benchmark", lambda cfg, idx, start: None)
    store = Store(dashboard.data_path(cfg, "aitrader.sqlite"))
    for kind in ("paper", "live"):
        store.record_fill(f"{kind}-swing", Fill("2026-09-23", "AAA", "BUY", 2, 50.0, "momentum score 0.95", order_id="1"))
        store.record_fill(f"{kind}-swing", Fill("2026-09-25", "AAA", "SELL", 2, 55.0, "exit", 10.0, "2"))
        store.record_equity(f"{kind}-swing", "2026-09-23", 500.0, 400.0)
        store.record_equity(f"{kind}-swing", "2026-09-25", 510.0, 510.0)
        store.set(f"{kind}-swing_ledger", {"cash": 510.0, "unsettled": {}, "pending": [], "positions": {}})
        a = dashboard._account(cfg, store, kind)
        assert a["trades"][0]["gain"] == 10.0 and a["trades"][0]["gain_pct"] == 10.0 and a["trades"][0]["result"] == "win"
        assert a["totals"]["wins"] == 1 and a["totals"]["spent_total"] == 100.0 and len(a["daily"]) == 2
