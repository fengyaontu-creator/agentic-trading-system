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
import json
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
    # TODO: Implement NewsAPI integration
    # -------------------------------------------------------
    # from newsapi import NewsApiClient
    #
    # api_key = os.getenv("NEWS_API_KEY")
    # if not api_key:
    #     print("WARNING: NEWS_API_KEY not set, returning empty headlines")
    #     return []
    #
    # newsapi = NewsApiClient(api_key=api_key)
    # from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    #
    # # Search for company name or ticker
    # response = newsapi.get_everything(
    #     q=symbol,
    #     from_param=from_date,
    #     language='en',
    #     sort_by='publishedAt',
    #     page_size=20
    # )
    #
    # headlines = [article['title'] for article in response.get('articles', [])]
    # return headlines
    # -------------------------------------------------------

    # Placeholder: return empty list until implemented
    print(f"[TODO] fetch_news_headlines not yet implemented for {symbol}")
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
    # TODO: Implement FinViz scraping
    # -------------------------------------------------------
    # import requests
    # from bs4 import BeautifulSoup
    #
    # url = f"https://finviz.com/quote.ashx?t={symbol}"
    # headers = {'User-Agent': 'Mozilla/5.0'}
    # response = requests.get(url, headers=headers)
    # soup = BeautifulSoup(response.text, 'html.parser')
    #
    # # Extract news headlines from the news table
    # news_table = soup.find(id='news-table')
    # headlines = []
    # if news_table:
    #     rows = news_table.find_all('tr')
    #     for row in rows[:10]:  # Last 10 headlines
    #         title = row.a.text if row.a else ""
    #         if title:
    #             headlines.append(title)
    #
    # # Extract analyst recommendation if available
    # analyst_rating = "N/A"
    # # ... parse from page ...
    #
    # return {"headlines": headlines, "analyst_rating": analyst_rating}
    # -------------------------------------------------------

    print(f"[TODO] fetch_finviz_sentiment not yet implemented for {symbol}")
    return {"headlines": [], "analyst_rating": "N/A"}


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

    # TODO: Implement LLM sentiment analysis
    # -------------------------------------------------------
    # from langchain_core.prompts import ChatPromptTemplate
    #
    # prompt = ChatPromptTemplate.from_messages([
    #     ("system", """You are a financial sentiment analyst.
    # Analyze each headline and rate its sentiment from -1.0 (very bearish)
    # to +1.0 (very bullish). Consider the financial market impact.
    #
    # Respond with ONLY a JSON object:
    # {{
    #     "scores": [
    #         {{"headline": "...", "score": 0.0, "reason": "..."}},
    #         ...
    #     ],
    #     "average_score": 0.0,
    #     "overall_label": "bullish" | "bearish" | "neutral"
    # }}"""),
    #     ("human", "Analyze these headlines:\n{headlines}")
    # ])
    #
    # chain = prompt | llm
    # headlines_text = "\n".join(f"- {h}" for h in headlines)
    # response = chain.invoke({"headlines": headlines_text})
    #
    # # Parse JSON response
    # content = response.content
    # if "```json" in content:
    #     content = content.split("```json")[1].split("```")[0]
    # result = json.loads(content.strip())
    # return result
    # -------------------------------------------------------

    print("[TODO] analyze_headlines_with_llm not yet implemented")
    return {
        "average_score": 0.0,
        "label": "neutral",
        "num_articles": len(headlines),
        "breakdown": []
    }


# ============================================================================
# 多源融合
# ============================================================================

def fuse_sentiment_scores(
    news_score: float,
    finviz_score: float = 0.0,
    news_weight: float = 0.6,
    finviz_weight: float = 0.4
) -> Dict:
    """
    Fuse sentiment scores from multiple sources into a single score.

    When only one source is available, that source gets full weight.

    Args:
        news_score: Sentiment from NewsAPI headlines (-1 to +1)
        finviz_score: Sentiment from FinViz (-1 to +1)
        news_weight: Weight for news source (default 0.6)
        finviz_weight: Weight for FinViz source (default 0.4)

    Returns:
        Dict with fused score, confidence, and label
    """
    # Weighted average
    total_weight = news_weight + finviz_weight
    fused = (news_score * news_weight + finviz_score * finviz_weight) / total_weight

    # Confidence is higher when sources agree
    agreement = 1.0 - abs(news_score - finviz_score) / 2.0
    confidence = agreement * 0.8 + 0.2  # minimum 0.2 confidence

    # Label
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
            "news": round(news_score, 4),
            "finviz": round(finviz_score, 4)
        }
    }


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
    # --- Source 1: NewsAPI ---
    news_headlines = fetch_news_headlines(symbol)
    # TODO: once LLM integration is done, replace 0.0 with actual score
    # news_analysis = analyze_headlines_with_llm(news_headlines, llm)
    # news_score = news_analysis.get("average_score", 0.0)
    news_score = 0.0

    # --- Source 2: FinViz ---
    finviz_data = fetch_finviz_sentiment(symbol)
    # TODO: score the FinViz headlines similarly
    finviz_score = 0.0

    # --- Fuse ---
    fused = fuse_sentiment_scores(news_score, finviz_score)

    # --- Build result ---
    result = {
        'symbol': symbol,
        'sentiment': fused['label'],
        'sentiment_score': fused['fused_score'],
        'confidence': fused['confidence'],
        'description': f"Sentiment analysis based on {len(news_headlines)} news articles",
        'news_volume': 'high' if len(news_headlines) > 10 else 'medium' if len(news_headlines) > 3 else 'low',
        'num_articles': len(news_headlines),
        'sources': fused['sources'],
    }

    return json.dumps(result, indent=2)


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    print("Testing get_market_sentiment for AAPL...")
    result = get_market_sentiment.invoke({"symbol": "AAPL"})
    print(result)
