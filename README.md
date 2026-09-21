# projectkoios-api

FastAPI HTTP interface for Project Koios.

Repository routing is documented in `projectkoios-bootstrap/maps/repositories.md`.

## Local citation review

The API exposes a human citation-review queue at `/citation-reviews`. It reads
a private review bundle and writes only explicit review decisions; it does not
edit manuscripts.

Default local paths are:

- `~/.local/share/projectkoios/citation-review/bundle.json`
- `~/.local/share/projectkoios/citation-review/decisions.sqlite3`
- `~/projectkoios/assets/references/ksdft2effmass/` for whitelisted source PDFs

The decision database is created with `0600` permissions. Source requests are
restricted to filenames already present in the review bundle.
