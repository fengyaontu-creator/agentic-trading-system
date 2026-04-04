"""
sentiment_tools.py — 多源情绪分析工具
Owner: Person B

替换模板中 get_market_sentiment 里的随机情绪数据。
接入真实新闻源 + 可选社交媒体情绪，多源融合后输出情绪评分。

数据源：
1. NewsAPI (newsapi.org) — 主数据源，免费 tier 可用
2. FinViz headlines — 备用数据源（网页抓取，无需 API key）
"""

import os
import re
import json
import requests
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
from langchain_core.tools import tool


# ============================================================================
# 新闻数据获取
# ============================================================================

def fetch_news_headlines(symbol: str, days: int = 7) -> List[str]:
    """
    Fetch recent news headlines for a stock symbol using NewsAPI.

    Setup:
    1. Register at https://newsapi.org/ (free developer tier)
    2. Add NEWS_API_KEY to your .env file

    Args:
        symbol: Stock ticker (e.g., 'AAPL')
        days: Number of days to look back

    Returns:
        List of headline strings
    """
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        print(f"WARNING: NEWS_API_KEY not set, returning empty headlines for {symbol}")
        return []

    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": symbol,
        "from": from_date,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 20,
        "apiKey": api_key,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        headlines = [
            article["title"]
            for article in data.get("articles", [])
            if article.get("title")
        ]
        return headlines
    except requests.exceptions.RequestException as e:
        print(f"ERROR: NewsAPI request failed for {symbol}: {e}")
        return []


def fetch_finviz_sentiment(symbol: str) -> Dict:
    """
    Scrape FinViz for analyst ratings and news headlines.
    No API key needed — uses web scraping.

    Args:
        symbol: Stock ticker

    Returns:
        Dict with 'headlines' (list of str) and 'analyst_rating' (str)
    """
    from bs4 import BeautifulSoup

    url = f"https://finviz.com/quote.ashx?t={symbol}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://finviz.com/",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: FinViz request failed for {symbol}: {e}")
        return {"headlines": [], "analyst_rating": "N/A"}

    soup = BeautifulSoup(response.text, "html.parser")

    # --- News headlines ---
    headlines = []
    news_table = soup.find(id="news-table")
    if news_table:
        for row in news_table.find_all("tr")[:10]:
            a_tag = row.find("a")
            if a_tag and a_tag.text.strip():
                headlines.append(a_tag.text.strip())

    # --- Analyst recommendation ---
    # FinViz displays it in a snapshot table as "Recom" with a numeric value,
    # and/or as a text label in the ratings table rows.
    analyst_rating = "N/A"
    for td in soup.find_all("td"):
        if td.text.strip() == "Recom":
            sibling = td.find_next_sibling("td")
            if sibling:
                analyst_rating = sibling.text.strip()
            break

    return {"headlines": headlines, "analyst_rating": analyst_rating}


# ============================================================================
# LLM-based 情绪分析
# ============================================================================

def analyze_headlines_with_llm(headlines: List[str], llm) -> Dict:
    """
    Use LLM to analyze sentiment from a list of news headlines.

    Args:
        headlines: List of news headline strings
        llm: LangChain LLM instance

    Returns:
        Dict with average sentiment score and per-headline breakdown
    """
    if not headlines:
        return {
            "average_score": 0.0,
            "label": "neutral",
            "num_articles": 0,
            "breakdown": []
        }

    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a financial sentiment analyst. "
            "Analyze each headline and rate its market sentiment from -1.0 (very bearish) "
            "to +1.0 (very bullish). Focus on the likely impact on the stock price.\n\n"
            "Rules for the JSON output:\n"
            "- Respond with ONLY a valid JSON object — no markdown, no extra text\n"
            "- The 'reason' field must be plain ASCII, no quotes, no newlines, max 15 words\n"
            "- Do NOT escape apostrophes or use smart quotes inside string values\n\n"
            "Format:\n"
            "{{\n"
            '    "scores": [\n'
            '        {{"headline": "...", "score": 0.0, "reason": "one sentence"}},\n'
            "        ...\n"
            "    ],\n"
            '    "average_score": 0.0,\n'
            '    "overall_label": "bullish" | "bearish" | "neutral"\n'
            "}}"
        )),
        ("human", "Analyze these headlines:\n{headlines}"),
    ])

    headlines_text = "\n".join(f"- {h}" for h in headlines)
    chain = prompt | llm

    try:
        response = chain.invoke({"headlines": headlines_text})
        content = response.content

        # Extract the outermost {...} block — handles fences, leading/trailing text,
        # and stray characters that break a simple strip approach.
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise json.JSONDecodeError("No JSON object found in LLM response", content, 0)
        parsed = json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse LLM JSON response: {e}")
        return {
            "average_score": 0.0,
            "label": "neutral",
            "num_articles": len(headlines),
            "breakdown": []
        }
    except Exception as e:
        print(f"ERROR: LLM call failed: {e}")
        return {
            "average_score": 0.0,
            "label": "neutral",
            "num_articles": len(headlines),
            "breakdown": []
        }

    return {
        "average_score": float(parsed.get("average_score", 0.0)),
        "label": parsed.get("overall_label", "neutral"),
        "num_articles": len(headlines),
        "breakdown": parsed.get("scores", []),
    }


