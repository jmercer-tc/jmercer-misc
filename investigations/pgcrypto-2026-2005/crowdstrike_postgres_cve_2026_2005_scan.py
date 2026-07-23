#!/usr/bin/env python3
"""
crowdstrike_postgres_cve_2026_2005_scan.py

Purpose
-------
Query the CrowdStrike Falcon API to build an inventory of hosts running
PostgreSQL (via Falcon Discover's Applications inventory), cross-check them
against Falcon Spotlight's vulnerability data for CVE-2026-2005 (pgcrypto
heap buffer overflow), and flag which hosts are running a version of
PostgreSQL that predates the patched releases:

    18.2, 17.8, 16.12, 15.16, 14.21

Background: CVE-2026-2005 is a heap buffer overflow in pgcrypto's
pgp_parse_pubenc_sesskey(), CVSS 8.8, patched upstream 2026-02-12.
See: https://www.postgresql.org/support/security/CVE-2026-2005

This script does NOT contain, use, or reference exploit code. It only
inventories asset/version data and does version comparison.

Requirements
------------
    pip install requests

Auth / Scopes
-------------
Create an API client in the Falcon console under:
    Support and resources > API clients and keys

Required scopes (read-only). Depending on console version these may be
labeled either the long form or the short form shown in parentheses:
    - Hosts: READ
    - Discover (Assets): READ            (may show simply as "Assets")
    - Spotlight Vulnerabilities: READ    (may show simply as "Vulnerabilities")

These scopes are gated by module licensing and may not appear at all when
creating a client under a parent CID in a Flight Control setup — if so, try
creating the client directly under the specific child CID instead. A client
created on a child CID is scoped to that CID's own data automatically; no
member_cid parameter is needed on any of the API calls below.

Provide credentials via environment variables (never hardcode them). A copy
of the RTR scripts' falcon.rc lives alongside this file for convenience — it
prompts interactively and exports the vars; nothing is ever written to disk:

    source ./falcon.rc
    export FALCON_BASE_URL="https://api.crowdstrike.com"   # see region table below

Region base URLs:
    us-1      https://api.crowdstrike.com
    us-2      https://api.us-2.crowdstrike.com
    eu-1      https://api.eu-1.crowdstrike.com
    us-gov-1  https://api.laggar.gcw.crowdstrike.com

Usage
-----
    python3 crowdstrike_postgres_cve_2026_2005_scan.py [--out report.csv] [--cid CID]

--cid CID   Optional. The CrowdStrike Customer ID (CID) you expect these
            credentials to be scoped to (find it in the Falcon console under
            Support and resources > API clients and keys, listed next to the
            client, or under Host setup and management > Deployment). If
            given, the script reads the 'cid' claim out of the OAuth2 access
            token and refuses to proceed if it doesn't match — this catches
            the case where credentials from the wrong CID (e.g. the parent
            CID in a Flight Control setup) get used by mistake, and prints
            what to create instead.

Output
------
Prints a summary table to stdout and writes a CSV report with columns:
    hostname, host_id, os_version, application_name, application_version,
    parsed_major, parsed_minor, patched_minor_for_major, status, source

`status` is one of: VULNERABLE, PATCHED, UNKNOWN_VERSION, SPOTLIGHT_MATCH
"""

import base64
import binascii
import csv
import json
import os
import re
import sys
import argparse
import requests

# Minimum PATCHED minor version per PostgreSQL major branch for CVE-2026-2005.
# A host is vulnerable if its installed minor version is LOWER than this
# value for its major branch.
PATCHED_MINOR_BY_MAJOR = {
    14: 21,
    15: 16,
    16: 12,
    17: 8,
    18: 2,
}

CVE_ID = "CVE-2026-2005"

REQUIRED_SCOPES_TEXT = (
    "  - Hosts: READ\n"
    "  - Discover (Assets): READ         (may show simply as \"Assets\")\n"
    "  - Spotlight Vulnerabilities: READ (may show simply as \"Vulnerabilities\")"
)


class FalconAuthError(Exception):
    """Credentials are missing, invalid, or lack a required API scope."""


def _describe_falcon_error(resp) -> str:
    """Pull the human-readable error message(s) out of a Falcon API error
    body, if present. Falls back to the raw response text."""
    try:
        body = resp.json()
        errors = body.get("errors") or []
        if errors:
            return "; ".join(e.get("message", str(e)) for e in errors)
    except ValueError:
        pass
    return (resp.text or "").strip()[:300] or resp.reason


