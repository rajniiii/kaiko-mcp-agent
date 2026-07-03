"""
FE524 HW12 – Kaiko Reference Data MCP Server (Basic Tier)

Exposes Kaiko basic-tier REST endpoints as MCP tools:
    get_exchanges   → GET /v1/exchanges
    get_instruments → GET /v1/instruments  (filtered — always use filters!)
    get_assets      → GET /v1/assets       (capped at 100 rows)
    search_assets   → searches assets by name keyword

"""

import json
import os

import httpx
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://reference-data-api.kaiko.io/v1"
API_KEY  = os.environ.get("KAIKO_API_KEY", "")

# Hard cap: never send more than this many rows to the LLM in one call.
# The instruments endpoint alone has ~500k rows — without a cap the
# context window overflows immediately.
MAX_ROWS = 100

mcp = FastMCP("Kaiko Reference Data")


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _kaiko_get(path: str, params: dict | None = None) -> str:
    """
    GET one page from a Kaiko reference-data endpoint.
    Results are capped at MAX_ROWS to stay within the LLM context window.
    Returns a JSON string (FastMCP sends it back as text content).
    """
    headers = {"Accept": "application/json"}
    if API_KEY:
        headers["X-Api-Key"] = API_KEY

    p = dict(params or {})
    p.setdefault("page_size", MAX_ROWS)

    resp = httpx.get(f"{BASE_URL}{path}", headers=headers, params=p, timeout=20)
    resp.raise_for_status()
    body = resp.json()

    data = body.get("data", [])
    if not isinstance(data, list):
        return json.dumps(body)

    truncated = data[:MAX_ROWS]
    return json.dumps({
        "returned": len(truncated),
        "note": "Use filters to narrow results further." if len(data) >= MAX_ROWS else "",
        "data": truncated,
    })


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool
def get_exchanges() -> str:
    """
    Return all exchanges supported by Kaiko with their code, name, and
    legacy slug.

    Use this to find an exchange's Kaiko code before calling get_instruments.
    e.g. Coinbase = "cbse", Binance = "bnce", Deribit = "drbt".
    Also answers: "what exchanges does Kaiko cover?" or
    "what derivatives exchanges are available?".
    """
    return _kaiko_get("/exchanges")


@mcp.tool
def get_instruments(
    exchange_code: str = "",
    base_asset: str = "",
    quote_asset: str = "",
    instrument_class: str = "",
) -> str:
    """
    Return trading instruments (exchange pairs) with optional filters.
    ALWAYS provide at least one filter – unfiltered calls return 500k+ rows.

    Each record includes:
      - exchange_code          : which exchange
      - class                  : spot / future / perpetual-future / option
      - trade_start_timestamp  : first trade recorded by Kaiko (ISO 8601)
      - trade_end_timestamp    : last trade recorded; null = still active

    Parameters
    ----------
    exchange_code    : Kaiko exchange code, e.g. "cbse" (Coinbase).
                       Call get_exchanges() first if unsure of the code.
    base_asset       : Base asset code, e.g. "btc", "eth", "syn" (Synapse).
    quote_asset      : Quote asset code, e.g. "usd", "usdt".
    instrument_class : "spot", "future", "perpetual-future", "option", or ""

    Examples
    --------
    "When was Synapse last traded on Coinbase?"
        → get_instruments(exchange_code="cbse", base_asset="syn")
    "Is ETH/USDT trading on Binance?"
        → get_instruments(exchange_code="bnce", base_asset="eth", quote_asset="usdt")
    "What futures does Deribit offer?"
        → get_instruments(exchange_code="drbt", instrument_class="future")
    """
    if not any([exchange_code, base_asset, quote_asset, instrument_class]):
        return json.dumps({
            "error": "Please provide at least one filter (exchange_code, base_asset, "
                     "quote_asset, or instrument_class) to avoid fetching 500k+ rows."
        })

    params: dict = {"page_size": MAX_ROWS}
    if exchange_code:
        params["exchange_code"] = exchange_code
    if base_asset:
        params["base_asset"] = base_asset
    if quote_asset:
        params["quote_asset"] = quote_asset
    if instrument_class:
        params["class"] = instrument_class

    return _kaiko_get("/instruments", params)


@mcp.tool
def search_assets(keyword: str) -> str:
    """
    Search for assets whose name or code contains the given keyword.
    Use this instead of get_assets() when looking for a specific token,
    e.g. search_assets("synapse") or search_assets("syn").

    Returns matching assets with their Kaiko code, name, and asset class.
    """
    result = _kaiko_get("/assets")
    assets = json.loads(result).get("data", [])
    kw = keyword.lower()
    matches = [
        a for a in assets
        if kw in a.get("name", "").lower() or kw in a.get("code", "").lower()
    ]
    return json.dumps({"returned": len(matches), "data": matches})


@mcp.tool
def get_assets() -> str:
    """
    Return the first 100 crypto assets tracked by Kaiko (code, name, asset class).
    For a specific token use search_assets(keyword) instead.
    """
    return _kaiko_get("/assets")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()