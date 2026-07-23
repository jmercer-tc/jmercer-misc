#!/usr/bin/env python3
"""
cs_cve_scan.py

Purpose
-------
List all servers CrowdStrike Falcon Spotlight currently reports as
vulnerable to a given CVE.

This queries Falcon Spotlight's vulnerability data directly for the CVE ID
you specify, and by default only reports findings whose Spotlight status is
still "open" or "reopened" (i.e. not yet remediated) -- use --include-closed
to see every match regardless of remediation status.

This is a standalone script: it embeds its own copy of the Falcon API
plumbing (auth, pagination, error handling) so it has no dependencies on any
other file in this repo and can be copied/run on its own.

Requirements
------------
    pip install requests

Auth / Scopes
-------------
Create an API client in the Falcon console under:
    Support and resources > API clients and keys

Required scope (read-only):
    - Spotlight Vulnerabilities: READ    (may show simply as "Vulnerabilities")

This scope is gated by Falcon Spotlight module licensing and may not appear
at all when creating a client under a parent CID in a Flight Control setup
-- if so, create the client directly under the specific child CID instead.
This script assumes the credentials in FALCON_CLIENT_ID/FALCON_CLIENT_SECRET
are already scoped to whichever CID you want to query; there is no --cid
option and no member_cid handling, by design.

Provide credentials via environment variables (never hardcode them):

    source ./falcon.rc
    export FALCON_BASE_URL="https://api.crowdstrike.com"   # see region table below

Region base URLs:
    us-1      https://api.crowdstrike.com
    us-2      https://api.us-2.crowdstrike.com
    eu-1      https://api.eu-1.crowdstrike.com
    us-gov-1  https://api.laggar.gcw.crowdstrike.com

Usage
-----
    python3 cs_cve_scan.py CVE-2026-2005 [--out report.csv] [--include-closed]

Output
------
Prints a summary to stderr and writes a CSV report with columns:
    hostname, aid, os_version, application_name, application_version,
    cve_id, severity, base_score, vuln_status
"""

import csv
import json
import os
import sys
import argparse
import requests

# Set from --debug in main(). When true, dump a sample raw Falcon API
# vulnerability entity to stderr -- useful for confirming actual field names,
# since this script's field extraction (host_info, app, cve sub-objects) is
# based on CrowdStrike's documented Spotlight schema but hasn't been
# confirmed against a live raw response the way the Discover applications
# entity shape was in the companion cs_app_scan.py tool.
DEBUG = False


def log(*args, **kwargs):
    """Print informational/summary/warning output to stderr, so stdout stays
    reserved for the CSV report when --out - is used to pipe it elsewhere."""
    print(*args, file=sys.stderr, **kwargs)


class FalconAuthError(Exception):
    """Raised for 401/403 responses -- missing/invalid credentials or scope."""


class FalconApiError(Exception):
    """A non-auth Falcon API error (400, 500, etc.) -- carries the API's own
    error detail, which plain requests.HTTPError discards."""


def _describe_falcon_error(resp):
    """Best-effort extraction of the Falcon API's own error message(s) from a
    JSON error response body, falling back to the raw response text."""
    try:
        body = resp.json()
        errors = body.get("errors") or []
        messages = [e.get("message", "") for e in errors if e.get("message")]
        if messages:
            return "; ".join(messages)
    except ValueError:
        pass
    return resp.text[:500] if resp.text else resp.reason


def _check_response(resp, context: str, required_scope: str = None):
    """Raise a clear, actionable FalconAuthError for auth/permission
    failures; raise FalconApiError (with the Falcon API's own error detail)
    for any other 4xx/5xx, since plain requests.HTTPError discards the
    response body."""
    if resp.status_code == 401:
        raise FalconAuthError(
            f"Falcon API authentication failed while {context} (HTTP 401): "
            f"{_describe_falcon_error(resp)}. Check FALCON_CLIENT_ID/FALCON_CLIENT_SECRET."
        )
    if resp.status_code == 403:
        scope_hint = f" Required scope: {required_scope}." if required_scope else ""
        raise FalconAuthError(
            f"Falcon API request forbidden while {context} (HTTP 403): "
            f"{_describe_falcon_error(resp)}.{scope_hint} Check the API client's scopes "
            "in the Falcon console under Support and resources > API clients and keys."
        )
    if resp.status_code >= 400:
        raise FalconApiError(
            f"Falcon API request failed while {context} (HTTP {resp.status_code}): "
            f"{_describe_falcon_error(resp)}"
        )


