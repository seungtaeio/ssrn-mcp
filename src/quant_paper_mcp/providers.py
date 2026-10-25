"""Rights-conscious, API-only scholarly metadata access.

Security / license boundary:
  * Outbound HTTP goes only to fixed OpenAlex and Crossref API origins.
  * SSRN, Elsevier, paper-hosted pages and PDF files are NEVER fetched.
  * Returned fields exclude abstracts, full text and dedicated PDF fields.
    Provider-supplied landing-page links are unverified and never downloaded.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import quote, unquote, urlsplit

import httpx

ProviderName = Literal["openalex", "crossref"]
ORIGINS = {
    "openalex": "https://api.openalex.org",
    "crossref": "https://api.crossref.org",
}
_DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s?#]+$", re.IGNORECASE)
_SSRN_ID_RE = re.compile(r"^[1-9][0-9]{0,11}$")
_MAX_RESPONSE_BYTES = 2_000_000
_CACHE_TTL_SECONDS = 15 * 60
_MAX_CACHE_ENTRIES = 128
_MAX_RETRY_WAIT_SECONDS = 2.0


@dataclass(frozen=True)
class Paper:
    source: str
    source_id: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    landing_page: str | None
    cited_by_count: int | None = None
    is_open_access: bool | None = None
    open_access_landing_page: str | None = None

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["note"] = (
            "Metadata only. Links are for manual access; no full-text access, "
            "copyright clearance, or automated downloads are implied."
        )
        return data


def normalize_doi(value: str) -> str:
    doi = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    if not _DOI_RE.fullmatch(doi) or len(doi) > 255:
        raise ValueError("Provide a valid DOI (e.g. 10.1000/xyz123).")
    return doi


def ssrn_reference(abstract_id: str) -> dict[str, str]:
    """Format a manually supplied SSRN abstract ID; does not access SSRN."""
    if not _SSRN_ID_RE.fullmatch(abstract_id.strip()):
        raise ValueError("SSRN abstract ID must contain 1-12 digits without leading zero.")
    paper_id = abstract_id.strip()
    return {
        "abstract_id": paper_id,
        "url": f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={paper_id}",
        "notice": "Link only; no network call, verification, scraping or PDF download.",
    }


def _safe_https_link(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
            return None
        if parts.port not in (None, 443):
            return None
        if any(ch in value for ch in ("\r", "\n", "\t")):
            return None
        return value
    except ValueError:
        return None


def _authors_openalex(record: dict[str, Any]) -> list[str]:
    output: list[str] = []
    authorships = record.get("authorships")
    for author in authorships if isinstance(authorships, list) else []:
        if isinstance(author, dict):
            obj = author.get("author") or {}
            if isinstance(obj, dict) and isinstance(obj.get("display_name"), str):
                output.append(obj["display_name"][:150])
    return output[:15]


def _parse_openalex(record: dict[str, Any]) -> Paper:
    primary = record.get("primary_location") or {}
    best_oa = record.get("best_oa_location") or {}
    if not isinstance(best_oa, dict):
        best_oa = {}
    if not isinstance(primary, dict):
        primary = {}
    oa = record.get("open_access") or {}
    if not isinstance(oa, dict):
        oa = {}
    doi_raw = record.get("doi")
    try:
        doi = normalize_doi(doi_raw) if isinstance(doi_raw, str) else None
    except ValueError:
        doi = None
    year = record.get("publication_year")
    count = record.get("cited_by_count")
    source_id = record.get("id")
    title = record.get("title")
    return Paper(
        source="openalex",
        source_id=source_id[:300] if isinstance(source_id, str) else "",
        title=title[:500] if isinstance(title, str) and title else "Untitled",
        authors=_authors_openalex(record),
        year=year if type(year) is int else None,
        doi=doi,
        landing_page=_safe_https_link(primary.get("landing_page_url"))
        or _safe_https_link(record.get("id")),
        cited_by_count=count if type(count) is int else None,
        is_open_access=oa.get("is_oa") if isinstance(oa.get("is_oa"), bool) else None,
        # A link is NOT permission to download or AI-process a paper.
        open_access_landing_page=(
            _safe_https_link(best_oa.get("landing_page_url"))
            or (_safe_https_link(primary.get("landing_page_url"))
                if primary.get("is_oa") is True else None)
        ),
    )


def _parse_crossref(record: dict[str, Any]) -> Paper:
    authors = []
    author_list = record.get("author")
    for author in author_list if isinstance(author_list, list) else []:
        if isinstance(author, dict):
            full = " ".join(x for x in (author.get("given"), author.get("family")) if isinstance(x, str))
            if full:
                authors.append(full[:150])
    published = record.get("published")
    date_parts = published.get("date-parts") if isinstance(published, dict) else None
    first_date = date_parts[0] if isinstance(date_parts, list) and date_parts else None
    year = first_date[0] if isinstance(first_date, list) and first_date else None
    doi_raw = record.get("DOI")
    try:
        doi = normalize_doi(doi_raw) if isinstance(doi_raw, str) else None
    except ValueError:
        doi = None
    title = record.get("title") or []
    return Paper(
        source="crossref",
        source_id=doi or "",
        title=title[0][:500] if isinstance(title, list) and title and isinstance(title[0], str) else "Untitled",
        authors=authors[:15],
        year=year if type(year) is int else None,
        doi=doi,
        landing_page=_safe_https_link(f"https://doi.org/{doi}") if doi else None,
    )


def _metadata_records(provider: ProviderName, endpoint: str, data: Any) -> list[Paper]:
    """Reconstruct only the per-provider fields allowed by Paper before caching.

    Raw provider payloads, including Crossref abstracts and OpenAlex inverted
    abstracts, are transient and never placed in the cache.
    """
    if not isinstance(data, dict):
        raise ValueError("Invalid metadata API response.")
    if provider == "openalex":
        records = data.get("results")
        parser = _parse_openalex
    else:
        message = data.get("message")
        if not isinstance(message, dict):
            raise ValueError("Invalid metadata API response.")
        records = message.get("items") if endpoint == "/works" else [message]
        parser = _parse_crossref
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise ValueError("Invalid metadata API response: expected a list of records.")
    return [parser(record) for record in records[:20]]


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        # Avoid converting arbitrarily large integer headers.
        return float(value) if len(value) < 10 else float("inf")
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


class MetadataAPI:
    """A tiny, testable client. No generic fetch method is exposed to MCP."""

    def __init__(
        self,
        *,
        openalex_api_key: str | None = None,
        crossref_email: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.openalex_api_key = openalex_api_key if openalex_api_key is not None else os.getenv("OPENALEX_API_KEY", "")
        self.crossref_email = crossref_email if crossref_email is not None else os.getenv("CROSSREF_EMAIL", "")
        self._transport = transport
        self._throttle_lock = asyncio.Lock()
        self._last_request = 0.0
        self._cache: dict[str, tuple[float, list[Paper]]] = {}

    async def _get(self, provider: ProviderName, endpoint: str, params: dict[str, Any]) -> list[Paper]:
        # Prevent unrestricted fetching, even if malicious tool arguments are supplied.
        if provider not in ORIGINS:
            raise ValueError("Invalid API endpoint.")
        if endpoint != "/works":
            if provider != "crossref" or not endpoint.startswith("/works/"):
                raise ValueError("Endpoint is not on the metadata API allowlist.")
            doi = normalize_doi(unquote(endpoint[len("/works/"):]))
            if endpoint != "/works/" + quote(doi, safe=""):
                raise ValueError("Endpoint is not on the metadata API allowlist.")
        headers = {
            "User-Agent": "quant-paper-mcp/0.1 (research metadata discovery; contact via CROSSREF_EMAIL)",
            "Accept-Encoding": "identity",
        }
        params = dict(params)
        if provider == "openalex" and self.openalex_api_key:
            headers["Authorization"] = f"Bearer {self.openalex_api_key}"
        if provider == "crossref" and self.crossref_email:
            params["mailto"] = self.crossref_email
            headers["User-Agent"] = f"quant-paper-mcp/0.1 (mailto:{self.crossref_email})"
        # Cache only allowlisted Paper records, with a TTL and a count bound.
        cache_key = repr((provider, endpoint, sorted(params.items())))
        now = time.monotonic()
        self._cache = {key: entry for key, entry in self._cache.items() if now - entry[0] < _CACHE_TTL_SECONDS}
        if cache_key in self._cache:
            return self._cache[cache_key][1]
        url = ORIGINS[provider] + endpoint
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(12),
            follow_redirects=False,
            headers=headers,
        ) as client:
            for attempt in range(3):
                async with self._throttle_lock:
                    loop = asyncio.get_running_loop()
                    since = loop.time() - self._last_request
                    # One request at a time, intentionally far below public API limits.
                    min_gap = 1.1 if provider == "crossref" else 0.2
                    if since < min_gap:
                        await asyncio.sleep(min_gap - since)
                    self._last_request = loop.time()
                    # Read an uncompressed stream so decoding cannot allocate a
                    # large inflated body before our size check runs.
                    async with client.stream("GET", url, params=params) as response:
                        retry_after = (
                            _retry_after_seconds(response.headers.get("Retry-After"))
                            if response.status_code in (429, 503) else None
                        )
                        if retry_after is not None and retry_after > _MAX_RETRY_WAIT_SECONDS:
                            raise ValueError("Metadata provider requests a longer retry delay. Retry later.")
                        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                            retry_delay = max(retry_after or 0.0, 0.6 * 2**attempt)
                        else:
                            # Never follow a redirect to a publisher, SSRN or any other host.
                            response.raise_for_status()
                            if response.headers.get("Content-Encoding", "identity").strip().lower() not in ("", "identity"):
                                raise ValueError("Compressed metadata responses are not supported; provider must honor identity encoding.")
                            content_length = response.headers.get("Content-Length", "")
                            if content_length.isdigit() and int(content_length) > _MAX_RESPONSE_BYTES:
                                raise ValueError("API response exceeds the safety size limit.")
                            body = bytearray()
                            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                                if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                                    raise ValueError("API response exceeds the safety size limit.")
                                body.extend(chunk)
                            try:
                                data = json.loads(body)
                            except (ValueError, UnicodeDecodeError) as exc:
                                raise ValueError("Invalid metadata API response: expected JSON.") from exc
                            papers = _metadata_records(provider, endpoint, data)
                            break
                await asyncio.sleep(retry_delay)
            else:
                raise RuntimeError("Metadata provider did not respond successfully.")
            if len(self._cache) >= _MAX_CACHE_ENTRIES:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = (time.monotonic(), papers)
            return papers

    async def search(self, query: str, *, provider: ProviderName = "openalex", limit: int = 5) -> list[Paper]:
        query = query.strip()
        if len(query) < 2 or len(query) > 200:
            raise ValueError("Search query must contain 2-200 characters.")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20.")
        if provider == "openalex":
            papers = await self._get(provider, "/works", {
                "search": query, "per_page": limit,
                "select": "id,title,doi,publication_year,authorships,primary_location,best_oa_location,open_access,cited_by_count",
            })
            return papers[:limit]
        if provider == "crossref":
            papers = await self._get(provider, "/works", {
                "query.bibliographic": query, "rows": limit,
                "select": "DOI,title,author,published,URL",
            })
            return papers[:limit]
        raise ValueError("provider must be 'openalex' or 'crossref'.")

    async def by_doi(self, doi: str, *, provider: ProviderName = "crossref") -> Paper | None:
        doi = normalize_doi(doi)
        if provider == "crossref":
            try:
                papers = await self._get("crossref", "/works/" + quote(doi, safe=""), {})
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    return None
                raise
            return papers[0] if papers and papers[0].doi and papers[0].doi.lower() == doi.lower() else None
        if provider == "openalex":
            # OpenAlex parses commas and pipes as filter operators even when
            # URL-encoded. Crossref's escaped DOI path can handle such suffixes.
            if any(char in doi for char in (",", "|")):
                raise ValueError("This DOI contains OpenAlex filter operators; use Crossref for this DOI.")
            papers = await self._get("openalex", "/works", {
                "filter": f"doi:https://doi.org/{doi}", "per_page": 1,
                "select": "id,title,doi,publication_year,authorships,primary_location,best_oa_location,open_access,cited_by_count",
            })
            return papers[0] if papers and papers[0].doi and papers[0].doi.lower() == doi.lower() else None
        raise ValueError("provider must be 'openalex' or 'crossref'.")
