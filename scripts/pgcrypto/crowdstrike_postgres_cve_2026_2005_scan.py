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

Required scopes (read-only):
    - Hosts: READ
    - Discover (Assets): READ
    - Spotlight Vulnerabilities: READ

Provide credentials via environment variables (never hardcode them):

    export FALCON_CLIENT_ID="..."
    export FALCON_CLIENT_SECRET="..."
    export FALCON_BASE_URL="https://api.crowdstrike.com"   # see region table below

Region base URLs:
    us-1      https://api.crowdstrike.com
    us-2      https://api.us-2.crowdstrike.com
    eu-1      https://api.eu-1.crowdstrike.com
    us-gov-1  https://api.laggar.gcw.crowdstrike.com

Usage
-----
    python3 crowdstrike_postgres_cve_2026_2005_scan.py [--out report.csv]

Output
------
Prints a summary table to stdout and writes a CSV report with columns:
    hostname, host_id, os_version, application_name, application_version,
    parsed_major, parsed_minor, patched_minor_for_major, status, source

`status` is one of: VULNERABLE, PATCHED, UNKNOWN_VERSION, SPOTLIGHT_MATCH
"""

import csv
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


def get_token(base_url: str, client_id: str, client_secret: str) -> str:
    resp = requests.post(
        f"{base_url}/oauth2/token",
        data={"client_id": client_id, "client_secret": client_secret},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def paginated_query(base_url, token, query_path, params=None, limit=500):
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
        resp.raise_for_status()
        body = resp.json()
        ids = body.get("resources", [])
        for _id in ids:
            yield _id
        pagination = body.get("meta", {}).get("pagination", {})
        total = pagination.get("total", 0)
        offset += len(ids)
        if not ids or offset >= total:
            break


def batch_get_entities(base_url, token, entities_path, ids, id_param="ids", batch_size=100):
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
        resp.raise_for_status()
        results.extend(resp.json().get("resources", []))
    return results


def discover_postgres_applications(base_url, token):
    """
    Use Falcon Discover's Applications inventory to find hosts with
    PostgreSQL installed, and pull the reported version string.
    """
    query_params = {"filter": "application_name:*'*ostgre*'"}
    app_ids = list(paginated_query(base_url, token, "/discover/queries/applications/v1", query_params))
    if not app_ids:
        return []

    apps = batch_get_entities(base_url, token, "/discover/entities/applications/v1", app_ids)

    # Resolve host_id -> hostname/os via Discover Hosts entities
    host_ids = sorted({a.get("host_id") for a in apps if a.get("host_id")})
    hosts_by_id = {}
    if host_ids:
        hosts = batch_get_entities(base_url, token, "/discover/entities/hosts/v1", host_ids)
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
    query_params = {"filter": f"cve.id:'{CVE_ID}'"}
    try:
        vuln_ids = list(paginated_query(base_url, token, "/spotlight/queries/vulnerabilities/v1", query_params))
    except requests.HTTPError as e:
        print(f"[warn] Spotlight query failed ({e}); skipping Spotlight cross-check.", file=sys.stderr)
        return []

    if not vuln_ids:
        return []

    vulns = batch_get_entities(base_url, token, "/spotlight/entities/vulnerabilities/v2", vuln_ids)

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
    parser = argparse.ArgumentParser(description="Inventory Postgres hosts in CrowdStrike Falcon and flag CVE-2026-2005 exposure.")
    parser.add_argument("--out", default="cve_2026_2005_postgres_report.csv", help="Output CSV path")
    args = parser.parse_args()

    client_id = os.environ.get("FALCON_CLIENT_ID")
    client_secret = os.environ.get("FALCON_CLIENT_SECRET")
    base_url = os.environ.get("FALCON_BASE_URL", "https://api.crowdstrike.com")

    if not client_id or not client_secret:
        sys.exit("Set FALCON_CLIENT_ID and FALCON_CLIENT_SECRET environment variables before running.")

    print(f"[info] Authenticating against {base_url} ...")
    token = get_token(base_url, client_id, client_secret)

    print("[info] Querying Falcon Discover for installed PostgreSQL applications ...")
    rows = discover_postgres_applications(base_url, token)
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