def get_token(base_url, client_id, client_secret):
    resp = requests.post(
        f"{base_url}/oauth2/token",
        data={"client_id": client_id, "client_secret": client_secret},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    _check_response(resp, "authenticating")
    return resp.json()["access_token"]


def paginated_query(base_url, token, query_path, params=None, limit=100, required_scope=None):
    """Yield IDs from a Falcon 'queries' endpoint, handling offset pagination.

    Default limit is 100: several Falcon "queries" endpoints cap out well
    below the naive assumption of 500 (confirmed for Discover applications
    via HTTP 400: "500 is an invalid limit, must be between 1 and 100"), and
    100 is safely within range for every endpoint this script uses.
    """
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


def spotlight_cve_matches(base_url, token, cve_id, include_closed):
    """
    Query Falcon Spotlight directly for hosts matching cve_id. By default
    only "open"/"reopened" findings are returned (i.e. still unremediated
    per Spotlight); pass include_closed=True to also return "closed"/
    "expired" findings.
    """
    scope = "Spotlight Vulnerabilities: READ"
    if include_closed:
        fql_filter = f"cve.id:'{cve_id}'"
    else:
        # FQL combines an AND ("+") with an OR-of-values (bracketed list) --
        # this is documented FQL syntax, but hasn't been confirmed against
        # this specific endpoint/property with a live request; if it comes
        # back as a 400, the error-surfacing below will show the exact
        # complaint (as it did for the Discover applications filter bug) so
        # it can be corrected without guessing blind.
        fql_filter = f"cve.id:'{cve_id}'+status:['open','reopened']"
    query_params = {"filter": fql_filter}

    vuln_ids = list(paginated_query(base_url, token, "/spotlight/queries/vulnerabilities/v1", query_params, required_scope=scope))
    if not vuln_ids:
        return []

    vulns = batch_get_entities(base_url, token, "/spotlight/entities/vulnerabilities/v2", vuln_ids, required_scope=scope)
    if DEBUG and vulns:
        log(f"[debug] sample /spotlight/entities/vulnerabilities/v2 entity:\n{json.dumps(vulns[0], indent=2, default=str)}")

    rows = []
    for v in vulns:
        host = v.get("host_info") or {}
        app = v.get("app") or {}
        cve_info = v.get("cve") or {}
        rows.append({
            "hostname": host.get("hostname", "UNKNOWN"),
            # "aid" (Falcon Agent ID) is documented as a top-level field on
            # most Falcon entities, vulnerabilities included -- not nested
            # under host_info. Fall back to host_info's own aid/host_id in
            # case that assumption is wrong; --debug will show the truth.
            "aid": v.get("aid") or host.get("aid") or host.get("host_id") or "UNKNOWN",
            "os_version": host.get("os_version", ""),
            "application_name": app.get("product_name_version") or app.get("product_name") or "",
            "application_version": app.get("version", ""),
            "cve_id": cve_id,
            "severity": cve_info.get("severity", ""),
            "base_score": cve_info.get("base_score", ""),
            "vuln_status": v.get("status", ""),
        })
    return rows


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
        "  Credentials are assumed to already be scoped to the CID you want to\n"
        "  query (e.g. a child CID API client in a Flight Control setup) -- this\n"
        "  script has no --cid option and does not switch between CIDs.\n"
        "\n"
        "required API scope (read-only):\n"
        "  - Spotlight Vulnerabilities: READ (may show simply as \"Vulnerabilities\")\n"
        "\n"
        "  Create the API client in the Falcon console under:\n"
        "    Support and resources > API clients and keys\n"
        "  If this scope doesn't appear under a parent CID, try creating the\n"
        "  client directly under the relevant child CID instead.\n"
        "\n"
        "example:\n"
        "  source ./falcon.rc\n"
        "  ./cs_cve_scan.py CVE-2026-2005 --out vulnerable_hosts.csv\n"
    )
    parser = argparse.ArgumentParser(
        description="List servers CrowdStrike Falcon Spotlight currently reports as vulnerable to a given CVE.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("cve", metavar="CVE-YYYY-NNNNN", help="CVE ID to check for, e.g. CVE-2026-2005")
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path, or - to write the CSV to stdout instead of a "
             "file (all [info]/[summary]/[warn] messages go to stderr either way, "
             "so stdout stays clean for piping). Default: <cve>_vulnerable_hosts.csv",
    )
    parser.add_argument(
        "--include-closed",
        action="store_true",
        help="Also include Spotlight findings whose status is \"closed\" or "
             "\"expired\" (i.e. already remediated). By default only \"open\"/"
             "\"reopened\" findings are reported.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print a sample raw Falcon API vulnerability entity to stderr "
             "for troubleshooting, e.g. when expected fields come back "
             "empty/UNKNOWN.",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    out_path = args.out if args.out is not None else f"{args.cve.lower()}_vulnerable_hosts.csv"

    client_id = os.environ.get("FALCON_CLIENT_ID")
    client_secret = os.environ.get("FALCON_CLIENT_SECRET")
    base_url = os.environ.get("FALCON_BASE_URL", "https://api.crowdstrike.com")

    if not client_id or not client_secret:
        sys.exit("Set FALCON_CLIENT_ID and FALCON_CLIENT_SECRET environment variables before running.")

    try:
        log(f"[info] Authenticating against {base_url} ...")
        token = get_token(base_url, client_id, client_secret)
    except (FalconAuthError, FalconApiError) as e:
        sys.exit(f"[error] {e}")
    except requests.HTTPError as e:
        sys.exit(f"[error] Falcon API request failed: {e}")
    except requests.RequestException as e:
        sys.exit(f"[error] Could not reach the Falcon API at {base_url}: {e}")

    try:
        log(f"[info] Querying Falcon Spotlight for {args.cve} matches "
            f"({'all statuses' if args.include_closed else 'open/reopened only'}) ...")
        rows = spotlight_cve_matches(base_url, token, args.cve, args.include_closed)
    except (FalconAuthError, FalconApiError) as e:
        sys.exit(f"[error] {e}")
    except requests.HTTPError as e:
        sys.exit(f"[error] Falcon API request failed: {e}")
    except requests.RequestException as e:
        sys.exit(f"[error] Could not reach the Falcon API at {base_url}: {e}")

    fieldnames = [
        "hostname", "aid", "os_version", "application_name", "application_version",
        "cve_id", "severity", "base_score", "vuln_status",
    ]
    if out_path == "-":
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        sys.stdout.flush()
    else:
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    report_destination = "stdout" if out_path == "-" else out_path
    log(f"\n[summary] Hosts vulnerable to {args.cve}: {len(rows)}")
    log(f"[summary] Report written to: {report_destination}\n")

    if rows:
        log("Vulnerable hosts:")
        for r in rows:
            log(f"  - {r['hostname']} (aid={r['aid']}): {r['application_name']} {r['application_version']} "
                f"[{r['vuln_status']}]")
    else:
        log(f"No hosts found vulnerable to {args.cve}.")


if __name__ == "__main__":
    main()
