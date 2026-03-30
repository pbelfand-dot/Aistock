import os
import json
import asyncio
from typing import AsyncGenerator

import yfinance as yf
import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="AiStock API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

TRACKED_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

TRENDING_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "AMD", "INTC", "NFLX",
    "UBER", "SNAP", "PLTR", "COIN", "RBLX"
]


def fetch_stock_data(ticker: str) -> dict:
    """Fetch stock data from yfinance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        hist = stock.history(period="1mo")
        if len(hist) >= 2:
            month_change = ((hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0]) * 100
        else:
            month_change = 0.0

        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        if current_price == 0 and len(hist) > 0:
            current_price = float(hist["Close"].iloc[-1])

        market_cap = info.get("marketCap", 0)
        if market_cap and market_cap > 1_000_000_000:
            market_cap_str = f"${market_cap / 1_000_000_000:.1f}B"
        elif market_cap and market_cap > 1_000_000:
            market_cap_str = f"${market_cap / 1_000_000:.1f}M"
        else:
            market_cap_str = "N/A"

        return {
            "ticker": ticker,
            "company_name": info.get("longName", ticker),
            "current_price": round(current_price, 2),
            "fifty_two_week_high": round(info.get("fiftyTwoWeekHigh", 0), 2),
            "fifty_two_week_low": round(info.get("fiftyTwoWeekLow", 0), 2),
            "pe_ratio": round(info.get("trailingPE", 0) or 0, 2),
            "market_cap": market_cap_str,
            "volume": info.get("volume", 0) or info.get("regularMarketVolume", 0),
            "month_change_pct": round(month_change, 2),
            "sector": info.get("sector", "Technology"),
            "description": info.get("longBusinessSummary", "")[:500] if info.get("longBusinessSummary") else "",
        }
    except Exception as e:
        return {
            "ticker": ticker,
            "company_name": ticker,
            "current_price": 0,
            "fifty_two_week_high": 0,
            "fifty_two_week_low": 0,
            "pe_ratio": 0,
            "market_cap": "N/A",
            "volume": 0,
            "month_change_pct": 0,
            "sector": "Unknown",
            "description": f"Error fetching data: {str(e)}",
        }


@app.get("/api/suggestions")
async def get_suggestions():
    """Get AI-powered stock suggestions using Claude with adaptive thinking."""
    loop = asyncio.get_event_loop()
    stocks_data = await loop.run_in_executor(
        None,
        lambda: [fetch_stock_data(t) for t in TRACKED_TICKERS]
    )

    stocks_summary = "\n\n".join([
        f"**{s['ticker']} ({s['company_name']})**\n"
        f"- Current Price: ${s['current_price']}\n"
        f"- 52-Week High: ${s['fifty_two_week_high']} | Low: ${s['fifty_two_week_low']}\n"
        f"- P/E Ratio: {s['pe_ratio'] if s['pe_ratio'] else 'N/A'}\n"
        f"- Market Cap: {s['market_cap']}\n"
        f"- Volume: {s['volume']:,}\n"
        f"- 1-Month Change: {s['month_change_pct']:+.2f}%\n"
        f"- Sector: {s['sector']}"
        for s in stocks_data
    ])

    prompt = f"""You are an expert stock analyst. Analyze the following stocks and provide investment recommendations.

## Stock Data (as of today)

{stocks_summary}

## Task

Analyze each stock based on:
1. **Fundamentals**: P/E ratio, market cap, valuation relative to 52-week range
2. **Momentum**: 1-month price change, distance from 52-week highs/lows
3. **Risk Assessment**: Volatility indicators, sector risks, valuation risk

For each stock, provide a recommendation with these exact JSON fields:
- ticker: string (stock symbol)
- company_name: string (full company name)
- recommendation: string (must be exactly "BUY", "HOLD", or "SELL")
- confidence: number (0-100, your confidence in this recommendation)
- reasoning: string (2-3 sentences explaining your analysis)
- risk_level: string (must be exactly "LOW", "MEDIUM", or "HIGH")
- target_price: number (your 12-month price target)

Return ONLY a valid JSON array with no additional text, markdown, or explanation. Example format:
[
  {{
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "recommendation": "BUY",
    "confidence": 78,
    "reasoning": "Apple shows strong momentum with solid fundamentals...",
    "risk_level": "LOW",
    "target_price": 210.50
  }}
]

