"""
Finance + weather "skills" exposed to Gemini via function calling.

Cleaned up from the original skills.py:
- Removed the unused `execute_function_call` / `finance_map` dead code paths
  (the app only ever called `handle_financial_function_call`).
- Removed the leftover "Medical Assistant" system prompt / chat-creation
  function that lived in this file — system prompt + chat orchestration now
  live in services/orchestrator.py and services/gemini_stream.py so there's
  one source of truth for the assistant's persona.
- FinancialMarketsController is now created fresh per call via
  get_financial_controller() so that API keys updated at runtime via the
  sidebar are actually picked up (previously the controller was built once
  at import time and cached stale keys forever).
"""
import os
import json
import aiohttp
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from google.genai import types
import config
from utils.logger import logger

WEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"


@dataclass
class StockData:
    symbol: str
    price: float
    change: float
    change_percent: float
    volume: int
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    year_high: Optional[float] = None
    year_low: Optional[float] = None


@dataclass
class CryptoData:
    symbol: str
    name: str
    price: float
    change_24h: float
    change_percent_24h: float
    market_cap: float
    volume_24h: float
    rank: int


@dataclass
class NewsItem:
    title: str
    summary: str
    source: str
    published: datetime
    sentiment: Optional[str] = None
    symbols: Optional[List[str]] = None


