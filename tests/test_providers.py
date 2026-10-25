import gzip
import time

import httpx
import pytest

import quant_paper_mcp.providers as providers

from quant_paper_mcp.providers import MetadataAPI, normalize_doi, ssrn_reference


OPENALEX_RECORD = {
    "id": "https://openalex.org/W123456",
    "title": "A Study of Momentum",
    "doi": "https://doi.org/10.1234/test.paper",
    "publication_year": 2023,
    "authorships": [{"author": {"display_name": "A. Researcher"}}],
    "primary_location": {"landing_page_url": "https://example.edu/paper", "is_oa": True},
    "open_access": {"is_oa": True},
    "cited_by_count": 42,
    "abstract_inverted_index": {"DO_NOT_REDISPLAY": [0]},
    "best_oa_location": {"pdf_url": "https://example.edu/private.pdf"},
}


def test_ssrn_reference_is_link_only_and_validated():
    item = ssrn_reference("1234567")
    assert item["url"] == "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1234567"
    for bad_id in ["abc", "../123", "1?download=true", "0", "9999999999999"]:
        with pytest.raises(ValueError):
            ssrn_reference(bad_id)


def test_doi_validation_blocks_injection():
    assert normalize_doi("https://doi.org/10.1234/ABC.xyz") == "10.1234/ABC.xyz"
    for bad_doi in ["https://ssrn.com/file", "10.1234/test?x=1", "../abc", "10.abc/x", ""]:
        with pytest.raises(ValueError):
            normalize_doi(bad_doi)


@pytest.mark.asyncio
async def test_openalex_only_allowed_host_and_metadata_only():
    requested = []

    def mock_response(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        assert request.url.host == "api.openalex.org"
        assert request.url.path == "/works"
        return httpx.Response(200, json={"results": [OPENALEX_RECORD]})

    api = MetadataAPI(transport=httpx.MockTransport(mock_response))
    papers = await api.search("post earnings drift", limit=3)
    assert len(papers) == 1
    paper = papers[0].public_dict()
    assert paper["title"] == "A Study of Momentum"
    assert paper["doi"] == "10.1234/test.paper"
    assert paper["open_access_landing_page"] == "https://example.edu/paper"
    assert not any("abstract" in key.lower() or "pdf" in key.lower() for key in paper)
    assert "DO_NOT_REDISPLAY" not in str(paper)
    assert len(requested) == 1
    # API response is cached (and still no paper-host requests).
    assert len(await api.search("post earnings drift", limit=3)) == 1
    assert len(requested) == 1


@pytest.mark.asyncio
async def test_crossref_citation_only_no_full_text():
    def mock_response(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.crossref.org"
        assert request.url.path == "/works"
        assert request.url.params["mailto"] == "researcher@example.edu"
        return httpx.Response(200, json={"message": {"items": [{
            "DOI": "10.5555/test123",
            "title": ["Finance Working Paper"],
            "author": [{"given": "J", "family": "Smith"}],
            "published": {"date-parts": [[2021, 10, 1]]},
            "abstract": "Restricted abstract text not output",
            "link": [{"URL": "https://papers.ssrn.com/unsafe.pdf"}],
        }]}})

    api = MetadataAPI(crossref_email="researcher@example.edu", transport=httpx.MockTransport(mock_response))
    paper = (await api.search("Finance Working Paper", provider="crossref"))[0]
    data = paper.public_dict()
    assert data["title"] == "Finance Working Paper"
    assert data["landing_page"] == "https://doi.org/10.5555/test123"
    assert "Restricted abstract" not in str(data)
    assert "ssrn.com/unsafe" not in str(data)


@pytest.mark.asyncio
async def test_limit_and_source_controls():
    api = MetadataAPI(transport=httpx.MockTransport(lambda _: pytest.fail("must not fetch")))
    for bad_limit in [0, 21, True]:
        with pytest.raises(ValueError):
            await api.search("momentum", limit=bad_limit)
    with pytest.raises(ValueError):
        await api.search("x")
    with pytest.raises(ValueError):
        await api.search("momentum", provider="ssrn")
    with pytest.raises(ValueError):
        await api._get("ssrn", "/works", {})
    with pytest.raises(ValueError):
        await api._get("openalex", "//papers.ssrn.com", {})


@pytest.mark.asyncio
async def test_redirect_not_followed_to_ssrn():
    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://papers.ssrn.com/secret"})

    api = MetadataAPI(transport=httpx.MockTransport(respond))
    with pytest.raises(httpx.HTTPStatusError):
        await api.search("momentum")


@pytest.mark.asyncio
async def test_oa_link_is_non_authorizing():
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.openalex.org"
        return httpx.Response(200, json={"results": [OPENALEX_RECORD]})

    api = MetadataAPI(transport=httpx.MockTransport(respond))
    paper = await api.by_doi("10.1234/test.paper", provider="openalex")
    assert paper is not None and paper.is_open_access
    assert paper.open_access_landing_page == "https://example.edu/paper"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openalex", "crossref"])
async def test_cache_keeps_only_allowlisted_metadata(provider):
    restricted = {
        "abstract": "PRIVATE_ABSTRACT_SENTINEL",
        "fulltext": "PRIVATE_FULLTEXT_SENTINEL",
        "pdf_url": "https://example.org/PRIVATE_PDF_SENTINEL.pdf",
    }
    if provider == "openalex":
        record = {
            **OPENALEX_RECORD,
            **restricted,
            "authorships": [{"author": {"display_name": "A. Researcher", **restricted}}],
            "primary_location": {
                "landing_page_url": "https://example.edu/paper", **restricted,
            },
        }
        payload = {"results": [record], "meta": restricted}
    else:
        payload = {"message": {
            "DOI": "10.1234/test.paper", "title": ["A Study of Momentum"],
            "author": [{"given": "A", "family": "Researcher", **restricted}],
            **restricted,
        }}
    api = MetadataAPI(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    paper = await api.by_doi("10.1234/test.paper", provider=provider)
    assert paper is not None
    assert paper.title == "A Study of Momentum"
    assert "PRIVATE_" not in repr(api._cache)
    assert "PRIVATE_" not in repr(paper.public_dict())


class CountingStream(httpx.AsyncByteStream):
    def __init__(self):
        self.chunks_read = 0
        self.closed = False

    async def __aiter__(self):
        for _ in range(8):
            self.chunks_read += 1
            yield b" " * 600_000

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_response_size_limit_stops_stream_before_full_body_is_buffered():
    stream = CountingStream()
    api = MetadataAPI(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, stream=stream),
    ))
    with pytest.raises(ValueError, match="size limit"):
        await api.search("momentum")
    assert stream.chunks_read <= 4
    assert stream.closed
    assert not api._cache


@pytest.mark.asyncio
async def test_large_content_length_is_rejected_without_reading_body():
    stream = CountingStream()
    api = MetadataAPI(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"Content-Length": "4800000"}, stream=stream),
    ))
    with pytest.raises(ValueError, match="size limit"):
        await api.search("momentum")
    assert stream.chunks_read == 0
    assert stream.closed


