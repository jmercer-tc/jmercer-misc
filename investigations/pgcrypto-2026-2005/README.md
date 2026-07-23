# pgcrypto — CVE-2026-2005

## Overview

Tracking exposure to **CVE-2026-2005**, a heap buffer overflow in PostgreSQL's
`pgcrypto` extension (`pgp_parse_pubenc_sesskey()`), CVSS 8.8. An authenticated
attacker who can supply ciphertext to a pgcrypto decryption function
(`pgp_pub_decrypt` / `pgp_sym_decrypt`) can write past a fixed-size buffer on
the backend heap, with a mechanical path to RCE as the OS user running
PostgreSQL.

Reference: https://www.postgresql.org/support/security/CVE-2026-2005

## Affected versions

Anything before:

| Major | Patched minor |
|---|---|
| 14 | 14.21 |
| 15 | 15.16 |
| 16 | 16.12 |
| 17 | 17.8 |
| 18 | 18.2 |

Patched upstream 2026-02-12. The flaw has existed since pgcrypto was
contributed in 2005; exploitability requires pgcrypto to be installed and
reachable with attacker-controlled ciphertext.

## What's in this folder

Two general-purpose, standalone CrowdStrike Falcon scripts (each embeds its
own copy of the API plumbing -- no shared dependencies between them, so
either can be copied elsewhere on its own):

- `cs_cve_scan.py` — lists all servers Falcon Spotlight currently reports as
  vulnerable to a given CVE (open/reopened findings by default; use
  `--include-closed` for everything). For this investigation:
  `./cs_cve_scan.py CVE-2026-2005`
- `cs_app_scan.py` — lists all servers running an application whose name
  matches one or more regexes, via Falcon Discover's application inventory.
  For this investigation:
  `./cs_app_scan.py 'postgresql(-[0-9]*)?'`

Neither script does its own version-vs-patched-release comparison — `cs_cve_scan.py`
depends entirely on Falcon Spotlight's own content having ingested
CVE-2026-2005 for this tenant, and `cs_app_scan.py` just inventories installs;
cross-reference `cs_app_scan.py`'s reported versions against the patched-minor
table above by hand.

- `falcon.rc` — copy of the RTR scripts' credential helper. Prompts
  interactively for the Falcon API client ID/secret and exports them into the
  shell; nothing is written to disk.

This is an **inventory/detection tooling only** — nothing here contains,
uses, or references exploit code, and none of it makes any changes to any
host.

## Running it

```bash
source ./falcon.rc   # prompts for API creds, exports FALCON_CLIENT_ID/SECRET

./cs_cve_scan.py CVE-2026-2005 --out vulnerable_hosts.csv
./cs_app_scan.py 'postgresql(-[0-9]*)?' --out postgres_hosts.csv
```

Both assume `FALCON_CLIENT_ID`/`FALCON_CLIENT_SECRET` are already scoped to
the CID you want to query (e.g. a child CID API client in a Flight Control
setup) — neither script has a `--cid` option. Requires `pip install requests`.

`cs_cve_scan.py` needs the `Spotlight Vulnerabilities: READ` scope;
`cs_app_scan.py` needs `Discover (Assets): READ`.

## Open items

- Confirm Falcon Spotlight's vulnerability content has ingested
  CVE-2026-2005 in this tenant — `cs_cve_scan.py` only finds what Spotlight
  has already correlated.
- `cs_cve_scan.py`'s open/reopened-only default filter (`status:['open','reopened']`)
  hasn't been confirmed against a live tenant response yet — if it 400s, the
  error message will say exactly what's wrong.
- Cross-reference `cs_app_scan.py`'s reported PostgreSQL versions against the
  patched-minor table above manually (it doesn't do CVE classification
  itself).
- Once affected hosts are identified, prioritize upgrading to the patched
  minor release; there's no config-level mitigation since the bug is in the
  C code itself.
