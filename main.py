from dotenv import load_dotenv
import os
load_dotenv()

import time
import uuid
import logging
from typing import Optional
from fastapi import FastAPI, Query, Header, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_mcp import FastApiMCP
from src.common.auth import validate_jwt
from src.common.policy import resolve_tier, REASON_CODES
from src.common.rate_limiter import check_rate_limit
from src.common.audit import emit_audit_event
from src.common.fastapi_util import success, exception_handler, BaseResponse
from src.api.ticker import get_ticker_info, get_ticker_prices, get_ticker_news, get_income_stmt, get_balance_sheet, get_cash_flow, get_insider_transactions, get_insider_roster_holders, get_insider_purchases, get_financial_metrics, lookup_ticker, get_financial_items
from src.models.ticker_info_model import TickerInfo
from src.models.ticker_prices_model import TickerPriceItem
from src.models.ticker_news_model import NewsItem
from src.models.ticker_income_stmt_model import IncomeStmtItem
from src.models.ticker_balance_sheet_model import BalanceSheetItem
from src.models.ticker_cash_flow_model import CashFlowItem
from src.models.ticker_insider_transactions_model import InsiderTransactionItem
from src.models.ticker_insider_roster_holders_model import InsiderRosterHolderItem
from src.models.ticker_insider_purchases_model import InsiderPurchaseItem
from src.models.ticker_financial_metrics_model import FinancialMetricItem
from src.models.ticker_financial_items_model import FinancialItem
from src.models.ticker_lookup_model import LookupItem
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(levelname)s %(message)s",
)

async def authenticated_claims(
        request: Request = None,
        authorization: str = Header(None),
        authentication: str = Header(None),
        x_api_key: str = Header(None),
        api_key: str = Header(None),
        x_token: str = Header(None),
        token: str = Header(None)) -> dict:
    """Extract Bearer token from any accepted header, validate as HS256 JWT,
    enforce rate limit, and return validated claims dict.

    No path is bypassed — /mcp and /sse routes go through the same check.
    Fails closed: any validation failure raises HTTPException before returning.
    Stores actor_id and role on request.state so the HTTPException handler can
    emit audit events for throttle and auth-failure paths.

    request is optional (defaults to None) so the function can be called
    directly in tests without a FastAPI Request object.
    """
    auth_str = authorization or authentication or x_api_key or api_key or x_token or token
    if not auth_str:
        # Store sentinel before raising so the exception handler can read it
        if request is not None:
            request.state.actor_id = "ANONYMOUS"
            request.state.actor_role = None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason_code": "TOKEN_MISSING", "message": "Authorization token required"},
        )
    # Accept "Bearer <token>" or a bare token string
    parts = auth_str.split(" ", 1)
    raw_token = parts[1] if len(parts) == 2 and parts[0] == "Bearer" else auth_str
    claims = validate_jwt(raw_token)
    # Store validated identity on request.state before rate-limit check so
    # the HTTPException handler emits the correct actor_id on throttle.
    if request is not None:
        request.state.actor_id = claims["sub"]
        request.state.actor_role = claims["role"]
    check_rate_limit(claims["sub"], claims["role"])
    return claims


app = FastAPI(
    title="Aostock financial data API",
    version="1.0",
    description=(
        "Aostock financial data API. "
        "All endpoints require a valid JWT in the Authorization: Bearer <token> header. "
        "Data tier (REALTIME or DELAYED) is determined server-side from the validated identity."
    ),
    dependencies=[Depends(authenticated_claims)],
)

# Add CORS middleware for remote access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Stamp a UUID correlation ID on every request for audit tracing."""
    request.state.request_id = str(uuid.uuid4())
    request.state.start_time = time.monotonic()
    return await call_next(request)


# Map HTTP status + reason_code combinations to audit decision/reason_code pairs.
# Used by the HTTPException handler to emit structured audit events.
_HTTP_AUDIT_MAP: dict[str, tuple[str, str]] = {
    "TOKEN_MISSING":          ("DENY",     "TOKEN_MISSING"),
    "TOKEN_EXPIRED":          ("DENY",     "TOKEN_EXPIRED"),
    "TOKEN_INVALID":          ("DENY",     "TOKEN_INVALID"),
    "TOKEN_AUDIENCE_INVALID": ("DENY",     "TOKEN_AUDIENCE_INVALID"),
    "POLICY_UNAVAILABLE":     ("DENY",     "POLICY_UNAVAILABLE"),
    "ENTITLEMENT_MISSING":    ("DENY",     "ENTITLEMENT_MISSING"),
    "RATE_LIMIT_EXCEEDED":    ("THROTTLE", "RATE_LIMIT_EXCEEDED"),
}