def _check_response(resp, context: str, required_scope: str = None):
    """Raise a clear, actionable FalconAuthError for auth/permission failures;
    otherwise fall back to requests' normal HTTPError for other failures."""
    if resp.status_code == 401:
        raise FalconAuthError(
            f"Authentication failed while {context} (HTTP 401): {_describe_falcon_error(resp)}. "
            "Check that FALCON_CLIENT_ID / FALCON_CLIENT_SECRET are correct and that the API "
            "client hasn't been disabled, deleted, or expired in the Falcon console, and that "
            "FALCON_BASE_URL matches the cloud region the client was created in."
        )
    if resp.status_code == 403:
        scope_hint = f" This endpoint requires the '{required_scope}' API scope — add it to the API client in Falcon under Support and resources > API clients and keys." if required_scope else ""
        raise FalconAuthError(
            f"Permission denied while {context} (HTTP 403): {_describe_falcon_error(resp)}.{scope_hint}"
        )
    resp.raise_for_status()


def get_token(base_url: str, client_id: str, client_secret: str) -> str:
    resp = requests.post(
        f"{base_url}/oauth2/token",
        data={"client_id": client_id, "client_secret": client_secret},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    _check_response(resp, "requesting an OAuth2 token")
    return resp.json()["access_token"]


def _decode_jwt_payload(token: str) -> dict:
    """Best-effort decode of a JWT's payload WITHOUT verifying its signature.
    This is only ever used to read the 'cid' claim back out of our own,
    already-authenticated access token for a sanity check against --cid — it
    is never used to trust or authorize anything."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("access token is not in JWT format")
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
    return json.loads(payload_bytes)


def resolve_cid_from_token(token: str):
    """Return the CID the given access token is scoped to, or None if it
    can't be determined (token isn't a JWT, or carries no recognizable CID
    claim)."""
    try:
        payload = _decode_jwt_payload(token)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        return None
    for key in ("cid", "ccid", "customer_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def paginated_query(base_url, token, query_path, params=None, limit=500, required_scope=None):
    """Yield IDs from a Falcon 'queries' endpoint, handling offset pagination."""
    params = dict(params or {})
    params["limit"] = limit
    offset = 0
    while True:
        params["offset"] = offset
        resp = requests.get(
            f"{base_url}{query_path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        _check_response(resp, f"querying {query_path}", required_scope)
        body = resp.json()
        ids = body.get("resources", [])
        for _id in ids:
            yield _id
        pagination = body.get("meta", {}).get("pagination", {})
        total = pagination.get("total", 0)
        offset += len(ids)
        if not ids or offset >= total:
            break


def batch_get_entities(base_url, token, entities_path, ids, id_param="ids", batch_size=100, required_scope=None):
    """GET entity details in batches of up to batch_size IDs."""
    results = []
    for i in range(0, len(ids), batch_size):
        chunk = ids[i:i + batch_size]
        resp = requests.get(
            f"{base_url}{entities_path}",
            headers={"Authorization": f"Bearer {token}"},
            params={id_param: chunk},
            timeout=30,
        )
        _check_response(resp, f"fetching {entities_path}", required_scope)
        results.extend(resp.json().get("resources", []))
    return results


def discover_postgres_applications(base_url, token):
    """
    Use Falcon Discover's Applications inventory to find hosts with
    PostgreSQL installed, and pull the reported version string.
    """
    scope = "Discover (Assets): READ"
    query_params = {"filter": "application_name:*'*ostgre*'"}
    app_ids = list(paginated_query(base_url, token, "/discover/queries/applications/v1", query_params, required_scope=scope))
    if not app_ids:
        return []

    apps = batch_get_entities(base_url, token, "/discover/entities/applications/v1", app_ids, required_scope=scope)

    # Resolve host_id -> hostname/os via Discover Hosts entities
    host_ids = sorted({a.get("host_id") for a in apps if a.get("host_id")})
    hosts_by_id = {}
    if host_ids:
        hosts = batch_get_entities(base_url, token, "/discover/entities/hosts/v1", host_ids, required_scope="Hosts: READ / Discover (Assets): READ")
        hosts_by_id = {h.get("id"): h for h in hosts}

    rows = []
    for app in apps:
        host = hosts_by_id.get(app.get("host_id"), {})
        rows.append({
            "hostname": host.get("hostname", "UNKNOWN"),
            "host_id": app.get("host_id", "UNKNOWN"),
            "os_version": host.get("os_version", ""),
            "application_name": app.get("name", ""),
            "application_version": app.get("version", ""),
            "source": "discover_applications",
        })
    return rows


def spotlight_cve_matches(base_url, token):
    """
    Cross-check Falcon Spotlight's vulnerability data directly for
    CVE-2026-2005, in case Falcon's own content has already correlated
    hosts to this CVE. Depends on Spotlight's content coverage as of
    when you run this.
    """
    scope = "Spotlight Vulnerabilities: READ"
    query_params = {"filter": f"cve.id:'{CVE_ID}'"}
    try:
        vuln_ids = list(paginated_query(base_url, token, "/spotlight/queries/vulnerabilities/v1", query_params, required_scope=scope))
        if not vuln_ids:
            return []
        vulns = batch_get_entities(base_url, token, "/spotlight/entities/vulnerabilities/v2", vuln_ids, required_scope=scope)
    except FalconAuthError as e:
        print(f"[warn] {e}\n[warn] Skipping Spotlight cross-check; Discover-based results below are unaffected.", file=sys.stderr)
        return []
    except requests.HTTPError as e:
        print(f"[warn] Spotlight query failed ({e}); skipping Spotlight cross-check.", file=sys.stderr)
        return []

    rows = []
    for v in vulns:
        host = v.get("host_info", {}) or {}
        app = v.get("app", {}) or {}
        rows.append({
            "hostname": host.get("hostname", "UNKNOWN"),
            "host_id": host.get("host_id", "UNKNOWN"),
            "os_version": host.get("os_version", ""),
            "application_name": app.get("product_name_version", app.get("product_name", "")),
            "application_version": app.get("version", ""),
            "source": "spotlight_vulnerabilities",
        })
    return rows


def parse_pg_version(version_str: str):
    """Extract (major, minor) from a version string like '14.10' or
    'PostgreSQL 16.3 on x86_64...'. Returns (None, None) if unparseable."""
    if not version_str:
        return None, None
    match = re.search(r"\b(1[4-9]|[2-9]\d)\.(\d+)\b", version_str)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def classify(row):
    major, minor = parse_pg_version(row.get("application_version", ""))
    row["parsed_major"] = major
    row["parsed_minor"] = minor

    if row["source"] == "spotlight_vulnerabilities":
        row["status"] = "SPOTLIGHT_MATCH"
        row["patched_minor_for_major"] = PATCHED_MINOR_BY_MAJOR.get(major, "")
        return row

    if major is None or major not in PATCHED_MINOR_BY_MAJOR:
        row["status"] = "UNKNOWN_VERSION"
        row["patched_minor_for_major"] = ""
        return row

    patched_minor = PATCHED_MINOR_BY_MAJOR[major]
    row["patched_minor_for_major"] = patched_minor
    row["status"] = "VULNERABLE" if minor < patched_minor else "PATCHED"
    return row


def main():
    epilog = (
        "environment variables (required):\n"
        "  FALCON_CLIENT_ID       Falcon API client ID\n"
        "  FALCON_CLIENT_SECRET   Falcon API client secret\n"
        "  FALCON_BASE_URL        Falcon API base URL for your cloud region\n"
        "                         (default: https://api.crowdstrike.com)\n"
        "                           us-1      https://api.crowdstrike.com\n"
        "                           us-2      https://api.us-2.crowdstrike.com\n"
        "                           eu-1      https://api.eu-1.crowdstrike.com\n"
        "                           us-gov-1  https://api.laggar.gcw.crowdstrike.com\n"
        "\n"
        "  Tip: `source ./falcon.rc` prompts for and exports the client ID/secret\n"
        "  interactively; nothing is ever written to disk.\n"
        "\n"
        "required API scopes (read-only):\n"
        f"{REQUIRED_SCOPES_TEXT}\n"
        "\n"
        "  Create the API client in the Falcon console under:\n"
        "    Support and resources > API clients and keys\n"
        "  If these scopes don't appear under a parent CID, try creating the\n"
        "  client directly under the relevant child CID instead.\n"
        "\n"
        "example:\n"
        "  source ./falcon.rc\n"
        "  ./crowdstrike_postgres_cve_2026_2005_scan.py --cid <CID> --out report.csv\n"
        "\n"
        f"reference: https://www.postgresql.org/support/security/{CVE_ID}"
    )
    parser = argparse.ArgumentParser(
        description="Inventory Postgres hosts in CrowdStrike Falcon and flag CVE-2026-2005 exposure.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--out", default="cve_2026_2005_postgres_report.csv", help="Output CSV path")
    parser.add_argument(
        "--cid",
        default=None,
        help="Expected CrowdStrike Customer ID (CID) these credentials should belong "
             "to. If given, the script verifies this before querying and refuses to "
             "proceed on a mismatch, printing what needs to be created instead.",
    )
    args = parser.parse_args()

    client_id = os.environ.get("FALCON_CLIENT_ID")
    client_secret = os.environ.get("FALCON_CLIENT_SECRET")
    base_url = os.environ.get("FALCON_BASE_URL", "https://api.crowdstrike.com")

    if not client_id or not client_secret:
        sys.exit("Set FALCON_CLIENT_ID and FALCON_CLIENT_SECRET environment variables before running.")

    try:
        print(f"[info] Authenticating against {base_url} ...")
        token = get_token(base_url, client_id, client_secret)
    except FalconAuthError as e:
        sys.exit(f"[error] {e}")
    except requests.HTTPError as e:
        sys.exit(f"[error] Falcon API request failed: {e}")
    except requests.RequestException as e:
        sys.exit(f"[error] Could not reach the Falcon API at {base_url}: {e}")

    resolved_cid = resolve_cid_from_token(token)
    if args.cid:
        if resolved_cid is None:
            print(
                f"[warn] Could not determine which CID these credentials belong to "
                f"(no readable 'cid' claim on the access token), so --cid {args.cid} "
                f"could not be verified. Proceeding anyway.",
                file=sys.stderr,
            )
        elif resolved_cid.lower() != args.cid.lower():
            sys.exit(
                f"[error] These credentials belong to CID '{resolved_cid}', not the "
                f"requested CID '{args.cid}'.\n"
                f"Create a new API client directly under CID '{args.cid}' in the "
                f"Falcon console (Support and resources > API clients and keys) with "
                f"these read-only scopes:\n{REQUIRED_SCOPES_TEXT}\n"
                f"Then re-run this script with FALCON_CLIENT_ID/FALCON_CLIENT_SECRET "
                f"sourced from that new client (e.g. via ./falcon.rc)."
            )
        else:
            print(f"[info] Confirmed credentials belong to requested CID '{args.cid}'.")
    elif resolved_cid:
        print(f"[info] These credentials are scoped to CID '{resolved_cid}'.")

    try:
        print("[info] Querying Falcon Discover for installed PostgreSQL applications ...")
        rows = discover_postgres_applications(base_url, token)
    except FalconAuthError as e:
        sys.exit(f"[error] {e}")
    except requests.HTTPError as e:
        sys.exit(f"[error] Falcon API request failed: {e}")
    except requests.RequestException as e:
        sys.exit(f"[error] Could not reach the Falcon API at {base_url}: {e}")

    print(f"[info] Found {len(rows)} PostgreSQL application instance(s) via Discover.")

    print(f"[info] Cross-checking Falcon Spotlight for direct {CVE_ID} matches ...")
    spotlight_rows = spotlight_cve_matches(base_url, token)
    print(f"[info] Found {len(spotlight_rows)} Spotlight match(es) for {CVE_ID}.")

    all_rows = [classify(r) for r in rows + spotlight_rows]

    fieldnames = [
        "hostname", "host_id", "os_version", "application_name", "application_version",
        "parsed_major", "parsed_minor", "patched_minor_for_major", "status", "source",
    ]
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    vulnerable = [r for r in all_rows if r["status"] in ("VULNERABLE", "SPOTLIGHT_MATCH")]
    unknown = [r for r in all_rows if r["status"] == "UNKNOWN_VERSION"]

    print(f"\n[summary] Total Postgres instances found: {len(all_rows)}")
    print(f"[summary] Flagged as vulnerable / matched to {CVE_ID}: {len(vulnerable)}")
    print(f"[summary] Version could not be parsed (needs manual check): {len(unknown)}")
    print(f"[summary] Full report written to: {args.out}\n")

    if vulnerable:
        print("Vulnerable / matched hosts:")
        for r in vulnerable:
            print(f"  - {r['hostname']} ({r['host_id']}): {r['application_name']} {r['application_version']} [{r['status']}]")

    if unknown:
        print("\nHosts with unparseable version strings (check manually):")
        for r in unknown:
            print(f"  - {r['hostname']} ({r['host_id']}): {r['application_name']} {r['application_version']!r}")


if __name__ == "__main__":
    main()
