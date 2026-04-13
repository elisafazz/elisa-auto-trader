from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import StockBarsRequest, NewsRequest
from alpaca.data.timeframe import TimeFrame
import config


def get_client():
    return TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=config.PAPER_TRADING,
    )


def get_clock():
    client = get_client()
    clock = client.get_clock()
    return {
        "is_open": clock.is_open,
        "next_open": str(clock.next_open),
        "next_close": str(clock.next_close),
    }


def get_account():
    client = get_client()
    acct = client.get_account()
    return {
        "cash": float(acct.cash),
        "portfolio_value": float(acct.portfolio_value),
        "buying_power": float(acct.buying_power),
        "equity": float(acct.equity),
        "status": acct.status,
    }


def get_positions():
    client = get_client()
    positions = client.get_all_positions()
    return [
        {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "market_value": float(p.market_value),
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_plpc": float(p.unrealized_plpc),
        }
        for p in positions
    ]


def place_order(symbol, side, notional):
    """Place a market order using dollar amount (notional) for fractional share support."""
    client = get_client()
    order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
    order_data = MarketOrderRequest(
        symbol=symbol,
        notional=round(notional, 2),
        side=order_side,
        time_in_force=TimeInForce.DAY,
    )
    order = client.submit_order(order_data)
    return {
        "id": str(order.id),
        "symbol": order.symbol,
        "side": str(order.side),
        "notional": str(order.notional),
        "status": str(order.status),
        "submitted_at": str(order.submitted_at),
    }


def get_data_client():
    return StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
    )


def get_bars(symbols, days=10):
    """Fetch daily bars for a list of symbols over the last N trading days."""
    client = get_data_client()
    end = datetime.now()
    start = end - timedelta(days=days + 5)  # buffer for weekends
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        limit=days,
    )
    bars = client.get_stock_bars(request)
    result = {}
    for symbol in symbols:
        symbol_bars = bars.data.get(symbol, [])
        result[symbol] = [
            {
                "date": str(b.timestamp.date()),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": int(b.volume),
            }
            for b in symbol_bars
        ]
    return result


def get_news(symbols=None, limit=10):
    """Fetch recent market news, optionally filtered by symbols."""
    client = NewsClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
    )
    symbol_str = ",".join(symbols) if symbols else None
    request = NewsRequest(
        symbols=symbol_str,
        start=datetime.now() - timedelta(days=2),
        end=datetime.now(),
        limit=limit,
        include_content=False,
    )
    news_set = client.get_news(request)
    return [
        {
            "headline": n.headline,
            "source": n.source,
            "symbols": [s for s in (n.symbols or [])],
            "summary": n.summary or "",
            "created_at": str(n.created_at),
        }
        for n in news_set.data.get("news", [])
    ]


def get_recent_orders(limit=10):
    client = get_client()
    request = GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        limit=limit,
    )
    orders = client.get_orders(request)
    return [
        {
            "symbol": o.symbol,
            "side": str(o.side),
            "notional": str(o.notional) if o.notional else None,
            "qty": str(o.qty) if o.qty else None,
            "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
            "status": str(o.status),
            "submitted_at": str(o.submitted_at),
        }
        for o in orders
    ]