@pytest.mark.asyncio
async def test_compressed_response_is_rejected_before_decompression():
    class GzipStream(CountingStream):
        async def __aiter__(self):
            self.chunks_read += 1
            yield gzip.compress(b'{"results": []}')

    stream = GzipStream()

    def respond(request):
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=stream)

    api = MetadataAPI(transport=httpx.MockTransport(respond))
    with pytest.raises(ValueError, match="Compressed"):
        await api.search("momentum")
    assert stream.chunks_read == 0
    assert stream.closed
    assert not api._cache


@pytest.mark.asyncio
async def test_metadata_requests_negotiate_uncompressed_json():
    requested_encoding = []

    def respond(request):
        requested_encoding.append(request.headers["Accept-Encoding"])
        return httpx.Response(200, json={"results": []})

    api = MetadataAPI(transport=httpx.MockTransport(respond))
    assert await api.search("momentum") == []
    assert requested_encoding == ["identity"]


@pytest.mark.asyncio
async def test_cached_metadata_expires_and_is_refetched(monkeypatch):
    clock = [100.0]
    calls = []

    async def no_wait(_):
        pass

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(providers.asyncio, "sleep", no_wait)

    def respond(_):
        calls.append(True)
        return httpx.Response(200, json={"results": [
            {**OPENALEX_RECORD, "cited_by_count": len(calls)},
        ]})

    api = MetadataAPI(transport=httpx.MockTransport(respond))
    assert (await api.search("momentum"))[0].cited_by_count == 1
    clock[0] += 899
    assert (await api.search("momentum"))[0].cited_by_count == 1
    clock[0] += 2
    assert (await api.search("momentum"))[0].cited_by_count == 2


@pytest.mark.asyncio
async def test_cache_eviction_keeps_memory_bounded(monkeypatch):
    async def no_wait(_):
        pass

    monkeypatch.setattr(providers.asyncio, "sleep", no_wait)
    calls = []

    def respond(request):
        calls.append(request.url.params["search"])
        return httpx.Response(200, json={"results": []})

    api = MetadataAPI(transport=httpx.MockTransport(respond))
    for index in range(129):
        await api.search(f"query {index}")
    await api.search("query 0")
    assert calls.count("query 0") == 2
    assert len(api._cache) <= 128


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize("retry_after", ["30", "Thu, 01 Jan 2099 00:00:00 GMT"])
async def test_long_retry_after_fails_without_retrying_early(status, retry_after, monkeypatch):
    requests = []
    sleeps = []

    async def no_wait(delay):
        sleeps.append(delay)

    monkeypatch.setattr(providers.asyncio, "sleep", no_wait)

    def respond(request):
        requests.append(request)
        return httpx.Response(status, headers={"Retry-After": retry_after})

    api = MetadataAPI(transport=httpx.MockTransport(respond))
    with pytest.raises(ValueError, match="retry|Retry"):
        await api.search("momentum")
    assert len(requests) == 1
    assert not sleeps