# ============================================================================
# 多源融合
# ============================================================================

def fuse_sentiment_scores(
    news_score: float,
    finviz_score: float = 0.0,
    av_score: float = 0.0,
    news_weight: float = 0.4,
    finviz_weight: float = 0.3,
    av_weight: float = 0.3,
    news_available: bool = True,
    finviz_available: bool = True,
    av_available: bool = False,
) -> Dict:
    """
    Fuse sentiment scores from three sources into a single score.
    When a source is unavailable its weight is redistributed to the others.

    Args:
        news_score:     Sentiment from NewsAPI headlines (-1 to +1)
        finviz_score:   Sentiment from FinViz (-1 to +1)
        av_score:       Sentiment from Alpha Vantage (-1 to +1)
        news_available:   Whether NewsAPI produced real data
        finviz_available: Whether FinViz produced real data
        av_available:     Whether Alpha Vantage produced real data
    """
    effective_news_w   = news_weight   if news_available   else 0.0
    effective_finviz_w = finviz_weight if finviz_available else 0.0
    effective_av_w     = av_weight     if av_available     else 0.0
    total_weight = effective_news_w + effective_finviz_w + effective_av_w

    if total_weight == 0.0:
        fused = 0.0
        confidence = 0.2
    else:
        fused = (
            news_score   * effective_news_w +
            finviz_score * effective_finviz_w +
            av_score     * effective_av_w
        ) / total_weight

        active_scores = [
            s for s, avail in [
                (news_score, news_available),
                (finviz_score, finviz_available),
                (av_score, av_available),
            ] if avail
        ]
        num_sources = len(active_scores)
        if num_sources >= 2:
            spread = max(active_scores) - min(active_scores)
            agreement = 1.0 - spread / 2.0
            confidence = agreement * 0.8 + 0.2
        else:
            confidence = 0.5  # single-source: moderate confidence

    if fused > 0.5:
        label = "very_bullish"
    elif fused > 0.2:
        label = "bullish"
    elif fused > -0.2:
        label = "neutral"
    elif fused > -0.5:
        label = "bearish"
    else:
        label = "very_bearish"

    return {
        "fused_score": round(fused, 4),
        "confidence": round(confidence, 4),
        "label": label,
        "sources": {
            "news":   round(news_score, 4),
            "finviz": round(finviz_score, 4),
            "alpha_vantage": round(av_score, 4),
        }
    }


# ============================================================================
# Alpha Vantage 情绪数据
# ============================================================================

def fetch_alpha_vantage_sentiment(symbol: str) -> Dict:
    """
    Fetch news sentiment score from Alpha Vantage News Sentiment API.
    Returns a score in [-1, 1] and the number of articles used.

    Requires ALPHA_VANTAGE_API_KEY in .env
    """
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        print(f"WARNING: ALPHA_VANTAGE_API_KEY not set, skipping for {symbol}")
        return {"score": 0.0, "num_articles": 0, "available": False}

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": symbol,
        "apikey": api_key,
        "limit": 20,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        feed = data.get("feed", [])
        if not feed:
            return {"score": 0.0, "num_articles": 0, "available": False}

        # Each article has ticker_sentiment list — find the score for our symbol
        scores = []
        for article in feed:
            for ticker_data in article.get("ticker_sentiment", []):
                if ticker_data.get("ticker") == symbol:
                    score = float(ticker_data.get("ticker_sentiment_score", 0.0))
                    scores.append(score)

        if not scores:
            return {"score": 0.0, "num_articles": 0, "available": False}

        avg_score = float(np.mean(scores))
        return {"score": round(avg_score, 4), "num_articles": len(scores), "available": True}

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Alpha Vantage request failed for {symbol}: {e}")
        return {"score": 0.0, "num_articles": 0, "available": False}