@app.exception_handler(HTTPException)
async def http_exception_audit_handler(request: Request, exc: HTTPException):
    """Intercept all HTTPExceptions to emit audit events before returning.

    This covers the paths where the route handler body never runs:
      - Token validation failures (TOKEN_EXPIRED, TOKEN_AUDIENCE_INVALID, etc.)
      - Rate-limit throttles (RATE_LIMIT_EXCEEDED)
      - Entitlement denies that re-raise HTTPException from inside the route body
        (the route already emitted its own event; we skip double-emitting those)

    To avoid double-emitting on DENY paths that already called emit_audit_event
    inside the route handler (e.g. ENTITLEMENT_MISSING), we only emit here for
    exceptions that originated before or outside the handler body — detected via
    the absence of request.state.audit_emitted.
    """
    latency_ms = (time.monotonic() - getattr(request.state, "start_time", time.monotonic())) * 1000
    channel = "MCP" if request.url.path.startswith(("/mcp", "/sse")) else "REST"
    actor_id = getattr(request.state, "actor_id", "ANONYMOUS")

    # Only emit if the route handler has not already emitted an audit event
    if not getattr(request.state, "audit_emitted", False):
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        reason_code = detail.get("reason_code", "POLICY_UNAVAILABLE")
        decision, mapped_reason = _HTTP_AUDIT_MAP.get(
            reason_code, ("DENY", "POLICY_UNAVAILABLE")
        )
        emit_audit_event(
            request_id=getattr(request.state, "request_id", "UNKNOWN"),
            actor_id=actor_id,
            channel=channel,
            action="GET_QUOTE",
            resource=request.url.path,
            decision=decision,
            reason_code=mapped_reason,
            latency_ms=latency_ms,
        )

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, e: Exception):
    """Catch-all for unexpected errors (not HTTPException). Always fails closed."""
    latency_ms = (time.monotonic() - getattr(request.state, "start_time", time.monotonic())) * 1000
    channel = "MCP" if request.url.path.startswith(("/mcp", "/sse")) else "REST"
    actor_id = getattr(request.state, "actor_id", "UNKNOWN")
    emit_audit_event(
        request_id=getattr(request.state, "request_id", "UNKNOWN"),
        actor_id=actor_id,
        channel=channel,
        action="UNKNOWN",
        resource=request.url.path,
        decision="DENY",
        reason_code="POLICY_UNAVAILABLE",
        latency_ms=latency_ms,
    )
    return await exception_handler(request, e)


@app.get("/api/v1/test", operation_id="get_test", tags=["Test"], summary="Test", description="Test endpoint", response_model=BaseResponse)
async def test():
    """Test endpoint that returns a simple message."""
    return success("Hello World")


@app.get("/api/v1/ticker/info", operation_id="get_ticker_info", tags=["Ticker"], summary="Ticker Info",
description="Get ticker info",
response_model=BaseResponse[TickerInfo])
async def ticker_info(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS")):
    """Get information about a specific ticker symbol.

    Args:
        symbol: The ticker symbol to get information for (e.g., AAPL, 601398.SS)

    Returns:
        Ticker information including company name, sector, industry, etc.
    """
    data = get_ticker_info(symbol)
    return success(data)


@app.get("/api/v1/ticker/prices", operation_id="get_ticker_prices", tags=["Ticker"], summary="Ticker Prices",
    description="Get ticker prices. Data tier (REALTIME or DELAYED) is determined server-side from the caller's identity and entitlement.",
    response_model=BaseResponse[list[TickerPriceItem]])
async def ticker_prices(
        request: Request,
        claims: dict = Depends(authenticated_claims),
        symbol: str = Query(..., description="Ticker symbol, eg: AURORA, NEXUS, SYN1"),
        interval: str = Query(..., description="Time interval, eg: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo"),
        start_date: str = Query(..., description="Start date, eg: 2026-08-01"),
        end_date: str = Query(..., description="End date, eg: 2026-08-04")):
    """Get historical prices for a specific ticker symbol.

    The data tier (REALTIME or DELAYED) is resolved server-side from the caller's
    validated JWT claims. REALTIME: quote_as_of = served_at.
    DELAYED: quote_as_of = served_at minus 15 minutes.

    Args:
        symbol: The ticker symbol (synthetic instruments: AURORA, NEXUS, OASIS, FALCON,
                CEDAR, HORIZON, SYN1, SYN2, SYN3)
        interval: Time interval for the data (e.g., 1d)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        List of ticker price items annotated with data_tier and quote_as_of.
    """
    t_start = getattr(request.state, "start_time", time.monotonic())
    channel = "MCP" if request.url.path.startswith(("/mcp", "/sse")) else "REST"
    actor_id = claims["sub"]
    request_id = getattr(request.state, "request_id", "UNKNOWN")

    decision, tier = resolve_tier(claims)

    if decision == "DENY":
        emit_audit_event(
            request_id=request_id,
            actor_id=actor_id,
            channel=channel,
            action="GET_QUOTE",
            resource=symbol,
            decision="DENY",
            reason_code=REASON_CODES["NONE"],
            latency_ms=(time.monotonic() - t_start) * 1000,
        )
        # Mark audit as emitted so the HTTPException handler does not double-emit.
        request.state.audit_emitted = True
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_code": "ENTITLEMENT_MISSING", "message": "Entitlement required for market data access"},
        )

    data = get_ticker_prices(symbol, interval, start_date, end_date, tier)

    emit_audit_event(
        request_id=request_id,
        actor_id=actor_id,
        channel=channel,
        action="GET_QUOTE",
        resource=symbol,
        decision="ALLOW",
        reason_code=REASON_CODES[tier],
        latency_ms=(time.monotonic() - t_start) * 1000,
    )
    return success(data)


