"""
aitrader: a small, readable auto-trading bot for Alpaca (now) and Charles Schwab (later).

It has two "desks" that share the money but earn trust separately:
    swing  holds days to weeks, decides once a day at 3:45pm
    day    in and out the same day, decides every 5 minutes

Each desk moves through four phases, one at a time:

    1. STUDY        watch the market for a month, make predictions, grade them
    2. PLAN_REVIEW  write a trading plan and wait for YOU to approve it
    3. PAPER        trade the plan with fake money and real prices
    4. LIVE         trade real money (small and capped), after paper proves profitable

Where things live:

    config.py        loads config.yaml + .env
    market_hours.py  when the market is open (incl. early-close days)
    storage.py       the bot's memory (one SQLite file)
    market_data.py   downloads prices (Yahoo now, Schwab later)
    features.py      turns prices into numbers the AI can learn from
    brain.py         the local AI model
    strategies.py    the trading ideas the bot compares against each other
    risk.py          position sizing, stop-losses, kill switch
    engine.py        decides what to buy/sell today, backtester, trading day
    study.py         phase 1: daily predictions + grading
    planner.py       phase 2: pick the best strategy, write the plan
    phases.py        the rules for moving between phases
    performance.py   scorekeeping: return, drawdown, win rate...
    llm.py           optional local LLM (Ollama) for plain-English write-ups
    schwab_api.py    Schwab login + connection
    brokers/         paper (simulated), Alpaca and Schwab order execution
    alpaca_api.py    Alpaca connection
    mac_service.py   background autopilot on a Mac
    claude_setup.py  connects Claude Desktop (MCP)
"""
