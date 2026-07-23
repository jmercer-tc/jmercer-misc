#!/usr/bin/env python3
"""
cs_app_scan.py

Purpose
-------
List all servers running an application whose name matches one or more
regular expressions given on the command line.

Falcon's FQL query language can't express arbitrary regexes, so this script
doesn't attempt to filter server-side: it pages through Falcon Discover's
*entire* application inventory and matches each application's name against
your regex(es) client-side (a name matches if it matches ANY of the regexes
given, i.e. OR semantics; anchor with ^/$ yourself if you want an exact
match rather than a substring search). In a large environment this means
scanning a lot of entities, so it may take a while.

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
    - Discover (Assets): READ    (may show simply as "Assets")

This scope is gated by Falcon Discover module licensing and may not appear
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
    python3 cs_app_scan.py 'postgresql(-[0-9]*)?' [--out report.csv]
    python3 cs_app_scan.py 'nginx' 'apache2?' --out -

Output
------
Prints a summary to stderr and writes a CSV report with columns:
    hostname, host_id, aid, os_version, application_name, application_vendor,
    application_version, matched_pattern
"""

import csv
import json
import os
import re
import sys
import argparse
import requests

# Set from --debug in main(). When true, dump a sample raw Falcon API
# application entity to stderr -- useful for confirming actual field names.
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
    via HTTP 400: "500 is an invalid limit, must be between 1 and 100").
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


def discover_matching_applications(base_url, token, patterns):
    """
    Page through Falcon Discover's *entire* application inventory (no
    server-side name filter -- arbitrary regexes can't be safely expressed
    in FQL) and return one row per (application, host) match, for any
    application whose name matches ANY of the given compiled regex patterns.
    """
    scope = "Discover (Assets): READ"
    app_ids = list(paginated_query(base_url, token, "/discover/queries/applications/v1", {}, required_scope=scope))
    if not app_ids:
        return []

    apps = batch_get_entities(base_url, token, "/discover/entities/applications/v1", app_ids, required_scope=scope)
    if DEBUG and apps:
        log(f"[debug] sample /discover/entities/applications/v1 entity:\n{json.dumps(apps[0], indent=2, default=str)}")

    rows = []
    for app in apps:
        name = app.get("name") or ""
        matched = next((p for p in patterns if p.search(name)), None)
        if matched is None:
            continue

        # Host info is nested directly inside each application entity under
        # "host" (confirmed via --debug against a real Falcon tenant) --
        # not a flat host_id/aid field on the app itself.
        host = app.get("host") or {}
        rows.append({
            "hostname": host.get("hostname", "UNKNOWN"),
            "host_id": host.get("id", "UNKNOWN"),
            "aid": host.get("aid", "UNKNOWN"),
            "os_version": host.get("os_version", ""),
            "application_name": name,
            "application_vendor": app.get("vendor", ""),
            "application_version": app.get("version", ""),
            "matched_pattern": matched.pattern,
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
        "  - Discover (Assets): READ (may show simply as \"Assets\")\n"
        "\n"
        "  Create the API client in the Falcon console under:\n"
        "    Support and resources > API clients and keys\n"
        "  If this scope doesn't appear under a parent CID, try creating the\n"
        "  client directly under the relevant child CID instead.\n"
        "\n"
        "examples:\n"
        "  source ./falcon.rc\n"
        "  ./cs_app_scan.py 'postgresql(-[0-9]*)?' --out postgres_hosts.csv\n"
        "  ./cs_app_scan.py 'nginx' 'apache2?' --out -\n"
    )
    parser = argparse.ArgumentParser(
        description="List servers running an application matching one or more regexes.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "pattern",
        nargs="+",
        metavar="REGEX",
        help="One or more regular expressions to match against the application "
             "name (case-insensitive substring search by default; anchor with "
             "^/$ for an exact match). A host is included if its application "
             "name matches ANY of the given patterns.",
    )
    parser.add_argument(
        "--out",
        default="app_scan_report.csv",
        help="Output CSV path, or - to write the CSV to stdout instead of a "
             "file (all [info]/[summary]/[warn] messages go to stderr either way, "
             "so stdout stays clean for piping).",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Match patterns case-sensitively (default is case-insensitive).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print a sample raw Falcon API application entity to stderr for "
             "troubleshooting, e.g. when expected fields come back empty/UNKNOWN.",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    flags = 0 if args.case_sensitive else re.IGNORECASE
    try:
        patterns = [re.compile(p, flags) for p in args.pattern]
    except re.error as e:
        sys.exit(f"[error] Invalid regex: {e}")

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
        log("[info] Querying Falcon Discover's full application inventory "
            "(no server-side name filter -- this may take a while) ...")
        rows = discover_matching_applications(base_url, token, patterns)
    except (FalconAuthError, FalconApiError) as e:
        sys.exit(f"[error] {e}")
    except requests.HTTPError as e:
        sys.exit(f"[error] Falcon API request failed: {e}")
    except requests.RequestException as e:
        sys.exit(f"[error] Could not reach the Falcon API at {base_url}: {e}")

    fieldnames = [
        "hostname", "host_id", "aid", "os_version", "application_name",
        "application_vendor", "application_version", "matched_pattern",
    ]
    if args.out == "-":
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        sys.stdout.flush()
    else:
        with open(args.out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    report_destination = "stdout" if args.out == "-" else args.out
    log(f"\n[summary] Matching application instances found: {len(rows)}")
    log(f"[summary] Report written to: {report_destination}\n")

    if rows:
        log("Matching hosts:")
        for r in rows:
            log(f"  - {r['hostname']} (aid={r['aid']}): {r['application_name']} {r['application_version']} "
                f"[matched /{r['matched_pattern']}/]")
    else:
        log("No matching applications found.")


if __name__ == "__main__":
    main()
