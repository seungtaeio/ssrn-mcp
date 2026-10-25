# ssrn-mcp

An **unofficial** local MCP server for scholarly bibliography from OpenAlex and Crossref, SSRN links for manual browsing, and a quant-research checklist from your own authorized notes. The Python package is `quant-paper-mcp`; both `ssrn-mcp` and `quant-paper-mcp` start the server.

[한국어](README.ko.md) · [Rights and access policy](docs/RIGHTS.md) · [Contributing](CONTRIBUTING.md)

This project is not affiliated with or endorsed by SSRN, Elsevier, OpenAlex, or Crossref. It uses no SSRN/Elsevier logo.

## Scope

- Search official OpenAlex/Crossref metadata APIs and look up a DOI.
- Return titles, authors, years, DOI/provider identifiers, citation/OA indicators where available, and manual landing-page links.
- Format an SSRN public abstract-page link from an ID you supply, without visiting or verifying it.
- Create a research checklist from user-authored notes or notes with separate, verified permission for the intended AI use. This tool returns the supplied notes locally; it does not retrieve a paper.
- Make no requests to SSRN or Elsevier. There is no SSRN search, scraper, login, PDF download, bulk harvest, or automatic paper-text analysis.
- Exclude abstracts and full text from provider-derived tool outputs. Upstream API responses may include additional fields; parsers discard unexposed fields.

The official [SSRN Terms of Use](https://www.ssrn.com/index.cfm/en/terms-of-use/) prohibit automated queries to SSRN and limit content reuse, including certain AI uses. Reviewed on 2026-10-25; the page footer displayed “Last updated June 2017.” This server adopts the narrower scope above. It does not establish permission for every downstream use of metadata, notes, or linked papers. See [RIGHTS.md](docs/RIGHTS.md) for relevant sections and implementation limits.

## Install

Requires Python 3.11+, internet access to the metadata providers, and a local MCP client.

```bash
git clone https://github.com/seungtaeio/ssrn-mcp.git
cd ssrn-mcp
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows, activate with `.venv\Scripts\activate`.

Provider settings:

- `OPENALEX_API_KEY` — optional. OpenAlex permits basic anonymous queries; a free key raises the available budget. See [OpenAlex authentication](https://help.openalex.org/api/authentication/).
- `CROSSREF_EMAIL` — recommended contact email for Crossref's polite pool. See [Crossref metadata access](https://www.crossref.org/documentation/retrieve-metadata/).

Pass settings in the MCP server process environment, as in the example below. [.env.example](.env.example) lists the variables; the server does not automatically load `.env` files. Never commit credentials.

## Connect an MCP client

For a client that accepts an `mcpServers` configuration:

```json
{
  "mcpServers": {
    "ssrn-mcp": {
      "command": "/ABSOLUTE/PATH/TO/ssrn-mcp/.venv/bin/ssrn-mcp",
      "env": {
        "OPENALEX_API_KEY": "",
        "CROSSREF_EMAIL": "you@example.edu"
      }
    }
  }
}
```

Replace the absolute executable path and email. Add an OpenAlex key if desired, or leave it empty. On Windows, use the executable under `.venv\Scripts`. Restart the client after updating its configuration.

The executable uses **stdio** and waits for an MCP client on standard input. It does not open a network port or show an interactive prompt.

## Tools

- `search_papers(query, source, limit)` — search `openalex` or `crossref`; at most 20 results.
- `get_paper_by_doi(doi, source)` — retrieve one paper's bibliography.
- `find_open_access_link(doi)` — return an OpenAlex landing-page link/OA indication; no download.
- `get_ssrn_reference_link(abstract_id)` — format a manual SSRN link; no request.
- `make_quant_research_checklist(paper_title, original_user_notes)` — return checklist questions alongside your own or expressly licensed notes.
- `source_and_rights_policy()` — inspect the access restrictions.

Example requests:

> Search Crossref for five papers about earnings announcement drift and return their titles and DOI links.

> Look up DOI 10.2139/ssrn.1234567 through Crossref. If the external index has no record, report that without visiting SSRN.

> Format an SSRN reference link for abstract ID 1234567 without visiting it.

The DOI above illustrates the SSRN DOI pattern; a corresponding record is not guaranteed. Coverage of SSRN papers depends on the external indexes. A DOI, public link, or OA flag does not grant automated access, redistribution, or AI-use rights. This project does not provide market data, backtesting, or trade execution.

## Development

```bash
python -m pip install -e '.[dev]'
pytest -q
```

Tests use mocked HTTP transports. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) covers the original source code. Third-party metadata, papers, names, and linked materials retain their own rights and terms.