@pytest.mark.asyncio
async def test_short_retry_after_is_honored_before_success(monkeypatch):
    calls = []
    sleeps = []

    async def no_wait(delay):
        sleeps.append(delay)

    monkeypatch.setattr(providers.asyncio, "sleep", no_wait)

    def respond(_):
        calls.append(True)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"results": [OPENALEX_RECORD]})

    api = MetadataAPI(transport=httpx.MockTransport(respond))
    assert len(await api.search("momentum")) == 1
    assert len(calls) == 2
    assert any(delay >= 1 for delay in sleeps)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/works-extra", "/works/../secrets", "/works#fragment", "/works\\evil"])
async def test_only_exact_supported_endpoints_can_be_fetched(endpoint):
    api = MetadataAPI(transport=httpx.MockTransport(lambda _: pytest.fail("must not fetch")))
    with pytest.raises(ValueError):
        await api._get("openalex", endpoint, {})
    with pytest.raises(ValueError):
        await api._get("crossref", endpoint, {})


@pytest.mark.asyncio
@pytest.mark.parametrize("doi", ["10.1234/test,publication_year:2025", "10.1234/test|https://doi.org/10.9999/other"])
async def test_openalex_doi_lookup_rejects_filter_operators(doi):
    api = MetadataAPI(transport=httpx.MockTransport(lambda _: pytest.fail("must not fetch")))
    with pytest.raises(ValueError, match="DOI"):
        await api.by_doi(doi, provider="openalex")


@pytest.mark.asyncio
async def test_openalex_doi_lookup_does_not_return_a_different_work():
    api = MetadataAPI(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"results": [OPENALEX_RECORD]}),
    ))
    assert await api.by_doi("10.1234/different", provider="openalex") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,payload", [
    ("openalex", {"results": {"unexpected": "object"}}),
    ("openalex", {"results": ["unexpected string"]}),
    ("crossref", {"message": []}),
    ("crossref", {"message": {"items": {"unexpected": "object"}}}),
    ("crossref", {"message": {"items": ["unexpected string"]}}),
])
async def test_malformed_record_collections_raise_controlled_errors(provider, payload):
    api = MetadataAPI(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=payload),
    ))
    with pytest.raises(ValueError, match="metadata API response"):
        await api.search("momentum", provider=provider)
    assert not api._cache


@pytest.mark.asyncio
async def test_malformed_crossref_optional_fields_do_not_raise_raw_tracebacks():
    api = MetadataAPI(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"message": {
            "DOI": "10.1234/test.paper", "title": ["Valid Title"],
            "published": "malformed date", "author": 123,
        }}),
    ))
    paper = await api.by_doi("10.1234/test.paper")
    assert paper is not None
    assert paper.title == "Valid Title"
    assert paper.authors == []
    assert paper.year is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openalex", "crossref"])
async def test_malformed_bibliographic_objects_are_not_stringified_into_metadata(provider):
    restricted = {"abstract": "PRIVATE_ABSTRACT_SENTINEL"}
    if provider == "openalex":
        payload = {"results": [{
            "id": restricted, "title": [restricted], "doi": "10.1234/test.paper",
            "authorships": [{"author": {"display_name": restricted}}],
        }, {
            "title": restricted, "authorships": "malformed authors",
        }]}
    else:
        payload = {"message": {"items": [{
            "DOI": "10.1234/test.paper", "title": [restricted],
            "author": [{"given": restricted, "family": [restricted]}],
        }, {
            "title": restricted, "author": "malformed authors",
        }]}}
    api = MetadataAPI(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=payload),
    ))
    papers = await api.search("momentum", provider=provider)
    assert len(papers) == 2
    assert all(paper.title == "Untitled" and paper.authors == [] for paper in papers)
    assert "PRIVATE_" not in repr(api._cache)
    assert "PRIVATE_" not in repr([paper.public_dict() for paper in papers])


@pytest.mark.asyncio
async def test_openalex_key_uses_bearer_header_only_on_openalex():
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"message": {"items": []}})

    api = MetadataAPI(openalex_api_key="test-key", transport=httpx.MockTransport(respond))
    await api.search("momentum")
    await api.search("momentum", provider="crossref")
    assert requests[0].headers["Authorization"] == "Bearer test-key"
    assert "test-key" not in str(requests[0].url)
    assert "Authorization" not in requests[1].headers
    assert "test-key" not in repr(api._cache)


@pytest.mark.asyncio
async def test_crossref_can_lookup_doi_with_filter_punctuation_as_escaped_path():
    def respond(request):
        assert request.url.host == "api.crossref.org"
        assert request.url.raw_path == b"/works/10.1234%2Fa%2Cb%7Cc"
        return httpx.Response(200, json={"message": {
            "DOI": "10.1234/a,b|c", "title": ["Valid DOI with punctuation"],
        }})

    api = MetadataAPI(transport=httpx.MockTransport(respond))
    paper = await api.by_doi("10.1234/a,b|c")
    assert paper is not None and paper.doi == "10.1234/a,b|c"
