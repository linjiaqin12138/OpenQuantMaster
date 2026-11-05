from __future__ import annotations

import asyncio
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from src.entry.cli.base import echo_service_result, output_option
from src.services.news_fetcher import NewsFetcher


def render_news_fetcher(data: dict[str, Any]) -> None:
    console = Console()
    coverage = data["coverage"]
    console.print(
        f"[bold]NewsFetcher[/bold] {data['mode']} [dim]({data['rows']} rows; "
        f"{coverage['earliest'] or '-'} to {coverage['latest'] or '-'})[/dim]"
    )
    if not data["items"]:
        console.print("No news returned.")
    else:
        table = Table(show_lines=False)
        for column in ("Published", "Source", "Title", "URL"):
            table.add_column(column)
        for item in data["items"]:
            title = item["title"] or item["summary"] or item["content"] or ""
            table.add_row(item["published_at"], item["source"], title, item["url"] or "")
        console.print(table)
    for error in data["errors"]:
        console.print(f"[yellow]{error['source']}: {error['message']}[/yellow]")


@click.command(
    epilog="""
\b
Examples:
  qm-cli run news-fetcher --mode recent --sources cls,em --keywords 降息,央行
  qm-cli run news-fetcher --mode stock-recent --symbol 603777 --limit 50 -o json

Recent means each provider's current latest page, not a fixed time window.
Keywords are filtered locally after fetching. JSON output contains only service data.
""",
)
@click.option(
    "--mode",
    default="recent",
    show_default=True,
    type=click.Choice(["recent", "stock-recent"]),
    help="Latest multi-source flashes or latest Eastmoney stock news.",
)
@click.option("--sources", help="Comma-separated sources for recent mode: cls,em,sina,ths,futu.")
@click.option("--symbol", help="Stock code or keyword required by stock-recent mode.")
@click.option("--keywords", default="", help="Comma-separated keywords filtered locally.")
@click.option(
    "--keyword-match",
    default="any",
    show_default=True,
    type=click.Choice(["any", "all"]),
)
@click.option("--limit", type=int, help="Optional total cap after filtering and deduplication.")
@click.option("--no-deduplicate", is_flag=True, help="Disable exact text deduplication.")
@output_option
def news_fetcher(
    mode: str,
    sources: str | None,
    symbol: str | None,
    keywords: str,
    keyword_match: str,
    limit: int | None,
    no_deduplicate: bool,
    output: str,
) -> None:
    """Fetch and normalize recent financial news through AkShare."""
    result = asyncio.run(
        NewsFetcher().run(
            {
                "mode": mode.replace("-", "_"),
                "sources": [value.strip() for value in sources.split(",") if value.strip()]
                if sources is not None
                else None,
                "symbol": symbol,
                "keywords": [value.strip() for value in keywords.split(",") if value.strip()],
                "keyword_match": keyword_match,
                "limit": limit,
                "deduplicate": not no_deduplicate,
            }
        )
    )
    echo_service_result(result, "news-fetcher", output)
