# Financial News APIs and Open-Source Collectors

> Date: 2026-11-05
> Status: research note, not an implementation specification
> Purpose: source selection for investment-sentiment analysis, with emphasis on timeliness, provenance, noise, and 30-day history

## 1. Executive recommendation

For Chinese equities and global macro news, start with:

1. **Cailian Press (CLS)** for A-share policy, company, and industry flashes.
2. **Jin10** for macro data, central banks, FX, commodities, and overseas markets.
3. **WallstreetCN** for global macro context and longer analysis.
4. **Exchanges, CNINFO, and ministry websites** as primary evidence for filings and policy.
5. **Eastmoney** mainly as a stock-news index, not as an independent equal-weight sentiment stream.
6. **Sina and 10jqka** as fallback or cross-check sources rather than independent votes.

For immediate development, use **AkShare for current pages and incremental storage**. It does not provide dependable 30-day backfill. For straightforward Chinese historical backfill, **Tushare Pro's separately licensed News package** is the simplest identified option.

Do not combine all sources with equal weights. The same event is frequently republished across several providers, so raw article counts can amplify one story several times.

## 2. Domestic source comparison

| Source | Timeliness and editorial value | History/access path | Recommendation |
|--------|--------------------------------|---------------------|----------------|
| Cailian Press | Fast A-share policy, company, and industry flashes; also contains market snapshots, research promotion, and paid columns | Tushare `news(src="cls")`; commercial API; AkShare latest 20 | Core source |
| Jin10 | Broad macro, economic-calendar, central-bank, FX, commodity, and overseas coverage | Official flash pagination and WebSocket; verify actual pagination depth with an account | Core source |
| WallstreetCN | Strong global macro and market interpretation; separate factual flashes from opinion and analysis | Tushare `wallstreetcn`; official Skill/API supports latest, headlines, hot articles, and search | Core source |
| Eastmoney | Broad stock-linked coverage and useful URLs; substantial aggregation, syndication, market snapshots, and self-media | Tushare `eastmoney`; AkShare latest 200 flashes or latest 100 stock results | Keep as an index; downweight duplicates |
| Sina Finance | Fast and broad, but heavily overlaps other sources and emits many numeric market updates | Tushare `sina`; AkShare latest 20 | Fallback/cross-check |
| 10jqka | Useful A-share coverage; repeated flashes, market updates, and weak company-registry items add noise | Tushare `10jqka`; AkShare latest 20 | Fallback/cross-check |
| Caixin | Higher-value original and long-form reporting, but lower volume and some paid content | AkShare latest 100 selected items; Tushare `major_news` | Selective long-form source |
| Yicai, Securities Times, China Securities Journal, Shanghai Securities News | Generally useful authoritative policy and securities reporting | Tushare covers Yicai; others require RSS/page collection or licensed feeds | Keep as authoritative media sources |
| Futu | Convenient HK/US-market presentation, but many translated or attributed second-hand stories | AkShare latest 50 | Optional for HK/US coverage |
| Yuncaijing, JRJ, Phoenix aggregated flashes | Limited identified incremental value and less consistent source quality | Some are available through Tushare | Exclude from the first source set |
| Toutiao, Baidu hot search, Weibo, Zhihu, Douyin | Measure public attention rather than verified financial facts; high entertainment and clickbait content | NewsNow, TrendRadar, RSSHub | Exclude from the factual news corpus |
| Eastmoney forums, Xueqiu discussions, financial self-media | Useful for retail positioning and emotion, but rumors and opinions are common | Platform-specific collectors | Separate retail-sentiment dataset only |

Exclusion here means exclusion from the **factual investment-news corpus**. Social sources can still be valuable when modeled as a separate sentiment signal.

## 3. AkShare capabilities and observed behavior