class FinancialMarketsController:
    def __init__(self):
        self.alpha_vantage_key = config.ALPHA_VANTAGE_API_KEY
        self.finnhub_key = config.FINNHUB_API_KEY
        self.polygon_key = os.getenv("POLYGON_API_KEY")
        self.coinmarketcap_key = os.getenv("COINMARKETCAP_API_KEY")
        self.cache: Dict[str, Any] = {}
        self.cache_timeout = 60  # seconds

    async def get_stock_quote(self, symbol: str) -> Optional[StockData]:
        symbol = symbol.upper()
        cache_key = f"stock_{symbol}"
        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            if self.finnhub_key:
                stock_data = await self._get_finnhub_quote(symbol)
                if stock_data:
                    self._cache_data(cache_key, stock_data)
                    return stock_data
            if self.alpha_vantage_key:
                stock_data = await self._get_alphavantage_quote(symbol)
                if stock_data:
                    self._cache_data(cache_key, stock_data)
                    return stock_data
            if self.polygon_key:
                stock_data = await self._get_polygon_quote(symbol)
                if stock_data:
                    self._cache_data(cache_key, stock_data)
                    return stock_data
        except Exception as e:
            logger.error(f"Error fetching stock quote for {symbol}: {e}")

        return None

    async def _get_finnhub_quote(self, symbol: str) -> Optional[StockData]:
        try:
            async with aiohttp.ClientSession() as session:
                quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={self.finnhub_key}"
                async with session.get(quote_url) as response:
                    if response.status != 200:
                        return None
                    quote_data = await response.json()
                    if quote_data.get("c") is None:
                        return None

                profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={self.finnhub_key}"
                async with session.get(profile_url) as profile_response:
                    profile_data = await profile_response.json() if profile_response.status == 200 else {}

                return StockData(
                    symbol=symbol,
                    price=quote_data["c"],
                    change=quote_data["d"],
                    change_percent=quote_data["dp"],
                    volume=0,
                    market_cap=profile_data.get("marketCapitalization"),
                    day_high=quote_data["h"],
                    day_low=quote_data["l"],
                )
        except Exception as e:
            logger.error(f"Finnhub API error: {e}")
            return None

    async def _get_alphavantage_quote(self, symbol: str) -> Optional[StockData]:
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={self.alpha_vantage_key}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()
                    quote = data.get("Global Quote", {})
                    if not quote:
                        return None
                    return StockData(
                        symbol=symbol,
                        price=float(quote.get("05. price", 0)),
                        change=float(quote.get("09. change", 0)),
                        change_percent=float(quote.get("10. change percent", "0%").replace("%", "")),
                        volume=int(quote.get("06. volume", 0)),
                        day_high=float(quote.get("03. high", 0)),
                        day_low=float(quote.get("04. low", 0)),
                    )
        except Exception as e:
            logger.error(f"Alpha Vantage API error: {e}")
            return None

    async def _get_polygon_quote(self, symbol: str) -> Optional[StockData]:
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?adjusted=true&apikey={self.polygon_key}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()
                    results = data.get("results", [])
                    if not results:
                        return None
                    result = results[0]
                    change = result["c"] - result["o"]
                    change_percent = (change / result["o"]) * 100
                    return StockData(
                        symbol=symbol,
                        price=result["c"],
                        change=change,
                        change_percent=change_percent,
                        volume=result["v"],
                        day_high=result["h"],
                        day_low=result["l"],
                    )
        except Exception as e:
            logger.error(f"Polygon API error: {e}")
            return None

    async def get_crypto_quote(self, symbol: str) -> Optional[CryptoData]:
        symbol = symbol.upper()
        cache_key = f"crypto_{symbol}"
        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            if self.coinmarketcap_key:
                crypto_data = await self._get_coinmarketcap_quote(symbol)
                if crypto_data:
                    self._cache_data(cache_key, crypto_data)
                    return crypto_data
        except Exception as e:
            logger.error(f"Error fetching crypto quote for {symbol}: {e}")

        return None

    async def _get_coinmarketcap_quote(self, symbol: str) -> Optional[CryptoData]:
        try:
            headers = {"X-CMC_PRO_API_KEY": self.coinmarketcap_key, "Accept": "application/json"}
            url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={symbol}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()
                    crypto_info = data.get("data", {}).get(symbol)
                    if not crypto_info:
                        return None
                    quote = crypto_info["quote"]["USD"]
                    return CryptoData(
                        symbol=symbol,
                        name=crypto_info["name"],
                        price=quote["price"],
                        change_24h=quote["price"] * (quote["percent_change_24h"] / 100),
                        change_percent_24h=quote["percent_change_24h"],
                        market_cap=quote["market_cap"],
                        volume_24h=quote["volume_24h"],
                        rank=crypto_info["cmc_rank"],
                    )
        except Exception as e:
            logger.error(f"CoinMarketCap API error: {e}")
            return None

    async def get_market_news(self, symbols: Optional[List[str]] = None, limit: int = 5) -> List[NewsItem]:
        cache_key = f"news_{'_'.join(symbols or ['general'])}"
        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            if self.finnhub_key:
                news_data = await self._get_finnhub_news(symbols, limit)
                if news_data:
                    self._cache_data(cache_key, news_data)
                    return news_data
        except Exception as e:
            logger.error(f"Error fetching market news: {e}")

        return []

    async def _get_finnhub_news(self, symbols: Optional[List[str]], limit: int) -> List[NewsItem]:
        try:
            news_items = []
            async with aiohttp.ClientSession() as session:
                if symbols:
                    from datetime import timedelta
                    for symbol in symbols[:3]:
                        url = (f"https://finnhub.io/api/v1/company-news?symbol={symbol}"
                               f"&from={(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}"
                               f"&to={datetime.now().strftime('%Y-%m-%d')}&token={self.finnhub_key}")
                        async with session.get(url) as response:
                            if response.status == 200:
                                news_data = await response.json()
                                for item in news_data[:max(1, limit // len(symbols))]:
                                    news_items.append(NewsItem(
                                        title=item["headline"],
                                        summary=item["summary"][:200] + "..." if len(item["summary"]) > 200 else item["summary"],
                                        source=item["source"],
                                        published=datetime.fromtimestamp(item["datetime"]),
                                        symbols=[symbol],
                                    ))
                else:
                    url = f"https://finnhub.io/api/v1/news?category=general&token={self.finnhub_key}"
                    async with session.get(url) as response:
                        if response.status == 200:
                            news_data = await response.json()
                            for item in news_data[:limit]:
                                news_items.append(NewsItem(
                                    title=item["headline"],
                                    summary=item["summary"][:200] + "..." if len(item["summary"]) > 200 else item["summary"],
                                    source=item["source"],
                                    published=datetime.fromtimestamp(item["datetime"]),
                                ))
            return sorted(news_items, key=lambda x: x.published, reverse=True)
        except Exception as e:
            logger.error(f"Finnhub news API error: {e}")
            return []

    async def get_portfolio_analysis(self, holdings: Dict[str, float]) -> Dict[str, Any]:
        portfolio_value, total_change, positions = 0, 0, []

        for symbol, quantity in holdings.items():
            if symbol.upper() in ["BTC", "ETH", "ADA", "DOT"]:
                quote = await self.get_crypto_quote(symbol)
                if quote:
                    position_value = quote.price * quantity
                    position_change = quote.change_24h * quantity
                    positions.append({
                        "symbol": symbol, "type": "crypto", "quantity": quantity,
                        "price": quote.price, "value": position_value, "change": position_change,
                        "change_percent": quote.change_percent_24h,
                    })
                    portfolio_value += position_value
                    total_change += position_change
            else:
                quote = await self.get_stock_quote(symbol)
                if quote:
                    position_value = quote.price * quantity
                    position_change = quote.change * quantity
                    positions.append({
                        "symbol": symbol, "type": "stock", "quantity": quantity,
                        "price": quote.price, "value": position_value, "change": position_change,
                        "change_percent": quote.change_percent,
                    })
                    portfolio_value += position_value
                    total_change += position_change

        portfolio_change_percent = (
            (total_change / (portfolio_value - total_change)) * 100
            if portfolio_value != total_change else 0
        )

        return {
            "total_value": portfolio_value,
            "total_change": total_change,
            "change_percent": portfolio_change_percent,
            "positions": positions,
            "best_performer": max(positions, key=lambda x: x["change_percent"], default=None),
            "worst_performer": min(positions, key=lambda x: x["change_percent"], default=None),
        }

    def _is_cached(self, key: str) -> bool:
        if key not in self.cache:
            return False
        return (datetime.now() - self.cache[key]["timestamp"]).seconds < self.cache_timeout

    def _cache_data(self, key: str, data: Any):
        self.cache[key] = {"data": data, "timestamp": datetime.now()}


def get_financial_controller() -> FinancialMarketsController:
    """Fresh controller per call so runtime key updates from the sidebar are honored."""
    return FinancialMarketsController()


# ---------------------------------------------------------------------------
# Function implementations (what Gemini's function calls actually execute)
# ---------------------------------------------------------------------------
async def get_stock_price(symbol: str) -> str:
    stock_data = await get_financial_controller().get_stock_quote(symbol)
    if not stock_data:
        return f"Sorry, I couldn't retrieve data for {symbol.upper()}. The market might be closed or the symbol might be invalid."

    change_direction = "📈" if stock_data.change >= 0 else "📉"
    change_text = "up" if stock_data.change >= 0 else "down"

    response = f"**{symbol.upper()} - ${stock_data.price:.2f}** {change_direction}\n"
    response += f"Change: ${stock_data.change:+.2f} ({stock_data.change_percent:+.2f}%)\n"
    if stock_data.market_cap:
        response += f"Market Cap: ${stock_data.market_cap/1000:.1f}B\n"
    if stock_data.day_high and stock_data.day_low:
        response += f"Day Range: ${stock_data.day_low:.2f} - ${stock_data.day_high:.2f}\n"
    response += f"\n{symbol.upper()} is {change_text} {abs(stock_data.change_percent):.2f}% today."
    return response


async def get_crypto_price(symbol: str) -> str:
    crypto_data = await get_financial_controller().get_crypto_quote(symbol)
    if not crypto_data:
        return f"Sorry, I couldn't retrieve crypto data for {symbol.upper()}. Please check the symbol."

    change_direction = "📈" if crypto_data.change_percent_24h >= 0 else "📉"
    change_text = "up" if crypto_data.change_percent_24h >= 0 else "down"

    response = f"**{crypto_data.name} ({symbol.upper()}) - ${crypto_data.price:.2f}** {change_direction}\n"
    response += f"24h Change: ${crypto_data.change_24h:+.2f} ({crypto_data.change_percent_24h:+.2f}%)\n"
    response += f"Market Cap: ${crypto_data.market_cap/1e9:.2f}B\n"
    response += f"24h Volume: ${crypto_data.volume_24h/1e9:.2f}B\n"
    response += f"Rank: #{crypto_data.rank}\n"
    response += f"\n{crypto_data.name} is {change_text} {abs(crypto_data.change_percent_24h):.2f}% in the last 24 hours."
    return response


async def get_market_news_summary(symbols: Optional[str] = None, count: int = 3) -> str:
    symbol_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    news_items = await get_financial_controller().get_market_news(symbol_list, count)

    if not news_items:
        return "Sorry, I couldn't retrieve market news at the moment."

    response = "**Latest Market News:**\n\n"
    for i, news in enumerate(news_items, 1):
        age = datetime.now() - news.published
        if age.days > 0:
            time_str = f"{age.days} days ago"
        elif age.seconds > 3600:
            time_str = f"{age.seconds // 3600} hours ago"
        else:
            time_str = f"{age.seconds // 60} minutes ago"
        response += f"**{i}. {news.title}**\n_{news.source} • {time_str}_\n{news.summary}\n\n"
    return response


async def analyze_portfolio(holdings_json: str) -> str:
    try:
        holdings = json.loads(holdings_json)
    except json.JSONDecodeError:
        return "I need the portfolio in JSON format like: {\"AAPL\": 100, \"TSLA\": 50, \"BTC\": 1.5}"

    analysis = await get_financial_controller().get_portfolio_analysis(holdings)
    if not analysis["positions"]:
        return "I couldn't analyze the portfolio. Please check the symbols and try again."

    change_direction = "📈" if analysis["total_change"] >= 0 else "📉"
    performance_text = "gained" if analysis["total_change"] >= 0 else "lost"

    response = f"**Portfolio Analysis** {change_direction}\n\n"
    response += f"**Total Value:** ${analysis['total_value']:,.2f}\n"
    response += f"**Today's Change:** ${analysis['total_change']:+,.2f} ({analysis['change_percent']:+.2f}%)\n\n"
    response += "**Top Holdings:**\n"

    for pos in sorted(analysis["positions"], key=lambda x: x["value"], reverse=True)[:5]:
        pos_direction = "📈" if pos["change"] >= 0 else "📉"
        response += f"• **{pos['symbol']}**: ${pos['value']:,.2f} ({pos['change_percent']:+.2f}%) {pos_direction}\n"

    if analysis["best_performer"]:
        response += f"\n**Best Performer:** {analysis['best_performer']['symbol']} ({analysis['best_performer']['change_percent']:+.2f}%)\n"
    if analysis["worst_performer"]:
        response += f"**Worst Performer:** {analysis['worst_performer']['symbol']} ({analysis['worst_performer']['change_percent']:+.2f}%)\n"

    response += f"\nYour portfolio has {performance_text} ${abs(analysis['total_change']):,.2f} today."
    return response


async def compare_stocks(symbols: str) -> str:
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    if len(symbol_list) < 2:
        return "I need at least two symbols to compare. Try: 'AAPL,MSFT,GOOGL'"

    controller = get_financial_controller()
    comparisons = []
    for symbol in symbol_list[:5]:
        stock_data = await controller.get_stock_quote(symbol)
        if stock_data:
            comparisons.append(stock_data)

    if not comparisons:
        return "I couldn't retrieve data for any of those symbols."

    comparisons.sort(key=lambda x: x.change_percent, reverse=True)
    response = "**Stock Comparison:**\n\n"
    for i, stock in enumerate(comparisons, 1):
        direction = "📈" if stock.change >= 0 else "📉"
        response += f"**{i}. {stock.symbol}** - ${stock.price:.2f} {direction}\n"
        response += f"   Change: ${stock.change:+.2f} ({stock.change_percent:+.2f}%)\n\n"

    best, worst = comparisons[0], comparisons[-1]
    response += f"**{best.symbol}** is leading with {best.change_percent:+.2f}%, while **{worst.symbol}** is trailing at {worst.change_percent:+.2f}%."
    return response


async def get_weather_info(location: str, units: str = "metric") -> dict:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{WEATHER_BASE_URL}/weather"
            params = {"q": location, "appid": config.OPENWEATHER_API_KEY, "units": units}
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "data": {
                            "location": f"{data['name']}, {data['sys']['country']}",
                            "temperature": data["main"]["temp"],
                            "feels_like": data["main"]["feels_like"],
                            "humidity": data["main"]["humidity"],
                            "pressure": data["main"]["pressure"],
                            "description": data["weather"][0]["description"].title(),
                            "wind_speed": data.get("wind", {}).get("speed", 0),
                            "visibility": data.get("visibility", 0) / 1000,
                            "units": "°C" if units == "metric" else "°F" if units == "imperial" else "K",
                        },
                    }
                error_data = await response.json()
                return {"success": False, "error": f"Weather API error: {error_data.get('message', 'Unknown error')}"}
    except Exception as e:
        logger.error(f"Error fetching weather data: {e}")
        return {"success": False, "error": f"Failed to fetch weather data: {str(e)}"}


async def get_weather_forecast(location: str, units: str = "metric") -> dict:
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{WEATHER_BASE_URL}/forecast"
            params = {"q": location, "appid": config.OPENWEATHER_API_KEY, "units": units}
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    forecast_list = [{
                        "datetime": item["dt_txt"],
                        "temperature": item["main"]["temp"],
                        "description": item["weather"][0]["description"].title(),
                        "humidity": item["main"]["humidity"],
                        "wind_speed": item.get("wind", {}).get("speed", 0),
                    } for item in data["list"][:8]]
                    return {
                        "success": True,
                        "data": {
                            "location": f"{data['city']['name']}, {data['city']['country']}",
                            "forecast": forecast_list,
                            "units": "°C" if units == "metric" else "°F" if units == "imperial" else "K",
                        },
                    }
                error_data = await response.json()
                return {"success": False, "error": f"Forecast API error: {error_data.get('message', 'Unknown error')}"}
    except Exception as e:
        logger.error(f"Error fetching forecast data: {e}")
        return {"success": False, "error": f"Failed to fetch forecast data: {str(e)}"}


# ---------------------------------------------------------------------------
# Gemini function declarations
# ---------------------------------------------------------------------------
functions = [
    {"name": "get_stock_price", "description": "Get real-time stock price, change, and market information",
     "parameters": {"type": "object", "properties": {
         "symbol": {"type": "string", "description": "Stock symbol (e.g., AAPL, TSLA)"}}, "required": ["symbol"]}},
    {"name": "get_crypto_price", "description": "Get real-time cryptocurrency price and market data",
     "parameters": {"type": "object", "properties": {
         "symbol": {"type": "string", "description": "Cryptocurrency symbol (e.g., BTC, ETH)"}}, "required": ["symbol"]}},
    {"name": "get_market_news_summary", "description": "Get latest financial market news and updates",
     "parameters": {"type": "object", "properties": {
         "symbols": {"type": "string", "description": "Optional comma-separated stock symbols for targeted news"},
         "count": {"type": "integer", "description": "Number of news items to return (default 3)"}}}},
    {"name": "analyze_portfolio", "description": "Analyze a portfolio of stocks and cryptocurrencies",
     "parameters": {"type": "object", "properties": {
         "holdings_json": {"type": "string", "description": "JSON string of holdings like {'AAPL': 100, 'BTC': 1.5}"}},
         "required": ["holdings_json"]}},
    {"name": "compare_stocks", "description": "Compare multiple stocks side by side",
     "parameters": {"type": "object", "properties": {
         "symbols": {"type": "string", "description": "Comma-separated stock symbols to compare"}}, "required": ["symbols"]}},
    {"name": "get_current_weather_func", "description": "Get current weather information for a specific location",
     "parameters": {"type": "object", "properties": {
         "location": {"type": "string", "description": "The city name or location to get weather for"},
         "units": {"type": "string", "enum": ["metric", "imperial", "kelvin"], "default": "metric",
                    "description": "Temperature units"}}, "required": ["location"]}},
    {"name": "get_weather_forecast_func", "description": "Get weather forecast for the next 24 hours for a specific location",
     "parameters": {"type": "object", "properties": {
         "location": {"type": "string", "description": "The city name or location to get forecast for"},
         "units": {"type": "string", "enum": ["metric", "imperial", "kelvin"], "default": "metric",
                    "description": "Temperature units"}}, "required": ["location"]}},
]

# Tool object handed to Gemini's GenerateContentConfig(tools=[...])
tools = types.Tool(function_declarations=functions)


async def handle_financial_function_call(function_name: str, args: dict):
    """Single dispatcher for every function-call Gemini can make in this app."""
    try:
        if function_name == "get_stock_price":
            return await get_stock_price(args.get("symbol"))
        elif function_name == "get_crypto_price":
            return await get_crypto_price(args.get("symbol"))
        elif function_name == "get_market_news_summary":
            return await get_market_news_summary(args.get("symbols"), args.get("count", 3))
        elif function_name == "analyze_portfolio":
            return await analyze_portfolio(args.get("holdings_json"))
        elif function_name == "compare_stocks":
            return await compare_stocks(args.get("symbols"))
        elif function_name == "get_current_weather_func":
            return await get_weather_info(location=args.get("location"), units=args.get("units", "metric"))
        elif function_name == "get_weather_forecast_func":
            return await get_weather_forecast(location=args.get("location"), units=args.get("units", "metric"))
        else:
            return f"Unknown function: {function_name}"
    except Exception as e:
        logger.error(f"Error executing {function_name}: {e}")
        return f"Error executing {function_name}: {str(e)}"
