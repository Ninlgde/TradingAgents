"""AkShare-based A-share (China) news & sentiment data fetching.

AkShare (https://akshare.akfamily.xyz) pulls from EastMoney (东方财富) and
other Chinese data vendors. It is an OPTIONAL dependency — install it in your
environment with ``pip install akshare``.

Why this module exists: Yahoo Finance's news coverage of A-share tickers is
effectively empty (no headlines, no sentiment sources), which left the News
and Sentiment analysts with nothing real to analyze for Chinese stocks. These
functions source real A-share data:

  * ``get_news_akshare``          — EastMoney per-stock news feed
  * ``get_global_news_akshare``   — EastMoney global/macro flash news
  * ``get_sentiment_akshare``     — EastMoney 千股千评 (per-stock composite
                                    score, institutional participation,
                                    attention index) — used by the Sentiment
                                    analyst in place of StockTwits/Reddit,
                                    which do not cover A-shares

Contract matches the yfinance news module: every function returns a formatted
string and degrades to an explicit sentinel instead of raising, so the agent
never fabricates coverage it did not receive.
"""

from __future__ import annotations

import contextlib
import io
import logging
import re
import threading
import time
from datetime import datetime, timedelta

from .config import get_config
from .errors import NoMarketDataError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# A-share symbol detection
# ---------------------------------------------------------------------------

# Shanghai (.SS), Shenzhen (.SZ), Beijing (.BJ) exchange suffixes plus the
# bare six-digit codes Chinese brokers use.
_A_SHARE_RE = re.compile(r"^\d{6}(\.(SS|SZ|BJ))?$", re.IGNORECASE)


def is_a_share(ticker: str) -> bool:
    """True when ``ticker`` looks like a mainland-China listed stock.

    Matches both Yahoo-style ``600036.SS`` / ``000001.SZ`` and bare six-digit
    codes (``600036``). Purely syntactic; no network calls.
    """
    if not isinstance(ticker, str):
        return False
    return bool(_A_SHARE_RE.match(ticker.strip().upper()))


def _em_code(ticker: str) -> str:
    """Extract the six-digit EastMoney security code from a ticker."""
    m = re.search(r"\d{6}", ticker)
    if m is None:
        raise NoMarketDataError(
            ticker, ticker, f"'{ticker}' has no 6-digit security code"
        )
    return m.group(0)


def _import_akshare():
    """Import akshare lazily; raise NoMarketDataError with a clear message if absent."""
    try:
        import akshare  # noqa: PLC0415
        return akshare
    except ImportError as exc:  # pragma: no cover - depends on env
        raise NoMarketDataError(
            "akshare", "akshare",
            "the 'akshare' package is not installed. Run: pip install akshare",
        ) from exc


# ---------------------------------------------------------------------------
# Per-stock news (EastMoney)
# ---------------------------------------------------------------------------

