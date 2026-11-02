# Signalforge

A local-first, open-source starter for researching publicly available business contacts. Enter a public site and scan up to five same-origin pages. The app checks `robots.txt`, looks for contact information in public HTML and Person JSON-LD, displays a source URL for each result, and exports CSV. It has a responsive interface with light and dark modes.

## Run

Requires Python 3.10 or newer; no third-party packages.

```sh
python3 server.py
```

Open <http://localhost:8765>. Optionally set `PORT=8888` before running. Stop with Ctrl+C. The server binds only to localhost. Tests: `python3 -m unittest discover -s tests -v`.

## What it does today

- Fetches the provided URL and links on the **same origin**, at most five HTML pages and 1 MB per response, with at least a one-second delay between page requests.
- Checks robots.txt before crawling; missing (404) means no stated rules, unavailable or redirected robots means stop. Its conservative policy blocks any matching Disallow in any user-agent group even when an Allow might override it; this is not a full RFC 9309 implementation and may skip permissible pages. It does not follow redirects, render JavaScript, authenticate, access private networks, or bypass blocks.
- Extracts public email addresses and phone candidates separately, and person records only from explicit `Person` JSON-LD. Unassigned contacts are **not** attributed to a person. Structured-data results can be inaccurate or stale. Some page elements are inaccessible to this basic parser; results may contain false positives or miss information.
- Does not infer gender or scrape it. Does not guarantee a name, profession, phone, or email. No built-in business data, integrations, AI enrichment, search engine, scheduling, database, account system, or email sending. Data remains in the browser's current session until exported; theme preference is stored locally.
- URL handling resolves hosts and connects to a validated public IP, disallows IP literals/nonstandard ports, and does not follow redirects. API is localhost-only with origin and host checks. These measures are defense in depth, not a production security review.

## Responsible use

Scan only sites you are authorized to access and check applicable site terms and privacy/marketing laws. Respect opt-outs and avoid collecting sensitive or unnecessary personal information. Robots rules are not permission to collect or reuse data. This starter has no consent, deletion, opt-out, retention, or outreach-compliance management; build those before real-world deployment. Never expose this development server to the internet.

## Project roadmap

1. **Harden foundations:** security review, authentication, isolated workers, SSRF protection tested at network layer, quotas, observability, accessibility, and a compliant deployment model.
2. **Source management:** permission-aware connectors and imports; source provenance, policy checks, metadata and data deletion/retention controls.
3. **Lead workspace:** durable storage, organizations and roles, deduplication with review, filtering, and import/export.
4. **Enrichment:** opt-in integrations with licensed data providers, field-level provenance and freshness; never infer protected attributes.
5. **Workflow:** CRM connectors, task management, outreach only with lawful basis, suppression and unsubscribe support.
6. **Community:** contributor guidelines, automated checks, issue templates, releases, and public hosting once the repository and ownership are chosen.

## License

Original code in this project is available under the MIT License; see [LICENSE](LICENSE). Dependencies and third-party content remain under their own terms. Website content is not relicensed by this project.
