# Rights and upstream access policy

Reviewed on **2026-10-25** against the official [SSRN Website Terms of Use](https://www.ssrn.com/index.cfm/en/terms-of-use/). The page footer displayed “Last updated June 2017.” This document describes a conservative implementation boundary, not a legal opinion or a guarantee of compliance for every use.

## Relevant SSRN terms

- **User Representations and Warranties** prohibits software that sends repeated queries and automated queries of any sort to SSRN. The server therefore makes no HTTP requests to SSRN or Elsevier, including search pages, RSS, robots.txt, login, abstract pages, and downloads.
- **Content — Personal Use Only** limits the Services to personal, noncommercial, informational or scholarly use. Its noncommercial exception permits redisplaying an individual document's title, author and/or abstract with a link to its public SSRN abstract page. That exception does not authorize reuse of all or a significant part of the library, a category, or SSRN information. It is not an automated-query exception.
- **Elsevier Ownership and Rights** reserves rights including text and data mining and AI training, subject to the relevant open-access licenses. **Content — Personal Use Only** also restricts derivative works, including those resulting from AI tools, with its stated exceptions. Public visibility alone is not permission for AI use.
- **Linking** permits hyperlinks without implying sponsorship or endorsement. It restricts use of logos and other protected materials and incorporation of SSRN content into another site. This project is unofficial, uses no SSRN/Elsevier logo, and only formats a link from an ID supplied by the user.
- **Extent of Terms** recognizes applicable separate agreements and service-specific terms. Additional rights require checking the actual license or authorization and its scope.

The terms allow some uses under specific conditions. This project's narrower scope does not claim that every abstract use is prohibited, or that every metadata use is permitted.

## Implemented boundary

- Outbound requests use only the fixed OpenAlex and Crossref API origins. Redirects are disabled. There is no generic URL fetcher, browser automation, SSRN session access, or PDF downloader.
- Provider-derived tool results contain selected bibliographic fields, provider identifiers, citation/OA indicators where available, and links for a person to open manually. Dedicated abstract, full-text, and PDF fields are omitted. Landing links are unverified provider data and can lead to downloads; the server never follows them.
- Provider responses can contain additional fields. In particular, a Crossref DOI response can contain an abstract. The parser discards unexposed fields before caching normalized metadata; this is not a claim that the upstream response never contains them. No paper corpus is bundled or written to disk.
- The checklist tool works with the supplied title and user-authored or expressly licensed notes. It returns those notes and checklist questions locally. It does not retrieve content or establish that the supplied notes are authorized for an AI client to process.
- Requests have bounded result counts, query lengths and response size, throttling, retry limits, and a 128-entry metadata cache with a 15-minute lifetime. Long provider retry delays stop the call instead of retrying early. These controls do not create permission for otherwise restricted use.
- There is no bulk harvest/export, SSRN polling, paper-text indexing, summarization, or automatic AI analysis of SSRN paper content.

## Third-party metadata and links

Metadata comes from OpenAlex and Crossref, not from an SSRN crawl. [OpenAlex authentication guidance](https://help.openalex.org/api/authentication/) permits basic anonymous queries and provides API keys for a higher budget. [Crossref metadata guidance](https://www.crossref.org/documentation/retrieve-metadata/) distinguishes reusable bibliographic facts from abstracts, which retain copyright. Provider API policies and applicable content rights still apply; obtaining a field through another provider does not establish unrestricted rights to every field or to an underlying paper.

A DOI, landing-page link, or open-access flag is a discovery aid, not copyright clearance, permission for automated access, or permission for AI processing. The server does not visit those links.

## Contributions and licensing

The [MIT license](../LICENSE) covers this repository's original code. It does not license SSRN/Elsevier names, provider metadata, abstracts, papers, or linked materials. Follow [CONTRIBUTING.md](../CONTRIBUTING.md) when proposing changes to the access boundary. Any broader integration needs a separate review grounded in the exact written authorization and permitted workflow.
