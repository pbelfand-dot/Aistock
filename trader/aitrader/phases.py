"""
phases.py: the rules for moving from one phase to the next.

    STUDY --(30 days + a plan that passes)--> PLAN_REVIEW
    PLAN_REVIEW --(you approve the plan)--> PAPER
    PAPER --(promotion rules pass + you confirm)--> LIVE
    LIVE --(kill switch or `kill` command)--> PAPER (the plan must earn LIVE again)

No shortcuts to LIVE. Every step up needs numbers AND a human "yes".
"""
from datetime import date
from enum import Enum


class Phase(str, Enum):
    STUDY = "STUDY"
    PLAN_REVIEW = "PLAN_REVIEW"
    PAPER = "PAPER"
    LIVE = "LIVE"


STEP_NUMBER = {Phase.STUDY: 1, Phase.PLAN_REVIEW: 2, Phase.PAPER: 3, Phase.LIVE: 4}


def current_phase(store) -> Phase:
    return Phase(store.get("phase", Phase.STUDY.value))


def set_phase(store, phase: Phase, reason: str):
    old = current_phase(store)
    store.set("phase", phase.value)
    store.set(f"{phase.value.lower()}_started_on", date.today().isoformat())
    store.log(f"PHASE CHANGE: {old.value} -> {phase.value} ({reason})")


def study_progress(store, cfg: dict, today: date = None) -> dict:
    """How far along the study month is, and what's still missing."""
    today = today or date.today()
    started = store.get("study_started_on")
    days = (today - date.fromisoformat(started)).days if started else 0
    study_days = len(store.study_dates())
    need_days, need_study = cfg["study"]["min_calendar_days"], cfg["study"]["min_study_days"]
    missing = []
    if days < need_days:
        missing.append(f"{need_days - days} more calendar days")
    if study_days < need_study:
        missing.append(f"{need_study - study_days} more trading days of study")
    return {"calendar_days": days, "study_days": study_days, "ready": not missing, "missing": missing}


def check_promotion(cfg: dict, paper: dict, benchmark_return_pct: float) -> list:
    """Each rule: (name, actual, required, passed). ALL must pass to go LIVE."""
    rules = cfg["promotion"]
    checks = [
        ("trading days in paper", paper["trading_days"], f">= {rules['min_trading_days']}",
         paper["trading_days"] >= rules["min_trading_days"]),
        ("closed trades", paper["num_closed_trades"], f">= {rules['min_closed_trades']}",
         paper["num_closed_trades"] >= rules["min_closed_trades"]),
        ("total return %", paper["total_return_pct"], f"> {rules['min_total_return_pct']}",
         paper["total_return_pct"] > rules["min_total_return_pct"]),
        ("profit factor", paper["profit_factor"], f">= {rules['min_profit_factor']}",
         paper["profit_factor"] >= rules["min_profit_factor"]),
        ("max drawdown %", paper["max_drawdown_pct"], f"<= {rules['max_drawdown_pct']}",
         paper["max_drawdown_pct"] <= rules["max_drawdown_pct"]),
    ]
    if rules.get("must_beat_benchmark"):
        checks.append((f"beat {cfg['benchmark']} ({benchmark_return_pct:.2f}%)",
                       paper["total_return_pct"], f"> {benchmark_return_pct:.2f}",
                       paper["total_return_pct"] > benchmark_return_pct))
    return checks
