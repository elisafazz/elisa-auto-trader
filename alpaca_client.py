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


def _format_order(order):
    return {
        "id": str(order.id),
        "symbol": order.symbol,
        "side": str(order.side),
        "notional": str(order.notional) if order.notional else None,
        "qty": str(order.qty) if order.qty else None,
        "status": str(order.status),
        "submitted_at": str(order.submitted_at),
    }


def _find_position(client, symbol):
    for p in client.get_all_positions():
        if p.symbol == symbol:
            return p
    return None


def place_order(symbol, side, notional):
    """Place a market order. Uses notional (dollar amount) for fractional shares.

    SELL-safety: Alpaca converts notional SELLs to shares at current bid. When
    the requested notional is within ~2% of position market value, bid drift
    can push implied qty above held qty and the order is rejected with
    insufficient qty (error 40310000). For near-full SELLs we submit qty=held
    directly. Notional rejections below threshold are caught and retried with
    qty=held as a fallback.
    """
    client = get_client()
    order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

    if order_side == OrderSide.SELL:
        position = _find_position(client, symbol)
        if position is not None:
            held_qty = float(position.qty)
            market_value = float(position.market_value)
            if market_value > 0 and notional >= market_value * 0.98:
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=held_qty,
                    side=order_side,
                    time_in_force=TimeInForce.DAY,
                )
                return _format_order(client.submit_order(order_data))

    order_data = MarketOrderRequest(
        symbol=symbol,
        notional=round(notional, 2),
        side=order_side,
        time_in_force=TimeInForce.DAY,
    )
    try:
        return _format_order(client.submit_order(order_data))
    except Exception as e:
        # Fallback: if a SELL is rejected for insufficient qty (sub-threshold
        # bid drift), retry with qty=held. Any other error re-raises.
        if order_side == OrderSide.SELL and "insufficient qty" in str(e).lower():
            position = _find_position(client, symbol)
            if position and float(position.qty) > 0:
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=float(position.qty),
                    side=order_side,
                    time_in_force=TimeInForce.DAY,
                )
                return _format_order(client.submit_order(order_data))
        raise


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


def get_all_orders(limit=500):
    """Fetch all orders with fill details for audit reconciliation."""
    client = get_client()
    request = GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        limit=limit,
    )
    orders = client.get_orders(request)
    return [
        {
            "id": str(o.id),
            "symbol": o.symbol,
            "side": str(o.side),
            "notional": str(o.notional) if o.notional else None,
            "qty": str(o.qty) if o.qty else None,
            "filled_qty": str(o.filled_qty) if o.filled_qty else None,
            "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
            "status": str(o.status),
            "submitted_at": str(o.submitted_at),
        }
        for o in orders
    ]
