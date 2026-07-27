from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, ClassVar

import litellm
import structlog
from pydantic import BaseModel, Field, field_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from runtime.config_loader import RuntimeConfig, get_llm_config, load_config
from runtime.notifier.composite import build_notifier
from runtime.openalice_client import OpenAliceClient, OpenAliceError
from tools.base.base_tool import BaseTool
from tools.base.tool_result import ArtifactRef, ToolResult

logger = structlog.get_logger()


class NewsFilterToolInput(BaseModel):
    window_minutes: int = Field(default=60, ge=1)
    limit: int = Field(default=100, ge=1)
    min_score: float = Field(default=0.6, ge=0.0, le=1.0)
    medium_score: float = Field(default=0.3, ge=0.0, le=1.0)
    read_concurrency: int = Field(default=5, ge=1, le=20)
    pipeline_run_id: str | None = None

    @field_validator("medium_score")
    @classmethod
    def _medium_below_high(cls, value: float, info: Any) -> float:
        if value > info.data.get("min_score", 0.6):
            raise ValueError("medium_score must be <= min_score")
        return value


class ScoredArticle(BaseModel):
    id: str
    time: str
    title: str
    source: str
    link: str
    content: str = ""
    score: float | None = None
    reason: str | None = None
    error: str | None = None


class NewsFilterToolOutput(BaseModel):
    total: int
    new: int
    scored: int
    high: list[ScoredArticle]
    medium_pending: list[ScoredArticle]
    degraded: list[ScoredArticle]
    artifact: str