# ============================================================================
# 主工具（替换模板中的 @tool get_market_sentiment）
# ============================================================================

@tool
def get_market_sentiment(symbol: str) -> str:
    """
    Get multi-source market sentiment analysis for a symbol.

    Combines:
    1. NewsAPI headlines → LLM sentiment scoring
    2. FinViz headlines / analyst ratings

    Args:
        symbol: Stock ticker symbol

    Returns:
        JSON string with fused sentiment score and analysis
    """
    # --- Build LLM instance once (shared across sources) ---
    llm = None
    try:
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        llm = ChatOpenAI(
            model="anthropic/claude-haiku-4-5",
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            temperature=0,
        )
    except Exception as e:
        print(f"WARNING: LLM unavailable, sentiment scoring disabled: {e}")

    # --- Source 1: NewsAPI + LLM scoring ---
    news_headlines = fetch_news_headlines(symbol)
    if llm and news_headlines:
        news_analysis = analyze_headlines_with_llm(news_headlines, llm)
    else:
        news_analysis = {"average_score": 0.0, "label": "neutral", "breakdown": []}
    news_score = news_analysis.get("average_score", 0.0)
    news_available = bool(news_headlines)

    # --- Source 2: FinViz ---
    finviz_data = fetch_finviz_sentiment(symbol)
    finviz_headlines = finviz_data.get("headlines", [])
    if llm and finviz_headlines:
        finviz_analysis = analyze_headlines_with_llm(finviz_headlines, llm)
    else:
        finviz_analysis = {"average_score": 0.0}
    finviz_score = finviz_analysis.get("average_score", 0.0)
    finviz_available = bool(finviz_headlines)

    # --- Source 3: Alpha Vantage ---
    av_data = fetch_alpha_vantage_sentiment(symbol)
    av_score = av_data["score"]
    av_available = av_data["available"]

    # --- Fuse ---
    fused = fuse_sentiment_scores(
        news_score, finviz_score, av_score,
        news_available=news_available,
        finviz_available=finviz_available,
        av_available=av_available,
    )

    # --- Build description ---
    total_articles = len(news_headlines) + len(finviz_headlines) + av_data["num_articles"]
    analyst_rating = finviz_data.get("analyst_rating", "N/A")
    source_parts = []
    if news_headlines:
        source_parts.append(f"{len(news_headlines)} NewsAPI article(s)")
    if finviz_headlines:
        source_parts.append(f"{len(finviz_headlines)} FinViz headline(s)")
    if av_available:
        source_parts.append(f"{av_data['num_articles']} Alpha Vantage article(s)")
    if not source_parts:
        source_parts.append("no articles retrieved")
    description = (
        f"{fused['label'].replace('_', ' ').title()} outlook for {symbol} "
        f"based on {', '.join(source_parts)}."
        + (f" Analyst rating: {analyst_rating}." if analyst_rating != "N/A" else "")
    )

    # --- Build result ---
    result = {
        "symbol": symbol,
        "sentiment": fused["label"],
        "sentiment_score": fused["fused_score"],
        "confidence": fused["confidence"],
        "description": description,
        "analyst_rating": analyst_rating,
        "num_articles": total_articles,
        "news_volume": "high" if total_articles > 10 else "medium" if total_articles > 3 else "low",
        "sources": {
            "news": {
                "score": fused["sources"]["news"],
                "num_headlines": len(news_headlines),
            },
            "finviz": {
                "score": fused["sources"]["finviz"],
                "num_headlines": len(finviz_headlines),
                "analyst_rating": analyst_rating,
            },
            "alpha_vantage": {
                "score": fused["sources"]["alpha_vantage"],
                "num_articles": av_data["num_articles"],
            },
        },
    }

    return json.dumps(result, indent=2)


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    test_symbols = ["AAPL", "TSLA"]
    for sym in test_symbols:
        print(f"\n{'='*50}")
        print(f"Testing get_market_sentiment for {sym}...")
        print('='*50)
        raw = get_market_sentiment.invoke({"symbol": sym})
        parsed = json.loads(raw)
        print(json.dumps(parsed, indent=2))
        print(f"  => {parsed['sentiment']}  score={parsed['sentiment_score']}  confidence={parsed['confidence']}")
        print(f"     {parsed['description']}")