@app.get("/api/v1/ticker/news", operation_id="get_ticker_news", tags=["Ticker"], summary="Ticker News",
description="Get ticker news",
response_model=BaseResponse[list[NewsItem]])
async def ticker_news(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS"),
    count: Optional[int] = Query(default=10, description="Number of news, eg: 10")):
    """Get recent news articles for a specific ticker symbol.

    Args:
        symbol: The ticker symbol to get news for (e.g., AAPL, 601398.SS)
        count: Number of news articles to retrieve (default: 10)

    Returns:
        List of news items related to the specified ticker
    """
    data = get_ticker_news(symbol, count)
    return success(data)


@app.get("/api/v1/ticker/income_stmt", operation_id="get_ticker_income_stmt", tags=["Ticker"], summary="Ticker Income Statement",
description="Get ticker income statement",
response_model=BaseResponse[list[IncomeStmtItem]])
async def ticker_income_stmt(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS"),
    freq: str = Query(default='yearly', description="Income statement frequency, eg: yearly, quarterly or trailing")):
    """Get income statement data for a specific ticker symbol.

    Args:
        symbol: The ticker symbol to get income statement for (e.g., AAPL, 601398.SS)
        freq: Frequency of data - 'yearly', 'quarterly', or 'trailing' (default: yearly)

    Returns:
        List of income statement items for the specified ticker
    """
    data = get_income_stmt(symbol, freq)
    return success(data)


@app.get("/api/v1/ticker/balance_sheet", operation_id="get_ticker_balance_sheet", tags=["Ticker"], summary="Ticker Balance Sheet",
description="Get ticker balance sheet",
response_model=BaseResponse[list[BalanceSheetItem]])
async def ticker_balance_sheet(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS"),
    freq: str = Query(default='yearly', description="Balance sheet frequency, eg: yearly, quarterly or trailing")):
    """Get balance sheet data for a specific ticker symbol.

    Args:
        symbol: The ticker symbol to get balance sheet for (e.g., AAPL, 601398.SS)
        freq: Frequency of data - 'yearly', 'quarterly', or 'trailing' (default: yearly)

    Returns:
        List of balance sheet items for the specified ticker
    """
    data = get_balance_sheet(symbol, freq)
    return success(data)


@app.get("/api/v1/ticker/cash_flow", operation_id="get_ticker_cash_flow", tags=["Ticker"], summary="Ticker Cash Flow",
description="Get ticker cash flow",
response_model=BaseResponse[list[CashFlowItem]])
async def ticker_cash_flow(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS"),
    freq: str = Query(default='yearly', description="Cash flow frequency, eg: yearly, quarterly or trailing")):
    """Get cash flow data for a specific ticker symbol.

    Args:
        symbol: The ticker symbol to get cash flow for (e.g., AAPL, 601398.SS)
        freq: Frequency of data - 'yearly', 'quarterly', or 'trailing' (default: yearly)

    Returns:
        List of cash flow items for the specified ticker
    """
    data = get_cash_flow(symbol, freq)
    return success(data)