Analyze all {len(TRACKED_TICKERS)} stocks and return recommendations for all of them."""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text = block.text
                break

        # Parse the JSON response
        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        recommendations = json.loads(response_text)

        # Merge recommendations with live stock data
        stock_map = {s["ticker"]: s for s in stocks_data}
        for rec in recommendations:
            ticker = rec.get("ticker")
            if ticker in stock_map:
                rec["current_price"] = stock_map[ticker]["current_price"]
                rec["month_change_pct"] = stock_map[ticker]["month_change_pct"]
                rec["market_cap"] = stock_map[ticker]["market_cap"]
                rec["volume"] = stock_map[ticker]["volume"]
                rec["pe_ratio"] = stock_map[ticker]["pe_ratio"]
                rec["fifty_two_week_high"] = stock_map[ticker]["fifty_two_week_high"]
                rec["fifty_two_week_low"] = stock_map[ticker]["fifty_two_week_low"]

        return {"recommendations": recommendations, "status": "success"}

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response as JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting suggestions: {str(e)}")


@app.get("/api/stock/{ticker}")
async def get_stock_analysis(ticker: str):
    """Get detailed stock info with streaming AI analysis."""
    ticker = ticker.upper()

    loop = asyncio.get_event_loop()
    stock_data = await loop.run_in_executor(None, lambda: fetch_stock_data(ticker))

    prompt = f"""You are an expert financial analyst. Provide a comprehensive analysis of {ticker} ({stock_data['company_name']}).

## Current Market Data
- **Current Price**: ${stock_data['current_price']}
- **52-Week Range**: ${stock_data['fifty_two_week_low']} - ${stock_data['fifty_two_week_high']}
- **P/E Ratio**: {stock_data['pe_ratio'] if stock_data['pe_ratio'] else 'N/A'}
- **Market Cap**: {stock_data['market_cap']}
- **Volume**: {stock_data['volume']:,}
- **1-Month Performance**: {stock_data['month_change_pct']:+.2f}%
- **Sector**: {stock_data['sector']}

## Company Overview
{stock_data['description'] if stock_data['description'] else 'Information not available.'}

## Analysis Request

Please provide a detailed investment analysis covering:

### 1. Technical Overview
Analyze the current price position relative to 52-week range, momentum indicators, and key price levels.

### 2. Fundamental Analysis
Evaluate the P/E ratio, market cap valuation, and what they suggest about growth expectations vs. current pricing.

### 3. Risk Assessment
Identify key risks including market, sector-specific, competitive, and macroeconomic risks.

### 4. Investment Thesis
Present both bull and bear cases for this stock with specific price catalysts.

### 5. Recommendation
Give your final recommendation (BUY/HOLD/SELL) with a 12-month price target and confidence level.

Write in a professional, analytical tone suitable for sophisticated investors."""

    async def stream_analysis() -> AsyncGenerator[str, None]:
        try:
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            yield f"\n\nError: {str(e)}"

    return StreamingResponse(
        stream_analysis(),
        media_type="text/plain",
        headers={
            "X-Stock-Price": str(stock_data["current_price"]),
            "X-Stock-Change": str(stock_data["month_change_pct"]),
            "X-Stock-Name": stock_data["company_name"],
            "Access-Control-Expose-Headers": "X-Stock-Price, X-Stock-Change, X-Stock-Name",
        }
    )


@app.get("/api/trending")
async def get_trending():
    """Get trending stocks with basic stats (no AI)."""
    loop = asyncio.get_event_loop()

    async def fetch_all():
        tasks = [
            loop.run_in_executor(None, lambda t=ticker: fetch_stock_data(t))
            for ticker in TRENDING_TICKERS
        ]
        return await asyncio.gather(*tasks)

    stocks = await fetch_all()

    trending = []
    for s in stocks:
        if s["current_price"] > 0:
            trending.append({
                "ticker": s["ticker"],
                "company_name": s["company_name"],
                "current_price": s["current_price"],
                "month_change_pct": s["month_change_pct"],
                "volume": s["volume"],
                "market_cap": s["market_cap"],
                "sector": s["sector"],
            })

    trending.sort(key=lambda x: abs(x["month_change_pct"]), reverse=True)

    return {"trending": trending, "status": "success"}


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "AiStock API"}
