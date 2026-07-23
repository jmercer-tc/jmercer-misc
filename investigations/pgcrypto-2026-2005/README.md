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

- `crowdstrike_postgres_cve_2026_2005_scan.py` — queries Falcon Discover for
  hosts with PostgreSQL installed and their reported versions, cross-checks
  Falcon Spotlight for any existing CVE-2026-2005 matches, and flags anything
  below the patched thresholds above. Writes a CSV report.

This is an **inventory/detection tool only** — it does not contain, use, or
reference exploit code, and it makes no changes to any host.

## Running it

```bash
source ~/wip/secops-scripts/crowdstrike/rtr/falcon.rc   # prompts for API creds, exports FALCON_CLIENT_ID/SECRET
python3 crowdstrike_postgres_cve_2026_2005_scan.py --out report.csv
```

Requires a Falcon API client with `Hosts: READ`, `Discover (Assets): READ`,
and `Spotlight Vulnerabilities: READ` scopes, and `pip install requests`.

## Open items

- Confirm Falcon Spotlight's vulnerability content has ingested
  CVE-2026-2005 in this tenant (direct Spotlight matches depend on it).
- Check any `UNKNOWN_VERSION` rows in the CSV manually — Discover's reported
  application version string doesn't always parse cleanly.
- Once affected hosts are identified, prioritize upgrading to the patched
  minor release; there's no config-level mitigation since the bug is in the
  C code itself.