def get_news_akshare(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Retrieve A-share news for ``ticker`` from EastMoney.

    Non-A-share tickers are delegated to the yfinance implementation so the
    vendor chain stays uniform (configure ``news_data=akshare`` and US/global
    coverage keeps working).
    """
    if not is_a_share(ticker):
        from .yfinance_news import get_news_yfinance  # noqa: PLC0415
        return get_news_yfinance(ticker, start_date, end_date)

    try:
        ak = _import_akshare()
        df = ak.stock_news_em(symbol=_em_code(ticker))
        if df is None or df.empty:
            return f"No news found for {ticker} (EastMoney)"

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        news_str = ""
        kept = 0
        for _, row in df.iterrows():
            pub = str(row.get("发布时间", ""))
            if pub:
                try:
                    pub_dt = datetime.strptime(pub[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                if not (start_dt <= pub_dt < end_dt + timedelta(days=1)):
                    continue
            title = str(row.get("新闻标题", "")).strip()
            content = str(row.get("新闻内容", "")).strip()
            source = str(row.get("文章来源", "东方财富")).strip()
            link = str(row.get("新闻链接", "")).strip()
            if not title:
                continue
            news_str += f"### {title} (source: {source})\n"
            if content:
                news_str += f"{content}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"
            kept += 1

        if kept == 0:
            return f"No news found for {ticker} between {start_date} and {end_date}"

        return f"## {ticker} News (EastMoney), from {start_date} to {end_date}:\n\n{news_str}"

    except NoMarketDataError:
        raise
    except Exception as e:  # noqa: BLE001 - mirror yfinance module's soft contract
        logger.warning("EastMoney news fetch failed for %s: %s", ticker, e)
        return f"Error fetching news for {ticker}: {str(e)}"


# ---------------------------------------------------------------------------
# Global / macro news (EastMoney flash feed)
# ---------------------------------------------------------------------------

def get_global_news_akshare(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Retrieve global/macro news from the EastMoney flash feed.

    ``look_back_days`` / ``limit`` fall back to the configured defaults
    (``global_news_lookback_days`` / ``global_news_article_limit``) when not
    passed, matching ``get_global_news_yfinance``.
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    try:
        ak = _import_akshare()
        df = ak.stock_info_global_em()
        if df is None or df.empty:
            return f"No global news found for {curr_date} (EastMoney)"

        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - timedelta(days=look_back_days)

        news_str = ""
        kept = 0
        for _, row in df.iterrows():
            if kept >= limit:
                break
            pub = str(row.get("发布时间", ""))
            if pub:
                try:
                    pub_dt = datetime.strptime(pub[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                if not (start_dt <= pub_dt < curr_dt + timedelta(days=1)):
                    continue
            title = str(row.get("标题", "")).strip()
            summary = str(row.get("摘要", "")).strip()
            link = str(row.get("链接", "")).strip()
            if not title:
                continue
            news_str += f"### {title} (source: EastMoney)\n"
            if summary:
                news_str += f"{summary}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"
            kept += 1

        if kept == 0:
            return f"No global news found between {start_dt:%Y-%m-%d} and {curr_date}"

        return (
            f"## Global Market News (EastMoney), "
            f"from {start_dt:%Y-%m-%d} to {curr_date}:\n\n{news_str}"
        )

    except NoMarketDataError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("EastMoney global news fetch failed: %s", e)
        return f"Error fetching global news: {str(e)}"


# ---------------------------------------------------------------------------
# Sentiment (EastMoney 千股千评)
# ---------------------------------------------------------------------------

# stock_comment_em() returns the WHOLE market (~5000 rows, paginated). Cache
# the composite table briefly so repeated per-ticker sentiment fetches within
# one run don't hammer EastMoney.
_COMMENT_CACHE_TTL_SECONDS = 3600
_comment_cache_lock = threading.Lock()
_comment_cache: tuple[float, object] | None = None  # (fetched_at, dataframe)


def _comment_table():
    """Return the cached 千股千评 table, refreshing it if stale."""
    global _comment_cache
    with _comment_cache_lock:
        now = time.time()
        if (
            _comment_cache is not None
            and now - _comment_cache[0] < _COMMENT_CACHE_TTL_SECONDS
        ):
            return _comment_cache[1]
        ak = _import_akshare()
        # stock_comment_em() prints a tqdm progress bar for its paginated
        # load — silence it so the run log stays clean (data is unaffected).
        with contextlib.redirect_stderr(io.StringIO()):
            df = ak.stock_comment_em()
        _comment_cache = (now, df)
        return df


def get_sentiment_akshare(ticker: str, trade_date: str) -> str:
    """A-share sentiment block for the Sentiment analyst.

    Uses EastMoney 千股千评 (per-stock composite rating): 综合得分, 机构参与度,
    关注指数, 主力成本, 目前排名 etc. Serves the role StockTwits/Reddit play
    for US tickers — real, verifiable market-attention data instead of a
    fabricated placeholder.
    """
    if not is_a_share(ticker):
        return (
            f"<unavailable> {ticker} is not an A-share ticker; "
            "EastMoney sentiment does not apply."
        )

    try:
        df = _comment_table()
        code = _em_code(ticker)
        row = df[df["代码"].astype(str) == code]
        if row.empty:
            return (
                f"<unavailable> no 千股千评 record for {ticker}; "
                "the stock may be newly listed or suspended."
            )
        r = row.iloc[0]
        return f"""## EastMoney 千股千评 — {r['名称']} ({ticker}) as of {r.get('交易日', trade_date)}

- 综合得分: {r.get('综合得分', 'N/A')}  (100 = strongest composite rating)
- 机构参与度: {r.get('机构参与度', 'N/A')}  (0-1; institutional participation)
- 关注指数: {r.get('关注指数', 'N/A')}  (market-attention index)
- 目前排名 / 上升: {r.get('目前排名', 'N/A')} / {r.get('上升', 'N/A')}  (rank across all A-shares, +/− moves)
- 主力成本: {r.get('主力成本', 'N/A')}  (main-force average cost basis)
- 最新价 / 涨跌幅: {r.get('最新价', 'N/A')} / {r.get('涨跌幅', 'N/A')}%
- 换手率 / 市盈率: {r.get('换手率', 'N/A')}% / {r.get('市盈率', 'N/A')}

Interpretation: a high 综合得分 with rising 关注指数 and strong 机构参与度
suggests institutional accumulation; a falling rank with weak participation
suggests fading attention. Treat as market-attention signal, not a price call.
"""

    except NoMarketDataError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("EastMoney sentiment fetch failed for %s: %s", ticker, e)
        return f"<unavailable> EastMoney sentiment error: {e}"


# ---------------------------------------------------------------------------
# Insider transactions — A-shares have no public insider-trade feed here;
# delegate to yfinance so the news_data vendor chain stays complete.
# ---------------------------------------------------------------------------

def get_insider_transactions_akshare(ticker: str) -> str:
    """Delegate to the yfinance insider feed (A-shares have no EM equivalent)."""
    from .y_finance import get_yfinance_insider_transactions  # noqa: PLC0415
    return get_yfinance_insider_transactions(ticker)
