# pgcrypto CVE-2026-2005 — Session Notes
# Last updated: 2026-07-23

## Overview

Tracking exposure to CVE-2026-2005 (heap buffer overflow in PostgreSQL's
pgcrypto extension, CVSS 8.8) across the fleet using CrowdStrike Falcon
(Spotlight for vulnerability matches, Discover for application inventory).
Work lives on branch `inv-pgcrypto` in this repo, in
`investigations/pgcrypto-2026-2005/`.

## Key Files

- `README.md` — investigation overview, affected-version table, usage.
- `cs_cve_scan.py` — standalone script; lists servers Falcon Spotlight
  currently reports vulnerable to a given CVE (open/reopened by default,
  `--include-closed` for everything). Includes a `vuln_status` column.
- `cs_app_scan.py` — standalone script; lists servers running an application
  matching one or more regexes, via Falcon Discover's application inventory.
  No server-side name filter — fetches the full inventory and filters
  client-side, since arbitrary regexes can't be expressed in FQL.
- `falcon.rc` — interactive credential helper (prompts for Falcon API
  client ID/secret, exports `FALCON_CLIENT_ID`/`FALCON_CLIENT_SECRET`;
  nothing written to disk).
- `cve.txt` — untracked scratch file, real `cs_cve_scan.py` output from the
  user's tenant (see Current State). Left untracked/unstaged deliberately,
  same as an earlier scratch file `tt.txt` from mid-session debugging.

Both scripts embed their own copy of the Falcon API plumbing
(`get_token`, `paginated_query`, `batch_get_entities`, error handling, etc.)
— no shared module between them, by explicit design choice, so either can
be copied elsewhere standalone.

## Current State

- The investigation started as a single combined script
  (`crowdstrike_postgres_cve_2026_2005_scan.py`), which went through several
  rounds of fixes (FQL filter property/limit, package-name noise,
  hostname/host_id resolution via Discover's nested `host` object, `aid`
  column, a `--cve` option with vulnerable-only filtering).
- That combined script was then split into two standalone tools per the
  user's request, and the old file was deleted. Split landed in commit
  `3ec1043` ("Split pgcrypto CVE-2026-2005 scanner into two standalone
  Falcon scripts").
- `cs_cve_scan.py` has been run by the user against their real Falcon
  tenant (output captured in the untracked `cve.txt`) and confirmed
  working end-to-end: real hostnames, `aid`s, and `vuln_status: open` all
  came back correctly for `CVE-2026-2005`. This also confirms the
  `status:['open','reopened']` FQL syntax is valid against a live tenant.
- `cs_app_scan.py` has passed `py_compile`, `--help`, and mock-based smoke
  tests, but has **not yet been run against the real tenant** — the
  `host`/`aid` field extraction from Discover application entities is
  carried over from the combined script's live-debugged version, but hasn't
  been independently re-confirmed live for this standalone script.
- No fleet-wide remediation tracking has started yet — this has been tooling
  development only so far, not yet used to drive patching.

## Decisions Made

- **Standalone scripts, no shared module** — chosen over a shared plumbing
  module so either script can be copied elsewhere independently.
- **Old combined script deleted** rather than kept alongside the new ones.
- **No `--cid` option on either script** — both assume
  `FALCON_CLIENT_ID`/`FALCON_CLIENT_SECRET` in the environment are already
  scoped to the target CID (e.g. a child CID API client in a Flight Control
  setup).
- **Spotlight status filtering defaults to open/reopened only** in
  `cs_cve_scan.py` (`--include-closed` to see everything) — this was our
  (Claude's) recommendation when the user had no preference, since
  "currently vulnerable" is the more useful default for this kind of scan.
- **`cs_app_scan.py` does no CVE/version classification** — it only
  inventories installs; cross-referencing reported versions against a
  patched-minor table is manual, by design, since the version-threshold
  logic in the old combined script was specific to CVE-2026-2005 and
  doesn't generalize.

## Pending / Next Steps

- Run `cs_app_scan.py 'postgresql(-[0-9]*)?'` against the real tenant to
  confirm the Discover `host`/`aid` field extraction live (same way
  `cs_cve_scan.py` was already confirmed).
- Cross-reference `cs_app_scan.py`'s reported PostgreSQL versions against
  the patched-minor table in `README.md` by hand.
- Confirm Falcon Spotlight's vulnerability content has ingested
  CVE-2026-2005 for this tenant if any hosts are unexpectedly absent from
  `cs_cve_scan.py`'s output (it only finds what Spotlight has already
  correlated).
- Once affected hosts are fully identified, prioritize upgrading to the
  patched minor release — no config-level mitigation exists since the bug
  is in the C code itself.

## Technical Reference

- Falcon Discover applications: host info is nested under `app["host"]`
  (fields `id`, `aid`, `hostname`, `os_version`), not a flat field on the
  application entity.
- Falcon Discover applications FQL: filter property is `name` (not
  `application_name`); endpoint's max `limit` is 100 (not 500).
- Falcon Spotlight FQL: `cve.id:'CVE-XXXX-NNNNN'+status:['open','reopened']`
  — `+` is AND, bracketed list is OR-of-values for the same property.
  Confirmed live.
- Spotlight vulnerability status lifecycle: `open`, `reopened`, `closed`,
  `expired`.
- Required Falcon API scopes: `Spotlight Vulnerabilities: READ` for
  `cs_cve_scan.py`, `Discover (Assets): READ` for `cs_app_scan.py`.
- Patched PostgreSQL minors (from `README.md`): 14.21, 15.16, 16.12, 17.8,
  18.2.

## Corrections / Gotchas

- Initial FQL filter used `application_name` as the property name and a
  `limit` of 500 — both wrong; correct property is `name`, max limit is 100.
- hostname/host_id initially showed `UNKNOWN` because the code looked for a
  flat `host_id`/`aid` field on the Discover application entity; the real
  data (confirmed via `--debug` output pasted by the user) has this nested
  under a `host` sub-object instead.
- The `aid` (Falcon Agent ID) is distinct from Discover's own compound
  entity `host_id` (e.g. `"0ea588fee7aa48e6b4ad753d7638fb15_ATDx..."`) —
  both are now surfaced as separate columns to avoid confusing the two.
