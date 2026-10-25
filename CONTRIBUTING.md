# Contributing

Contributions should preserve the access boundary described in [RIGHTS.md](docs/RIGHTS.md). The repository is named `ssrn-mcp`; the Python package remains `quant-paper-mcp`. Both command names start the same server.

## Local checks

Use Python 3.11 or newer:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
```

Tests must use mocked transports or synthetic fixtures. Do not query SSRN or Elsevier to validate a contribution, and do not commit real API keys, `.env` files, provider response dumps, abstracts, or paper files.

## Changes to review carefully

- Keep outbound requests on the fixed OpenAlex/Crossref API origins, with redirects disabled. Do not add SSRN endpoints, URL fetch tools, login/session handling, browser automation, or downloads.
- Return only the selected bibliography, indicators, and manual links from providers. Do not expose raw provider responses or dedicated abstract, full-text, or PDF fields. Landing-page fields are unverified; do not claim they can never lead to downloads. Use synthetic text to test that parsers discard extra fields before caching.
- Keep the checklist separate from fetched content: only user-authored or expressly licensed notes, with no fetching or claim that the tool verifies permissions.
- Keep query/result limits and bounded retries/cache. Do not add bulk harvests, SSRN polling, text indexes, or automatic paper-analysis features.
- Preserve the unofficial presentation and do not add SSRN/Elsevier logos or imply endorsement.

For a proposed change in scope, explain the use case and cite the precise license or written authorization first. A public URL or open-access flag alone does not establish the rights needed for an automated workflow.

Keep the English and Korean READMEs consistent when changing installation, configuration, or tools. Contributions are provided under the repository's MIT license; third-party material needs its own valid permissions.
