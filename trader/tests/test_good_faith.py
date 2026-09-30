"""Good faith violations: in a cash account (like Schwab) the bot only ever spends SETTLED money.

A good faith violation = buying with money that hasn't settled yet, then selling that stock before it
settles. Three in 12 months and Schwab restricts the account for 90 days. These tests prove the bot
can't cause one: it never buys with unsettled money, it waits out bank holidays, and if a position
was ever bought with unsettled money anyway, only your typed emergency stop may sell it early.
"""
import random
from datetime import date, timedelta

from aitrader.brokers import Ledger, PaperBroker
from aitrader.brokers.base import Fill, Order
from aitrader.config import is_cash_account
from aitrader.settlement import bank_holidays, is_settlement_day, market_holidays, settles_on


def test_money_settles_one_business_day_later_and_bank_holidays_dont_count():
    assert settles_on("2026-09-29") == "2026-09-30"          # Tuesday -> Wednesday
    assert settles_on("2026-09-25") == "2026-09-28"          # Friday -> Monday
    assert settles_on("2026-10-09") == "2026-10-13"          # Columbus Day: stocks trade, banks closed
    assert settles_on("2026-11-10") == "2026-11-12"          # Veterans Day, same
    assert settles_on("2026-04-02") == "2026-04-06"          # Good Friday: the market is closed
    assert settles_on("2026-07-02") == "2026-07-06"          # July 4th is a Saturday: closed Friday the 3rd
    assert settles_on("2025-12-31") == "2026-01-02"
    # The NYSE's published 2026 holidays, and the Federal Reserve's.
    assert sorted(d.isoformat() for d in market_holidays(2026)) == [
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
        "2026-09-07", "2026-11-26", "2026-12-25"]
    assert {"2026-10-12", "2026-11-11"} <= {d.isoformat() for d in bank_holidays(2026)}


def cash_broker(cash=50.0, slippage=0.0):
    return PaperBroker(Ledger(cash), slippage_pct=slippage, cash_account=True)


def test_money_from_a_sale_isnt_spent_until_it_settles():
    b = cash_broker(50)
    assert b.submit(Order("AAA", "BUY", 5, 10.0, "buy"), "2026-10-09 10:00")          # settled $50
    assert b.submit(Order("AAA", "SELL", 5, 10.0, "sell"), "2026-10-09 11:00")        # fine: paid with settled money
    assert b.buying_power("2026-10-09") == 0                                         # that $50 isn't settled yet
    assert b.submit(Order("BBB", "BUY", 5, 10.0, "buy"), "2026-10-09 12:00") is None
    assert b.buying_power("2026-10-12") == 0                                         # Columbus Day: still not
    assert b.buying_power("2026-10-13") == 50                                        # settled
    assert b.submit(Order("BBB", "BUY", 5, 10.0, "buy"), "2026-10-13 10:00")


def test_months_of_random_trading_never_buy_with_unsettled_money():
    rng = random.Random(7)
    b = cash_broker(1000, slippage=0.05)
    day = date(2026, 1, 2)
    for _ in range(250):                                   # about a year of trading days
        while not (day.weekday() < 5 and day not in market_holidays(day.year)):
            day += timedelta(days=1)
        today = day.isoformat()
        for ticker in rng.sample(["AAA", "BBB", "CCC", "DDD"], 2):
            price = rng.uniform(5, 50)
            if ticker in b.positions() and rng.random() < 0.6:
                b.submit(Order(ticker, "SELL", b.positions()[ticker].qty, price, "sell", urgent=rng.random() < .3),
                         f"{today} 15:50")
            else:
                b.submit(Order(ticker, "BUY", 1000, price, "buy"), f"{today} 10:00")
        assert all(not p.funds_settle_on for p in b.positions().values()), today
        assert b.ledger.cash >= -1e-9
        day += timedelta(days=1)
    assert b.ledger.gfv_events == []