Relevant interfaces from the [AKShare stock documentation](https://akshare.akfamily.xyz/data/stock/stock.html):

| Function | Source | Documented result |
|----------|--------|-------------------|
| `stock_info_global_cls()` | Cailian Press | Latest 20 |
| `stock_info_global_em()` | Eastmoney | Latest 200 |
| `stock_info_global_sina()` | Sina | Latest 20 |
| `stock_info_global_ths()` | 10jqka | Latest 20 |
| `stock_info_global_futu()` | Futu | Latest 50 |
| `stock_news_em(symbol=...)` | Eastmoney stock search | Latest 100 for the supplied code or keyword |
| `stock_news_main_cx()` | Caixin | Latest 100 selected items |
| `stock_info_cjzc_em()` | Eastmoney morning briefing | Historical briefing series, not a real-time flash stream |

A live probe using the repository's AKShare 1.19.3 installation confirmed all five flash interfaces and the Caixin interface. The five flash calls returned exactly 20/200/20/20/50 items. Their combined real coverage was only about 4 hours 41 minutes at that particular sample time. This demonstrates why `recent` must mean **the current upstream page**, not 24 hours or 30 days.

The sample also showed the same Nikkei market move appearing in Eastmoney, Sina, and 10jqka. CLS results included promotional research content, while Sina and 10jqka included repetitive numeric market reports. These are filtering and event-deduplication requirements, not reasons to discard the sources entirely.

AKShare has no general `stock_info_global_js` Jin10 flash interface in the checked documentation. Jin10 should use its official API rather than an assumed AKShare function.

## 4. Tushare Pro news restrictions

The [Tushare news-flash documentation](https://tushare.pro/document/2?doc_id=143) describes:

- `news` with required `start_date`, `end_date`, and `src`;
- more than six years of history according to the endpoint page;
- at most 1,500 rows per call, with repeated time-window extraction for history;
- sources including Sina, WallstreetCN, 10jqka, Eastmoney, Yuncaijing, Phoenix, JRJ, CLS, and Yicai.

The [long-form news documentation](https://tushare.pro/document/2?doc_id=195) describes `major_news` with more than eight years of history and at most 400 rows per call.

The critical restriction is in the [official permission table](https://tushare.pro/document/1?doc_id=290):

| Term | Current published condition |
|------|-----------------------------|
| Access | Independent News package; unrelated to ordinary API points |
| Personal price | CNY 1,000/year |
| Institutional price | Ten times the personal price |
| Included data | Flashes, long-form news, CCTV news transcripts |
| Request rate | 400 requests/minute |
| Total volume | Published as unlimited |
| Guaranteed history in permission table | More than three years; endpoint pages advertise longer coverage |
| Query capabilities | Source and time range, not stock symbol or keyword search |

A free token, or enough points for ordinary daily prices, does not unlock these endpoints. Local keyword filtering is still required after retrieval.

## 5. Other official APIs

### Jin10 Open Platform

The [Jin10 Open Platform](https://open.jin10.com/) publishes examples for:

- flash categories covering the main market, futures, US/HK, A-share, and commodity/FX streams;
- cursor-style flash pagination;
- WebSocket flash subscriptions;
- economic calendars, events, holidays, and reference articles.

The public example does not state a guaranteed pagination depth. Confirm 30-day completeness with an actual account before relying on it for backtesting.

Economic-calendar data is especially useful because pre-release expectations, actual-versus-forecast surprises, and post-release reactions can be modeled separately.

### WallstreetCN official Skill/API

The [official announcement](https://wallstreetcn.com/articles/3770605) describes latest, headline, hot-article, and cross-period search capabilities. The client code is available in the [WallstreetCN skills repository](https://github.com/wallstreetinsights/skills).

The code's open-source license does not automatically grant redistribution rights for article content. Content licensing remains a separate production concern.

### Eastmoney Choice and commercial feeds

Eastmoney advertises the Choice quantitative interface, while CLS and major financial newswires offer commercial data services. These are preferable when contractual stability, support, and content rights matter, but their news coverage and prices need separate procurement evaluation.

## 6. Overseas APIs

| Provider | Relevant capability | Fit |
|----------|---------------------|-----|
| Alpaca News / Benzinga | Time ranges, symbols, pagination, optional content; Alpaca advertises history back to 2015 | Strong US-market candidate |
| Alpha Vantage `NEWS_SENTIMENT` | Time range, tickers, topics, article and ticker sentiment; up to 1,000 results; documented as premium | Convenient US sentiment prototype |
| GDELT DOC 2.0 | Free rolling three-month search, 65 translated languages, article lists and tone timelines | Global macro attention; not a direct A-share sentiment substitute |
| NewsAPI.org | Developer tier commonly provides one-month search with delay, quotas, and non-production restrictions | Broad prototype source, weak as a Chinese financial primary feed |
| GNews / NewsData.io | Broad aggregation with plan-dependent delay and history | Secondary international coverage |
| Dow Jones, Reuters/LSEG, Bloomberg, RavenPack | Institutional newswires and/or news analytics with established licensing | Evaluate when budget supports commercial data |

References: [Alpaca News API](https://docs.alpaca.markets/reference/news-3), [Alpaca history announcement](https://alpaca.markets/blog/introducing-news-api-for-real-time-fiancial-news/), [Alpha Vantage documentation](https://www.alphavantage.co/documentation/), and [GDELT DOC 2.0 documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/).

Provider-provided sentiment should remain provider-specific. Do not assume scores from different vendors have identical definitions or calibration.

## 7. Open-source projects

| Project | Reuse | Limitation |
|---------|-------|------------|
| [AKShare](https://github.com/akfamily/akshare) | Standardized Python access to many public financial pages | Upstream changes can break adapters; history is limited by each source page |
| [RSSHub](https://github.com/DIYgod/RSSHub) | Normalize media and official-site updates as RSS | Incremental subscription, not a historical archive |
| [NewsNow](https://github.com/ourongxing/newsnow) | Current financial and general hot lists | Hot lists are not complete news streams |
| [TrendRadar](https://github.com/sansan0/TrendRadar) | NewsNow/RSS collection, SQLite storage, filtering, deduplication, AI reports | Oriented toward trends and notifications, not licensed financial history |
| [gdelt-doc-api](https://github.com/alex9smith/gdelt-doc-api) | Python client for GDELT document search | GDELT source coverage and machine-translated tone need validation |

Avoid depending on undocumented personal “free finance API” websites for backtests. Their provenance, continuity, timestamps, and redistribution rights are unclear, and historical data may change without notice.

## 8. Authenticity and provenance model

A recognized media brand does not make every item equally reliable or useful. Preserve these fields when the upstream evidence supports them:

- `source_platform`: the platform from which the item was collected;
- `original_source`: the actual publisher, company, agency, or newswire;
- `source_url`: the original evidence link;
- `published_at` and `first_seen_at`: publication time versus local observation time;
- `content_type`: flash, article, filing, policy, research, opinion, market snapshot, or rumor;
- `verification_level`: primary document, established media, single-source report, anonymous claim, rumor, or unknown;
- `event_id`: the cluster to which related reports belong.

Company filings should be reconciled to CNINFO or the relevant exchange. Policy should be reconciled to the issuing ministry or regulator. Media reports describe dissemination and interpretation; they should not silently override primary evidence.

## 9. Noise filtering and sentiment implications

Classify or exclude:

- repeated index-point, opening/closing, turnover, and fund-flow snapshots;
- fixed-template NAV, bond, and FX fix reports;
- weak company-registry, trademark, and recruitment items;
- “hot research,” paid-selection, VIP, and promotional items;
- exact reposts and near-identical rewrites;
- repeated summaries of old events;
- anonymous claims without a traceable origin.

Market snapshots may remain in a separate `market_snapshot` stream but should not vote in the news-text sentiment aggregate.

For sentiment, compute direction and attention separately. A useful event weight can incorporate source reliability, materiality, novelty, and time decay. Preserve raw news count, clustered event count, independent-source count, confidence, novelty, and source agreement. One negative report and eighteen reports describing three negative events should not produce the same evidence strength merely because their average direction matches.

## 10. Proposed 30-day source evaluation

When licensed historical access becomes available, compare the same 30-day window using:

1. raw item count;
2. count after exact deduplication;
3. count after event clustering;
4. proportion excluding market snapshots, promotion, and weak registry items;
5. publication lead/lag relative to the earliest observed source;
6. successful stock, sector, or macro-topic linkage rate;
7. manually reviewed material-information rate on a stratified sample;
8. extraction completeness, timestamp accuracy, and outage count.

Select sources by **incremental event-level information**, not raw article volume. Propagation across many platforms can be retained as an attention feature, but must not be counted as independent bullish or bearish evidence.

## 11. Implementation implications

The current `NewsFetcher` V1 intentionally supports only:

- current flash pages from CLS, Eastmoney, Sina, 10jqka, and Futu;
- Eastmoney's latest stock-search results;
- local keyword filtering, exact deduplication, normalization, and actual coverage reporting.

It does not claim date-range history, native keyword search, semantic event clustering, or sentiment scoring. Start storing timestamped snapshots now; revisit paid backfill only after the collection and filtering pipeline demonstrates useful signal quality.
