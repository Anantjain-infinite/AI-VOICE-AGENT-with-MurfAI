import os
import json
import requests
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import google.generativeai as gena
from google.genai import types
from google import genai
from utils.logger import logger
from config import FINNHUB_API_KEY , GEMINI_API_KEY , OPENWEATHER_API_KEY , ALPHA_VANTAGE_API_KEY

WEATHER_API_KEY = OPENWEATHER_API_KEY
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
        # Multiple API keys for redundancy and rate limiting
        self.alpha_vantage_key = ALPHA_VANTAGE_API_KEY
        self.finnhub_key = FINNHUB_API_KEY
        self.polygon_key = os.getenv("POLYGON_API_KEY")
        self.coinmarketcap_key = os.getenv("COINMARKETCAP_API_KEY")
        self.twelvedata_key = os.getenv("TWELVEDATA_API_KEY")
        
        # Cache for rate limiting
        self.cache = {}
        self.cache_timeout = 60  # seconds
    
    async def get_stock_quote(self, symbol: str) -> Optional[StockData]:
        """Get real-time stock quote"""
        symbol = symbol.upper()
        cache_key = f"stock_{symbol}"
        
        # Check cache
        if self._is_cached(cache_key):
            return self.cache[cache_key]['data']
        
        try:
            # Try Finnhub first (free tier, real-time)
            if self.finnhub_key:
                stock_data = await self._get_finnhub_quote(symbol)
                if stock_data:
                    self._cache_data(cache_key, stock_data)
                    return stock_data
            
            # Fallback to Alpha Vantage
            if self.alpha_vantage_key:
                stock_data = await self._get_alphavantage_quote(symbol)
                if stock_data:
                    self._cache_data(cache_key, stock_data)
                    return stock_data
            
            # Fallback to Polygon.io
            if self.polygon_key:
                stock_data = await self._get_polygon_quote(symbol)
                if stock_data:
                    self._cache_data(cache_key, stock_data)
                    return stock_data
                    
        except Exception as e:
            print(f"Error fetching stock quote for {symbol}: {e}")
            
        return None
    
    async def _get_finnhub_quote(self, symbol: str) -> Optional[StockData]:
        """Get quote from Finnhub API"""
        try:
            async with aiohttp.ClientSession() as session:
                # Get quote
                quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={self.finnhub_key}"
                async with session.get(quote_url) as response:
                    if response.status != 200:
                        return None
                    
                    quote_data = await response.json()
                    
                    if quote_data.get('c') is None:  # Current price
                        return None
                
                # Get company profile for additional data
                profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={self.finnhub_key}"
                async with session.get(profile_url) as profile_response:
                    profile_data = await profile_response.json() if profile_response.status == 200 else {}
                
                return StockData(
                    symbol=symbol,
                    price=quote_data['c'],  # Current price
                    change=quote_data['d'],  # Change
                    change_percent=quote_data['dp'],  # Change percent
                    volume=0,  # Finnhub doesn't provide volume in quote endpoint
                    market_cap=profile_data.get('marketCapitalization'),
                    day_high=quote_data['h'],
                    day_low=quote_data['l'],
                    year_high=None,
                    year_low=None
                )
                
        except Exception as e:
            print(f"Finnhub API error: {e}")
            return None
    
    async def _get_alphavantage_quote(self, symbol: str) -> Optional[StockData]:
        """Get quote from Alpha Vantage API"""
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={self.alpha_vantage_key}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    quote = data.get('Global Quote', {})
                    
                    if not quote:
                        return None
                    
                    return StockData(
                        symbol=symbol,
                        price=float(quote.get('05. price', 0)),
                        change=float(quote.get('09. change', 0)),
                        change_percent=float(quote.get('10. change percent', '0%').replace('%', '')),
                        volume=int(quote.get('06. volume', 0)),
                        day_high=float(quote.get('03. high', 0)),
                        day_low=float(quote.get('04. low', 0)),
                        year_high=float(quote.get('07. latest trading day', 0)),
                        year_low=None
                    )
                    
        except Exception as e:
            print(f"Alpha Vantage API error: {e}")
            return None
    
    async def _get_polygon_quote(self, symbol: str) -> Optional[StockData]:
        """Get quote from Polygon.io API"""
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?adjusted=true&apikey={self.polygon_key}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    results = data.get('results', [])
                    
                    if not results:
                        return None
                    
                    result = results[0]
                    change = result['c'] - result['o']  # Close - Open
                    change_percent = (change / result['o']) * 100
                    
                    return StockData(
                        symbol=symbol,
                        price=result['c'],  # Close price
                        change=change,
                        change_percent=change_percent,
                        volume=result['v'],  # Volume
                        day_high=result['h'],
                        day_low=result['l']
                    )
                    
        except Exception as e:
            print(f"Polygon API error: {e}")
            return None
    
    async def get_crypto_quote(self, symbol: str) -> Optional[CryptoData]:
        """Get cryptocurrency quote"""
        symbol = symbol.upper()
        cache_key = f"crypto_{symbol}"
        
        if self._is_cached(cache_key):
            return self.cache[cache_key]['data']
        
        try:
            if self.coinmarketcap_key:
                crypto_data = await self._get_coinmarketcap_quote(symbol)
                if crypto_data:
                    self._cache_data(cache_key, crypto_data)
                    return crypto_data
                    
        except Exception as e:
            print(f"Error fetching crypto quote for {symbol}: {e}")
            
        return None
    
    async def _get_coinmarketcap_quote(self, symbol: str) -> Optional[CryptoData]:
        """Get crypto quote from CoinMarketCap API"""
        try:
            headers = {
                'X-CMC_PRO_API_KEY': self.coinmarketcap_key,
                'Accept': 'application/json'
            }
            
            url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={symbol}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    crypto_info = data.get('data', {}).get(symbol)
                    
                    if not crypto_info:
                        return None
                    
                    quote = crypto_info['quote']['USD']
                    
                    return CryptoData(
                        symbol=symbol,
                        name=crypto_info['name'],
                        price=quote['price'],
                        change_24h=quote['price'] * (quote['percent_change_24h'] / 100),
                        change_percent_24h=quote['percent_change_24h'],
                        market_cap=quote['market_cap'],
                        volume_24h=quote['volume_24h'],
                        rank=crypto_info['cmc_rank']
                    )
                    
        except Exception as e:
            print(f"CoinMarketCap API error: {e}")
            return None
    
    async def get_market_news(self, symbols: Optional[List[str]] = None, limit: int = 5) -> List[NewsItem]:
        """Get latest market news"""
        cache_key = f"news_{'_'.join(symbols or ['general'])}"
        
        if self._is_cached(cache_key):
            return self.cache[cache_key]['data']
        
        try:
            if self.finnhub_key:
                news_data = await self._get_finnhub_news(symbols, limit)
                if news_data:
                    self._cache_data(cache_key, news_data)
                    return news_data
                    
        except Exception as e:
            print(f"Error fetching market news: {e}")
            
        return []
    
    async def _get_finnhub_news(self, symbols: Optional[List[str]], limit: int) -> List[NewsItem]:
        """Get news from Finnhub API"""
        try:
            news_items = []
            
            async with aiohttp.ClientSession() as session:
                if symbols:
                    # Get company news for specific symbols
                    for symbol in symbols[:3]:  # Limit to avoid rate limits
                        url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from={(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}&to={datetime.now().strftime('%Y-%m-%d')}&token={self.finnhub_key}"
                        
                        async with session.get(url) as response:
                            if response.status == 200:
                                news_data = await response.json()
                                for item in news_data[:limit//len(symbols)]:
                                    news_items.append(NewsItem(
                                        title=item['headline'],
                                        summary=item['summary'][:200] + "..." if len(item['summary']) > 200 else item['summary'],
                                        source=item['source'],
                                        published=datetime.fromtimestamp(item['datetime']),
                                        symbols=[symbol]
                                    ))
                else:
                    # Get general market news
                    url = f"https://finnhub.io/api/v1/news?category=general&token={self.finnhub_key}"
                    
                    async with session.get(url) as response:
                        if response.status == 200:
                            news_data = await response.json()
                            for item in news_data[:limit]:
                                news_items.append(NewsItem(
                                    title=item['headline'],
                                    summary=item['summary'][:200] + "..." if len(item['summary']) > 200 else item['summary'],
                                    source=item['source'],
                                    published=datetime.fromtimestamp(item['datetime'])
                                ))
            
            return sorted(news_items, key=lambda x: x.published, reverse=True)
            
        except Exception as e:
            print(f"Finnhub news API error: {e}")
            return []
    
    async def get_portfolio_analysis(self, holdings: Dict[str, float]) -> Dict[str, Any]:
        """Analyze a portfolio of holdings"""
        portfolio_value = 0
        total_change = 0
        positions = []
        
        for symbol, quantity in holdings.items():
            if symbol.upper() in ['BTC', 'ETH', 'ADA', 'DOT']:  # Common crypto symbols
                quote = await self.get_crypto_quote(symbol)
                if quote:
                    position_value = quote.price * quantity
                    position_change = quote.change_24h * quantity
                    positions.append({
                        'symbol': symbol,
                        'type': 'crypto',
                        'quantity': quantity,
                        'price': quote.price,
                        'value': position_value,
                        'change': position_change,
                        'change_percent': quote.change_percent_24h
                    })
                    portfolio_value += position_value
                    total_change += position_change
            else:
                quote = await self.get_stock_quote(symbol)
                if quote:
                    position_value = quote.price * quantity
                    position_change = quote.change * quantity
                    positions.append({
                        'symbol': symbol,
                        'type': 'stock',
                        'quantity': quantity,
                        'price': quote.price,
                        'value': position_value,
                        'change': position_change,
                        'change_percent': quote.change_percent
                    })
                    portfolio_value += position_value
                    total_change += position_change
        
        portfolio_change_percent = (total_change / (portfolio_value - total_change)) * 100 if portfolio_value != total_change else 0
        
        return {
            'total_value': portfolio_value,
            'total_change': total_change,
            'change_percent': portfolio_change_percent,
            'positions': positions,
            'best_performer': max(positions, key=lambda x: x['change_percent'], default=None),
            'worst_performer': min(positions, key=lambda x: x['change_percent'], default=None)
        }
    
    def _is_cached(self, key: str) -> bool:
        """Check if data is cached and still valid"""
        if key not in self.cache:
            return False
        return (datetime.now() - self.cache[key]['timestamp']).seconds < self.cache_timeout
    
    def _cache_data(self, key: str, data: Any):
        """Cache data with timestamp"""
        self.cache[key] = {
            'data': data,
            'timestamp': datetime.now()
        }

# Initialize financial controller
financial_controller = FinancialMarketsController()

# Function implementations for stocks and crypto
async def get_stock_price(symbol: str) -> str:
    """Get real-time stock price and information."""
    stock_data = await financial_controller.get_stock_quote(symbol)
    
    if not stock_data:
        return f"Sorry sir, I couldn't retrieve data for {symbol.upper()}. The market might be closed or the symbol might be invalid."
    
    change_direction = "📈" if stock_data.change >= 0 else "📉"
    change_text = "up" if stock_data.change >= 0 else "down"
    
    response = f"**{symbol.upper()} - ${stock_data.price:.2f}** {change_direction}\n"
    response += f"Change: ${stock_data.change:+.2f} ({stock_data.change_percent:+.2f}%)\n"
    
    if stock_data.volume:
        response += f"Volume: {stock_data.volume:,}\n"
    if stock_data.market_cap:
        response += f"Market Cap: ${stock_data.market_cap/1000:.1f}B\n"
    if stock_data.day_high and stock_data.day_low:
        response += f"Day Range: ${stock_data.day_low:.2f} - ${stock_data.day_high:.2f}\n"
    
    response += f"\nSir, {symbol.upper()} is {change_text} {abs(stock_data.change_percent):.2f}% today."
    
    return response

async def get_crypto_price(symbol: str) -> str:
    """Get real-time cryptocurrency price and information."""
    crypto_data = await financial_controller.get_crypto_quote(symbol)
    
    if not crypto_data:
        return f"Sorry sir, I couldn't retrieve crypto data for {symbol.upper()}. Please check the symbol."
    
    change_direction = "📈" if crypto_data.change_percent_24h >= 0 else "📉"
    change_text = "up" if crypto_data.change_percent_24h >= 0 else "down"
    
    response = f"**{crypto_data.name} ({symbol.upper()}) - ${crypto_data.price:.2f}** {change_direction}\n"
    response += f"24h Change: ${crypto_data.change_24h:+.2f} ({crypto_data.change_percent_24h:+.2f}%)\n"
    response += f"Market Cap: ${crypto_data.market_cap/1e9:.2f}B\n"
    response += f"24h Volume: ${crypto_data.volume_24h/1e9:.2f}B\n"
    response += f"Rank: #{crypto_data.rank}\n"
    
    response += f"\nSir, {crypto_data.name} is {change_text} {abs(crypto_data.change_percent_24h):.2f}% in the last 24 hours."
    
    return response

async def get_market_news_summary(symbols: Optional[str] = None, count: int = 3) -> str:
    """Get latest financial market news."""
    symbol_list = symbols.split(',') if symbols else None
    if symbol_list:
        symbol_list = [s.strip().upper() for s in symbol_list]
    
    news_items = await financial_controller.get_market_news(symbol_list, count)
    
    if not news_items:
        return "Sorry sir, I couldn't retrieve market news at the moment. The financial networks might be experiencing issues."
    
    response = "**Latest Market News:**\n\n"
    
    for i, news in enumerate(news_items, 1):
        age = datetime.now() - news.published
        if age.days > 0:
            time_str = f"{age.days} days ago"
        elif age.seconds > 3600:
            time_str = f"{age.seconds // 3600} hours ago"
        else:
            time_str = f"{age.seconds // 60} minutes ago"
        
        response += f"**{i}. {news.title}**\n"
        response += f"_{news.source} • {time_str}_\n"
        response += f"{news.summary}\n\n"
    
    response += "Sir, I've compiled the latest market intelligence for your review."
    
    return response

async def analyze_portfolio(holdings_json: str) -> str:
    """Analyze a portfolio of stock and crypto holdings."""
    try:
        holdings = json.loads(holdings_json)
    except json.JSONDecodeError:
        return "Sir, I need the portfolio in JSON format like: {'AAPL': 100, 'TSLA': 50, 'BTC': 1.5}"
    
    analysis = await financial_controller.get_portfolio_analysis(holdings)
    
    if not analysis['positions']:
        return "Sir, I couldn't analyze the portfolio. Please check the symbols and try again."
    
    change_direction = "📈" if analysis['total_change'] >= 0 else "📉"
    performance_text = "gained" if analysis['total_change'] >= 0 else "lost"
    
    response = f"**Portfolio Analysis** {change_direction}\n\n"
    response += f"**Total Value:** ${analysis['total_value']:,.2f}\n"
    response += f"**Today's Change:** ${analysis['total_change']:+,.2f} ({analysis['change_percent']:+.2f}%)\n\n"
    
    response += "**Top Holdings:**\n"
    sorted_positions = sorted(analysis['positions'], key=lambda x: x['value'], reverse=True)
    
    for pos in sorted_positions[:5]:  # Top 5 holdings
        pos_direction = "📈" if pos['change'] >= 0 else "📉"
        response += f"• **{pos['symbol']}**: ${pos['value']:,.2f} ({pos['change_percent']:+.2f}%) {pos_direction}\n"
    
    if analysis['best_performer']:
        best = analysis['best_performer']
        response += f"\n**Best Performer:** {best['symbol']} ({best['change_percent']:+.2f}%)\n"
    
    if analysis['worst_performer']:
        worst = analysis['worst_performer']
        response += f"**Worst Performer:** {worst['symbol']} ({worst['change_percent']:+.2f}%)\n"
    
    response += f"\nSir, your portfolio has {performance_text} ${abs(analysis['total_change']):,.2f} today."
    
    return response

async def compare_stocks(symbols: str) -> str:
    """Compare multiple stocks side by side."""
    symbol_list = [s.strip().upper() for s in symbols.split(',')]
    
    if len(symbol_list) < 2:
        return "Sir, I need at least two symbols to compare. Try: 'AAPL,MSFT,GOOGL'"
    
    comparisons = []
    
    for symbol in symbol_list[:5]:  # Limit to 5 stocks
        stock_data = await financial_controller.get_stock_quote(symbol)
        if stock_data:
            comparisons.append(stock_data)
    
    if not comparisons:
        return "Sir, I couldn't retrieve data for any of those symbols."
    
    response = "**Stock Comparison:**\n\n"
    
    # Sort by performance
    comparisons.sort(key=lambda x: x.change_percent, reverse=True)
    
    for i, stock in enumerate(comparisons, 1):
        direction = "📈" if stock.change >= 0 else "📉"
        response += f"**{i}. {stock.symbol}** - ${stock.price:.2f} {direction}\n"
        response += f"   Change: ${stock.change:+.2f} ({stock.change_percent:+.2f}%)\n"
        if stock.market_cap:
            response += f"   Market Cap: ${stock.market_cap/1000:.1f}B\n"
        response += "\n"
    
    best = comparisons[0]
    worst = comparisons[-1]
    
    response += f"Sir, **{best.symbol}** is leading with {best.change_percent:+.2f}%, while **{worst.symbol}** is trailing at {worst.change_percent:+.2f}%."
    
    return response

#function implementations for weather
async def get_weather_info(location: str, units: str = "metric") -> dict:
    """
    Get current weather information for a given location.
    
    Args:
        location: City name or coordinates
        units: Temperature units (metric, imperial, kelvin)
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Current weather endpoint
            url = f"{WEATHER_BASE_URL}/weather"
            params = {
                "q": location,
                "appid": WEATHER_API_KEY,
                "units": units
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    weather_info = {
                        "location": f"{data['name']}, {data['sys']['country']}",
                        "temperature": data['main']['temp'],
                        "feels_like": data['main']['feels_like'],
                        "humidity": data['main']['humidity'],
                        "pressure": data['main']['pressure'],
                        "description": data['weather'][0]['description'].title(),
                        "wind_speed": data.get('wind', {}).get('speed', 0),
                        "visibility": data.get('visibility', 0) / 1000,  # Convert to km
                        "units": "°C" if units == "metric" else "°F" if units == "imperial" else "K"
                    }
                    
                    return {
                        "success": True,
                        "data": weather_info
                    }
                else:
                    error_data = await response.json()
                    return {
                        "success": False,
                        "error": f"Weather API error: {error_data.get('message', 'Unknown error')}"
                    }
                    
    except Exception as e:
        logger.error(f"Error fetching weather data: {e}")
        return {
            "success": False,
            "error": f"Failed to fetch weather data: {str(e)}"
        }

async def get_weather_forecast(location: str, units: str = "metric") -> dict:
    """
    Get 5-day weather forecast for a given location.
    
    Args:
        location: City name or coordinates
        units: Temperature units (metric, imperial, kelvin)
    """
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{WEATHER_BASE_URL}/forecast"
            params = {
                "q": location,
                "appid": WEATHER_API_KEY,
                "units": units
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    forecast_list = []
                    for item in data['list'][:8]:  # Get next 24 hours (8 x 3-hour intervals)
                        forecast_list.append({
                            "datetime": item['dt_txt'],
                            "temperature": item['main']['temp'],
                            "description": item['weather'][0]['description'].title(),
                            "humidity": item['main']['humidity'],
                            "wind_speed": item.get('wind', {}).get('speed', 0)
                        })
                    
                    return {
                        "success": True,
                        "data": {
                            "location": f"{data['city']['name']}, {data['city']['country']}",
                            "forecast": forecast_list,
                            "units": "°C" if units == "metric" else "°F" if units == "imperial" else "K"
                        }
                    }
                else:
                    error_data = await response.json()
                    return {
                        "success": False,
                        "error": f"Forecast API error: {error_data.get('message', 'Unknown error')}"
                    }
                    
    except Exception as e:
        logger.error(f"Error fetching forecast data: {e}")
        return {
            "success": False,
            "error": f"Failed to fetch forecast data: {str(e)}"
        }

# Define weather functions for Gemini function calling
def get_current_weather_func(location: str, units: str = "metric") -> str:
    """
    Get current weather information for a specific location.
    
    Args:
        location: The city name or location to get weather for
        units: Temperature units (metric for Celsius, imperial for Fahrenheit, kelvin for Kelvin)
    
    Returns:
        JSON string with weather information
    """
    # This is a placeholder - actual implementation will be handled by execute_function_call
    return f"Getting current weather for {location} in {units} units"

def get_weather_forecast_func(location: str, units: str = "metric") -> str:
    """
    Get weather forecast for the next 24 hours for a specific location.
    
    Args:
        location: The city name or location to get forecast for
        units: Temperature units (metric for Celsius, imperial for Fahrenheit, kelvin for Kelvin)
    
    Returns:
        JSON string with forecast information
    """
    # This is a placeholder - actual implementation will be handled by execute_function_call
    return f"Getting weather forecast for {location} in {units} units"



# Function declarations for Gemini

functions = [
    {
        "name": "get_stock_price",
        "description": "Get real-time stock price, change, and market information",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol (e.g., AAPL, TSLA)"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_crypto_price", 
        "description": "Get real-time cryptocurrency price and market data",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Cryptocurrency symbol (e.g., BTC, ETH)"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_market_news_summary",
        "description": "Get latest financial market news and updates", 
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "string",
                    "description": "Optional comma-separated stock symbols for targeted news"
                },
                "count": {
                    "type": "integer", 
                    "description": "Number of news items to return (default 3)"
                }
            }
        }
    },
    {
        "name": "analyze_portfolio",
        "description": "Analyze a portfolio of stocks and cryptocurrencies",
        "parameters": {
            "type": "object",
            "properties": {
                "holdings_json": {
                    "type": "string",
                    "description": "JSON string of holdings like {'AAPL': 100, 'BTC': 1.5}"
                }
            },
            "required": ["holdings_json"]
        }
    },
    {
        "name": "compare_stocks",
        "description": "Compare multiple stocks side by side",
        "parameters": {
            "type": "object", 
            "properties": {
                "symbols": {
                    "type": "string",
                    "description": "Comma-separated stock symbols to compare"
                }
            },
            "required": ["symbols"]
        }
    },
    {
        "name": "get_current_weather_func",
        "description": "Get current weather information for a specific location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city name or location to get weather for"
                },
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial", "kelvin"],
                    "description": "Temperature units (metric for Celsius, imperial for Fahrenheit, kelvin for Kelvin)",
                    "default": "metric"
                }
            },
            "required": ["location"]
        }
    },
    {
        "name": "get_weather_forecast_func",
        "description": "Get weather forecast for the next 24 hours for a specific location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city name or location to get forecast for"
                },
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial", "kelvin"],
                    "description": "Temperature units (metric for Celsius, imperial for Fahrenheit, kelvin for Kelvin)",
                    "default": "metric"
                }
            },
            "required": ["location"]
        }
    }
]


   
# Tool for Gemini
tools =types.Tool(function_declarations=functions)


#fuction handler

async def execute_function_call(function_name: str, arguments: dict) -> dict:
        """Execute the requested function call and return results"""
        try:
            if function_name == "get_current_weather_func":
                return await get_weather_info(
                    location=arguments.get("location"),
                    units=arguments.get("units", "metric")
                )
            elif function_name == "get_weather_forecast_func":
                return await get_weather_forecast(
                    location=arguments.get("location"),
                    units=arguments.get("units", "metric")
                )
            else:
                return {
                    "success": False,
                    "error": f"Unknown function: {function_name}"
                }
        except Exception as e:
            logger.error(f"Error executing function {function_name}: {e}")
            return {
                "success": False,
                "error": f"Function execution failed: {str(e)}"
            }



finance_map = {
    "get_stock_price": get_stock_price,
    "get_crypto_price": get_crypto_price,
    "get_market_news_summary": get_market_news_summary,
    "analyze_portfolio": analyze_portfolio,
    "compare_stocks": compare_stocks,
}
# Function handler
async def handle_financial_function_call(function, args):
    """Handle financial function calls from Gemini"""
    function_name = function
    args = args
    
    try:
        if function_name == "get_stock_price":
            result = await get_stock_price(args.get("symbol"))
        elif function_name == "get_crypto_price":
            result = await get_crypto_price(args.get("symbol"))
        elif function_name == "get_market_news_summary":
            result = await get_market_news_summary(
                args.get("symbols"), 
                args.get("count", 3)
            )
        elif function_name == "analyze_portfolio":
            result = await analyze_portfolio(args.get("holdings_json"))
        elif function_name == "compare_stocks":
            result = await compare_stocks(args.get("symbols"))

            
        elif function_name == "get_current_weather_func":
                result= await get_weather_info(
                    location=args.get("location"),
                    units=args.get("units", "metric")
                )
        elif function_name == "get_weather_forecast_func":
                result= await get_weather_forecast(
                    location=args.get("location"),
                    units=args.get("units", "metric")
                )
        
        else:
            result = f"Unknown  function: {function_name}"
        
        return result
        
    except Exception as e:
        return f"Error executing {function_name}: {str(e)}"

# Updated chat configuration
def create_financial_markets_chat(conversation_text):
    """Create Gemini chat with financial markets capabilities"""
    gemini_client = genai.Client()
    
    chat = gemini_client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction="""You are Tony, an AI persona inspired by Tony Stark with advanced financial market analysis capabilities!
            
Key personality traits:
- Always address the user as "Sir"
- Respond with wit, confidence, and occasional sarcasm
- Act like a genius investor and tech mogul
- Use financial terminology confidently
- Make clever references to market trends, science, and technology
- Never be robotic—always sharp, playful, and brilliant

Financial Market Capabilities:
- Real-time stock prices and market data
- Cryptocurrency tracking and analysis
- Portfolio performance analysis
- Latest financial news and market sentiment
- Stock comparisons and investment insights

Weather Intelligence Capabilities:
- Provide real-time weather updates for any city
- Deliver witty, investor-style commentary on the weather
- Relate weather patterns to lifestyle, business, or markets (e.g., "Rainy in New York, Sir. Bad day for umbrellas, but a bullish day for coffee shops.")
- Use the same Tony Stark flair and confidence when reporting weather

General Knowledge & Reasoning Capabilities:
- Answer any general knowledge, science, history, or tech question
- Provide logical explanations with a mix of wit and brilliance
- Always keep answers confident, clever, and engaging
- Use humor and sarcasm when appropriate (Tony Stark style)
- Relate insights back to innovation, intelligence, or strategy

Communication Style:
- "Sir, the markets are looking..."
- "Based on current market conditions..."
- "Your portfolio performance indicates..."
- "The financial data suggests..."
- "Sir, according to my atmospheric algorithms..."
- "Sir, based on universal knowledge matrices..."
- Reference Tony Stark's wealth, investment acumen, tech genius, and now his encyclopedic intelligence
- Use terms like "market intelligence," "financial algorithms," "investment matrices," "atmospheric data streams," and "knowledge engines"

Always provide actionable insights while maintaining the Tony Stark personality.
"""
,
            tools=[tools],
            
        )
    )

    response = chat.send_message_stream(conversation_text)
    
    return response