class NewsFilterTool(BaseTool):
    name: ClassVar[str] = "news_filter_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "news"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = NewsFilterToolInput
    output_model: ClassVar[type[BaseModel]] = NewsFilterToolOutput

    def __init__(
        self,
        artifacts_path: Path | str | None = None,
        openalice_client: OpenAliceClient | None = None,
        notifier: Any | None = None,
        watch_state_path: Path | str | None = None,
    ) -> None:
        self._artifacts_path: Path | None = Path(artifacts_path) if artifacts_path else None
        self._openalice_client: OpenAliceClient | None = openalice_client
        self._notifier: Any | None = notifier
        self._watch_state_path: Path | None = Path(watch_state_path) if watch_state_path else None

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        validated = self.input_model(**inputs)
        params = validated.model_dump()

        run_id = params.get("pipeline_run_id") or str(uuid.uuid4())
        cfg = self._load_config()
        artifacts_path = self._artifacts_path or cfg.paths.artifacts
        watch_state_path = self._watch_state_path or Path(cfg.paths.database).parent / "watch_state.json"

        client = self._openalice_client or OpenAliceClient(
            cfg.openalice, timeout=float(cfg.llm.timeout)
        )
        notifier = self._notifier or build_notifier(cfg.notifier)

        from_time = self._compute_from_time(params["window_minutes"])
        try:
            rss = await client.window_rss(from_time=from_time, limit=params["limit"])
        except OpenAliceError as exc:
            logger.error("news_filter.openalice_failed", error=str(exc))
            return ToolResult(success=False, error=f"OpenAlice gateway error: {exc}")

        raw_articles = rss.get("results") if isinstance(rss, dict) else None
        if not isinstance(raw_articles, list):
            raw_articles = []
        total = rss.get("total") if isinstance(rss, dict) else len(raw_articles)
        if not isinstance(total, int):
            total = len(raw_articles)

        state = self._load_state(watch_state_path)
        seen_ids = self._get_seen_ids(state)

        new_articles: list[dict[str, Any]] = []
        for article in raw_articles:
            article_id = self._article_id(article)
            if article_id not in seen_ids:
                new_articles.append(article)

        # Enrich new articles with full metadata via readRss.
        semaphore = asyncio.Semaphore(params["read_concurrency"])
        enriched_articles: list[dict[str, Any]] = []
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._enrich_article(client, article, semaphore))
                for article in new_articles
            ]
        for task in tasks:
            enriched = task.result()
            if enriched is not None:
                enriched_articles.append(enriched)

        high: list[ScoredArticle] = []
        medium_pending: list[ScoredArticle] = []
        degraded: list[ScoredArticle] = []
        scored_count = 0

        llm_cfg = get_llm_config(cfg, self.name)
        model, api_key, api_base, timeout = self._normalize_llm_settings(llm_cfg)

        try:
            for article in enriched_articles:
                scored = await self._score_article(
                    article,
                    model=model,
                    api_key=api_key,
                    api_base=api_base,
                    timeout=timeout,
                )
                if scored.error:
                    degraded.append(scored)
                    continue

                scored_count += 1
                if scored.score is None:
                    continue
                if scored.score >= params["min_score"]:
                    high.append(scored)
                elif scored.score >= params["medium_score"]:
                    medium_pending.append(scored)
        except Exception as exc:
            logger.error("news_filter.llm_failed", error=str(exc))
            await self._notify_failure(notifier, exc)
            return ToolResult(
                success=False,
                error=f"LLM scoring failed after retries: {exc}",
            )

        high.sort(key=lambda a: a.score or 0.0, reverse=True)
        medium_pending.sort(key=lambda a: a.score or 0.0, reverse=True)

        now = datetime.now(timezone.utc)
        processed_ids = [self._article_id(a) for a in raw_articles]
        self._update_state(state, watch_state_path, processed_ids, now)

        output = self.output_model(
            total=total,
            new=len(new_articles),
            scored=scored_count,
            high=high,
            medium_pending=medium_pending,
            degraded=degraded,
            artifact="",
        )

        artifact = self._persist_artifact(
            output=output,
            artifacts_path=artifacts_path,
            run_id=run_id,
        )
        output.artifact = artifact.relative_path

        return ToolResult(
            success=True,
            data=output.model_dump(),
            artifacts=[artifact],
        )

    def _load_config(self) -> RuntimeConfig:
        try:
            return load_config()
        except FileNotFoundError:
            return RuntimeConfig()

    @staticmethod
    def _compute_from_time(window_minutes: int) -> str:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _article_id(article: dict[str, Any]) -> str:
        return str(article.get("id", ""))

    @staticmethod
    def _load_state(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("news_filter.watch_state_corrupt", path=str(path), error=str(exc))
            return {}

    @staticmethod
    def _get_seen_ids(state: dict[str, Any]) -> set[str]:
        section = state.get("news_filter") if isinstance(state.get("news_filter"), dict) else {}
        seen = section.get("seen_ids")
        if isinstance(seen, list):
            return {str(i) for i in seen}
        return set()

    @staticmethod
    def _update_state(
        state: dict[str, Any],
        path: Path,
        seen_ids: list[str],
        now: datetime,
    ) -> None:
        if not isinstance(state, dict):
            state = {}
        section = state.setdefault("news_filter", {})
        existing = {str(i) for i in section.get("seen_ids", []) if isinstance(i, (str, int))}
        existing.update(seen_ids)
        section["seen_ids"] = sorted(existing)
        section["last_run_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _normalize_llm_settings(llm_cfg: Any) -> tuple[str, str | None, str | None, float]:
        model = getattr(llm_cfg, "model", "gpt-4o-mini") or "gpt-4o-mini"
        api_key = getattr(llm_cfg, "api_key", "") or None
        api_base = getattr(llm_cfg, "api_base", "") or None
        timeout = float(getattr(llm_cfg, "timeout", 30) or 30)
        return model, api_key, api_base, timeout

    _SOURCE_RE = re.compile(r'"source"\s*:\s*"([^"]*?)(?:"|$)')
    _LINK_RE = re.compile(r'"link"\s*:\s*"([^"]*?)(?:"|$)')

    async def _enrich_article(
        self,
        client: OpenAliceClient,
        article: dict[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any] | None:
        """Fetch full article content via readRss to avoid truncated metadata."""
        article_id = self._article_id(article)
        if not article_id:
            return None
        try:
            numeric_id = int(article_id)
        except ValueError:
            logger.warning("news_filter.invalid_article_id", article_id=article_id)
            return None

        async with semaphore:
            try:
                full = await client.read_rss(numeric_id)
            except OpenAliceError as exc:
                logger.warning(
                    "news_filter.read_rss_failed",
                    article_id=article_id,
                    error=str(exc),
                )
                return None

        # Merge: keep windowRss time/title, use readRss metadata (and content if present).
        merged = dict(article)
        merged["metadata"] = full.get("metadata", article.get("metadata", "{}"))
        if "content" in full:
            merged["content"] = full["content"]
        return merged

    @staticmethod
    def _parse_article(article: dict[str, Any]) -> dict[str, Any]:
        metadata_value = article.get("metadata", "{}")
        if isinstance(metadata_value, dict):
            metadata = metadata_value
        else:
            metadata_text = str(metadata_value)
            try:
                metadata = json.loads(metadata_text)
            except json.JSONDecodeError:
                # Fallback for truncated metadata from windowRss.
                source_match = NewsFilterTool._SOURCE_RE.search(metadata_text)
                link_match = NewsFilterTool._LINK_RE.search(metadata_text)
                metadata = {
                    "source": source_match.group(1) if source_match else "",
                    "link": link_match.group(1) if link_match else "",
                }

        return {
            "id": str(article.get("id", "")),
            "time": str(article.get("time", "")),
            "title": str(article.get("title", "")),
            "source": str(metadata.get("source", "")),
            "link": str(metadata.get("link", "")),
            "content": str(article.get("content", "")),
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _call_litellm(
        self,
        prompt: str,
        model: str,
        api_key: str | None,
        api_base: str | None,
        timeout: float,
    ) -> Any:
        return await litellm.acompletion(
            model=model,
            api_key=api_key,
            api_base=api_base,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
            timeout=timeout,
        )

    async def _score_article(
        self,
        article: dict[str, Any],
        model: str,
        api_key: str | None,
        api_base: str | None,
        timeout: float,
    ) -> ScoredArticle:
        parsed = self._parse_article(article)
        prompt = self._build_prompt(parsed)

        # This call retries via tenacity. If it ultimately fails, the exception
        # propagates and the whole tool fails loudly (no keyword fallback).
        response = await self._call_litellm(
            prompt=prompt,
            model=model,
            api_key=api_key,
            api_base=api_base,
            timeout=timeout,
        )
        content = response.choices[0].message.content

        try:
            score, reason = self._parse_score_response(content)
        except Exception as exc:
            logger.warning(
                "news_filter.score_parse_failed",
                article_id=parsed["id"],
                error=str(exc),
            )
            return ScoredArticle(
                **parsed,
                score=None,
                reason=None,
                error=f"LLM parse error: {exc}",
            )

        return ScoredArticle(
            **parsed,
            score=score,
            reason=reason,
            error=None,
        )

    @staticmethod
    def _build_prompt(article: dict[str, Any]) -> str:
        content_preview = article["content"][:800] if article["content"] else ""
        return (
            "You are a crypto trading risk analyst. Rate the article's relevance to a "
            "short-term crypto trading decision and its potential to be a black-swan / "
            "tail-risk event. Return ONLY JSON: "
            '{"score": float 0-1, "reason": string}. 0 = irrelevant, 1 = extremely urgent black swan.\n\n'
            f"Title: {article['title']}\n"
            f"Time: {article['time']}\n"
            f"Source: {article['source']}\n"
            f"Link: {article['link']}\n"
            f"Content preview: {content_preview}"
        )

    @staticmethod
    def _parse_score_response(content: str | None) -> tuple[float, str]:
        if not isinstance(content, str):
            raise ValueError("LLM response content is empty")

        text = content.strip()
        # Strip markdown code fences if the model added them.
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not a JSON object")

        score = parsed.get("score")
        reason = parsed.get("reason")
        if not isinstance(score, (int, float)):
            raise ValueError("LLM response missing numeric 'score'")
        if not isinstance(reason, str):
            reason = str(reason) if reason is not None else ""

        score = max(0.0, min(1.0, float(score)))
        return score, reason

    async def _notify_failure(self, notifier: Any, exc: Exception) -> None:
        try:
            await notifier.send(
                subject="news_filter_tool LLM failure",
                body=f"The news filter tool failed to score articles after retries. Error: {exc}",
            )
        except Exception as notify_exc:
            logger.warning(
                "news_filter.notification_failed",
                error=str(notify_exc),
            )

    def _persist_artifact(
        self,
        output: NewsFilterToolOutput,
        artifacts_path: Path,
        run_id: str,
    ) -> ArtifactRef:
        artifact_dir = artifacts_path / run_id / "news_filter_tool"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "news_filter_result.json"
        content = json.dumps(
            output.model_dump(),
            indent=2,
            ensure_ascii=False,
        )
        artifact_path.write_text(content, encoding="utf-8")

        relative_path = str(artifact_path.relative_to(artifacts_path))
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        return ArtifactRef(
            name="news_filter_result.json",
            mime_type="application/json",
            relative_path=relative_path,
            sha256=sha256,
            content=content,
        )