@app.get("/api/v1/ticker/insider_transactions", operation_id="get_ticker_insider_transactions", tags=["Ticker"], summary="Ticker Insider Transactions",
description="Get ticker insider transactions",
response_model=BaseResponse[list[InsiderTransactionItem]])
async def ticker_insider_transactions(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS")):
    """Get insider transactions data for a specific ticker symbol.

    Args:
        symbol: The ticker symbol to get insider transactions for (e.g., AAPL, 601398.SS)

    Returns:
        List of insider transaction items for the specified ticker
    """
    data = get_insider_transactions(symbol)
    return success(data)

@app.get("/api/v1/ticker/insider_roster_holders", operation_id="get_ticker_insider_roster_holders", tags=["Ticker"], summary="Ticker Insider Roster Holders",
description="Get ticker insider roster holders",
response_model=BaseResponse[list[InsiderRosterHolderItem]])
async def ticker_insider_roster_holders(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS")):
    """Get insider roster holders data for a specific ticker symbol.

    Args:
        symbol: The ticker symbol to get insider roster holders for (e.g., AAPL, 601398.SS)

    Returns:
        List of insider roster holder items for the specified ticker
    """
    data = get_insider_roster_holders(symbol)
    return success(data)

@app.get("/api/v1/ticker/insider_purchases", operation_id="get_ticker_insider_purchases", tags=["Ticker"], summary="Ticker Insider Purchases",
description="Get ticker insider purchases",
response_model=BaseResponse[list[InsiderPurchaseItem]])
async def ticker_insider_purchases(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS")):
    """Get insider purchases data for a specific ticker symbol.

    Args:
        symbol: The ticker symbol to get insider purchases for (e.g., AAPL, 601398.SS)

    Returns:
        List of insider purchase items for the specified ticker
    """
    data = get_insider_purchases(symbol)
    return success(data)


@app.get("/api/v1/ticker/financial_metrics", operation_id="get_ticker_financial_metrics", tags=["Ticker"], summary="Ticker Financial Metrics",
description="Get ticker financial metrics",
response_model=BaseResponse[list[FinancialMetricItem]])
async def ticker_financial_metrics(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS"), freq: Optional[str] = Query(default='yearly', description="Financial metrics frequency, eg: yearly, quarterly")):
    """Get financial metrics data for a specific ticker symbol.

    Args:
        symbol: The ticker symbol to get financial metrics for (e.g., AAPL, 601398.SS)
        freq: Frequency of data - 'yearly' or 'quarterly' (default: yearly)

    Returns:
        List of financial metric items for the specified ticker
    """
    data = get_financial_metrics(symbol, freq)
    return success(data)


@app.get("/api/v1/ticker/financial_items", operation_id="get_ticker_financial_items", tags=["Ticker"], summary="Ticker Financial Items",
description="Get ticker financial items",
response_model=BaseResponse[list[FinancialItem]])
async def ticker_financial_items(symbol: str = Query(..., description="Ticker symbols, eg: AAPL, 601398.SS"), items: Optional[str] = Query(default=None, description="Financial items, eg: revenue_growth,market_cap"), freq: Optional[str] = Query(default='yearly', description="Financial items frequency, eg: yearly, quarterly")):
    """Get specific financial items data for a ticker symbol.

    Args:
        symbol: The ticker symbol to get financial items for (e.g., AAPL, 601398.SS)
        items: Comma-separated list of specific financial items to retrieve
        freq: Frequency of data - 'yearly' or 'quarterly' (default: yearly)

    Returns:
        List of financial items for the specified ticker
    """
    if items is not None:
        items = items.split(',')
    data = get_financial_items(symbol, items, freq)
    return success(data)


@app.get("/api/v1/ticker/lookup", operation_id="get_ticker_lookup", tags=["Ticker"], summary="Ticker lookup",
description="lookup ticker",
response_model=BaseResponse[list[LookupItem]])
async def ticker_lookup(query: str = Query(..., description="lookup query, eg: AAPL")):
    """Look up ticker symbols based on a search query.

    Args:
        query: The search query to look up ticker symbols for (e.g., AAPL)

    Returns:
        List of matching ticker symbols and company names
    """
    data = lookup_ticker(query)
    return success(data)


mcp = FastApiMCP(app, describe_all_responses=True, headers=["authorization", "authentication", "x-api-key", "api-key", "x-token", "token"])
mcp.mount_http()
mcp.mount_sse()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PM2_SERVE_PORT", 8000))
    print(f"Starting FastAPI app with MCP on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