def test_a_position_bought_with_unsettled_money_waits_and_only_the_emergency_stop_overrides():
    notes = []
    b = cash_broker(0)
    b.note = notes.append
    b.ledger.cash, b.ledger.unsettled = 100.0, {"2026-10-01": 100.0}        # all of it still unsettled on Sep 30
    b._book(Fill("2026-09-30", "AAA", "BUY", 10, 10.0, "filled at the broker before the bot knew"))
    assert b.positions()["AAA"].funds_settle_on == "2026-10-01"

    assert b.submit(Order("AAA", "SELL", 10, 9.0, "stop-loss", urgent=True), "2026-09-30 11:00") is None
    assert "good faith violation" in notes[-1] and "AAA" in b.positions()      # held, not sold

    fill = b.submit(Order("AAA", "SELL", 10, 9.0, "EMERGENCY STOP", urgent=True, emergency=True), "2026-09-30 11:05")
    assert fill and "AAA" not in b.positions()
    assert b.ledger.gfv_count("2026-09-30") == 1 and "GOOD FAITH VIOLATION" in notes[-1]


def test_once_the_money_has_settled_the_sale_goes_ahead():
    b = cash_broker(0)
    b.ledger.cash, b.ledger.unsettled = 100.0, {"2026-10-01": 100.0}
    b._book(Fill("2026-09-30", "AAA", "BUY", 10, 10.0, "test"))
    assert b.submit(Order("AAA", "SELL", 10, 11.0, "take profit"), "2026-10-01 10:00")
    assert b.ledger.gfv_events == []


def test_margin_accounts_like_alpaca_can_reuse_sale_money_right_away():
    b = PaperBroker(Ledger(50), slippage_pct=0, cash_account=False)
    assert b.submit(Order("AAA", "BUY", 5, 10.0, "buy"), "2026-10-09 10:00")
    assert b.submit(Order("AAA", "SELL", 5, 10.0, "sell"), "2026-10-09 11:00")
    assert b.submit(Order("BBB", "BUY", 5, 10.0, "buy"), "2026-10-09 12:00")


def test_ledgers_saved_by_older_versions_are_read_safely():
    ledger = Ledger.from_dict({"cash": 100, "unsettled": {"2026-10-09": 100}, "positions": {}})   # by SALE date
    assert ledger.unsettled == {"2026-10-13": 100}
    assert ledger.buying_power("2026-10-12", True) == 0 and ledger.buying_power("2026-10-13", True) == 100
    again = Ledger.from_dict(ledger.to_dict())                                                     # saved the new way
    assert again.unsettled == {"2026-10-13": 100}


def test_schwab_follows_cash_rules_unless_you_say_margin(cfg):
    cfg["live"]["account_type"] = "auto"
    cfg["broker"] = "schwab"
    assert is_cash_account(cfg)
    cfg["broker"] = "alpaca"
    assert not is_cash_account(cfg)
    cfg["live"]["account_type"] = "cash"
    assert is_cash_account(cfg)
    cfg["broker"], cfg["live"]["account_type"] = "schwab", "margin"
    assert not is_cash_account(cfg)


def test_schwabs_cash_number_leaves_out_unsettled_money():
    from aitrader.brokers.schwab_broker import SchwabGateway
    gw = SchwabGateway.__new__(SchwabGateway)
    gw._account = lambda positions=False: {"currentBalances": {"cashAvailableForTrading": 80.0, "unsettledCash": 30.0}}
    assert gw.cash() == 50.0


def test_every_trading_day_of_2026_settles_on_a_real_settlement_day():
    day = date(2026, 1, 1)
    while day.year == 2026:
        settle = date.fromisoformat(settles_on(day))
        assert settle > day and is_settlement_day(settle)
        assert all(not is_settlement_day(day + timedelta(days=k)) for k in range(1, (settle - day).days))
        day += timedelta(days=1)
