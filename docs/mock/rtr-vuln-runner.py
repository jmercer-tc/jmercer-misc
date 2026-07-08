#!/usr/bin/env python3
"""
rtr-vuln-runner.py — CrowdStrike CVE mitigation survey runner

For a given CVE (and optional vuln-type), queries CrowdStrike Spotlight
for vulnerable hosts, opens an RTR batch session, runs the appropriate
survey script(s) on each host, and writes a timestamped machine-readable
report.

Requirements:
    pip install crowdstrike-falconpy pyyaml

Environment:
    FALCON_CLIENT_ID      CrowdStrike API client ID
    FALCON_CLIENT_SECRET  CrowdStrike API client secret

    Credentials must be generated from the parent CID (Flight Control /
    MSSP console) to provide visibility across all child CIDs. A credential
    scoped to a single child CID will only see that CID's hosts.

Must be run from within a local clone of the repo, or with --repo-root
pointing at one. CVE configs and RTR scripts are read from the local
filesystem — no network fetch of repo content at runtime.

Usage:
    rtr-vuln-runner.py --cve CVE-2026-31431
    rtr-vuln-runner.py --cve CVE-2026-31431 --vuln-type kernel
    rtr-vuln-runner.py --cve CVE-2026-31431 --cids "Wavelo Prod" "TCX Prod"
    rtr-vuln-runner.py --cve CVE-2026-31431 --hosts aidlist.txt --dry-run
    rtr-vuln-runner.py --cve CVE-2026-31431 --output-format json
    rtr-vuln-runner.py --cve CVE-2026-31431 --repo-root /opt/secops-scripts
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

# CrowdStrike falconpy SDK service classes
# https://github.com/CrowdStrike/falconpy
from falconpy import SpotlightVulnerabilities, Hosts, RealTimeResponse, RealTimeResponseAdmin, FlightControl

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RTR_POLL_INTERVAL_S = 5
RTR_TIMEOUT_S = 120
DEVICES_BATCH_SIZE = 100        # Devices API limit per request
RTR_BATCH_SIZE = 5000           # RTR batch session host limit

# Default repo root: directory containing this script.
# Override with --repo-root if running from elsewhere.
REPO_ROOT_DEFAULT = Path(__file__).resolve().parent

SURVEY_SCRIPT_MAP = {
    "modprobe-block": "rtr-survey-modprobe-block.sh",
    # future:
    # "sysctl-value":     "rtr-survey-sysctl-value.sh",
    # "package-version":  "rtr-survey-package-version.sh",
}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="CrowdStrike CVE mitigation survey runner"
    )
    p.add_argument("--cve", required=True,
                   help="CVE identifier, e.g. CVE-2026-31431")
    p.add_argument("--vuln-type", dest="vuln_type",
                   choices=["kernel", "config", "package"],
                   help="Limit to one vuln-type (default: all types for this CVE)")
    p.add_argument("--cids", nargs="+", metavar="CID_NAME",
                   help="One or more CID names to limit scope "
                        "(default: all CIDs under the parent). "
                        "Host scope precedence: "
                        "--hosts (exact AID list, ignores --cids and Spotlight) > "
                        "--cids (Spotlight scoped to named CIDs) > "
                        "neither (Spotlight across all CIDs under the parent)")
    p.add_argument("--hosts", metavar="FILE",
                   help="Newline-delimited AID list; skips Spotlight query")
    p.add_argument("--previous-report", dest="previous_report", metavar="FILE",
                   help="Prior report file; hosts with mitigation-status: full "
                        "are skipped and their records carried forward")
    p.add_argument("--output-dir", dest="output_dir", default="./reports-data",
                   help="Output directory (default: ./reports-data)")
    p.add_argument("--output-format", dest="output_format",
                   choices=["csv", "json", "yaml"], default="csv",
                   help="Report format (default: csv)")
    p.add_argument("--repo-root", dest="repo_root",
                   default=None,
                   help="Root of the local repo clone (default: directory of this script)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="Resolve hosts and configs; skip RTR execution")
    return p.parse_args()

# ---------------------------------------------------------------------------
# CID resolution
# ---------------------------------------------------------------------------

def resolve_target_cids(cid_names: list[str] | None,
                        client_id: str, client_secret: str) -> list[str] | None:
    """
    Resolve a list of CID names to CID ID strings using the Flight Control API.

    If cid_names is None (--cids not supplied), returns None, which signals
    the caller to run across all CIDs under the parent (default behaviour).

    If cid_names is provided, each name is matched case-insensitively against
    the child CID list. Exits with an error if any name cannot be matched.

    Returns a list of CID ID strings, or None for "all CIDs".
    """
    if cid_names is None:
        return None

    fc = FlightControl(client_id=client_id, client_secret=client_secret)

    # Fetch all child CIDs (paginated)
    all_children = []
    offset = 0
    while True:
        resp = fc.query_children(offset=offset, limit=500)
        if resp["status_code"] != 200:
            sys.exit(f"ERROR: Flight Control API returned {resp['status_code']}: "
                     f"{resp['body']}")
        ids = resp["body"].get("resources", [])
        if not ids:
            break
        # Fetch details for this page of IDs
        detail_resp = fc.get_children(ids=ids)
        for child in detail_resp["body"].get("resources", []):
            all_children.append({
                "cid": child["child_cid"],
                "name": child.get("name", ""),
            })
        total = resp["body"].get("meta", {}).get("pagination", {}).get("total", 0)
        offset += len(ids)
        if offset >= total:
            break

    # Match requested names (case-insensitive)
    name_lower_map = {c["name"].lower(): c["cid"] for c in all_children}
    resolved = []
    unmatched = []
    for name in cid_names:
        cid_id = name_lower_map.get(name.lower())
        if cid_id:
            resolved.append(cid_id)
        else:
            unmatched.append(name)

    if unmatched:
        available = sorted(c["name"] for c in all_children)
        sys.exit(
            f"ERROR: CID name(s) not found: {unmatched}\n"
            f"Available CIDs: {available}"
        )

    return resolved

# ---------------------------------------------------------------------------
# Previous report
# ---------------------------------------------------------------------------

def load_previous_report(path: str) -> dict[str, dict]:
    """
    Load a prior JSON report and return a dict of host records keyed by
    asset-id. Only hosts with mitigation-status: full are returned — these
    are candidates to skip in the current run.
    """
    with open(path) as fh:
        report = json.load(fh)
    return {
        h["asset-id"]: h
        for h in report.get("hosts", [])
        if h.get("mitigation-status") == "full"
    }

# ---------------------------------------------------------------------------
# CrowdStrike auth
# ---------------------------------------------------------------------------

def get_credentials():
    client_id = os.environ.get("FALCON_CLIENT_ID")
    client_secret = os.environ.get("FALCON_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("ERROR: FALCON_CLIENT_ID and FALCON_CLIENT_SECRET must be set")
    return client_id, client_secret

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_cve_configs(repo_root: Path, cve: str, vuln_type: str | None) -> list[dict]:
    """
    Load all CVE config YAML files matching the given CVE (and optionally
    vuln-type) from <repo_root>/rtr-vuln-config/.

    Returns a list of parsed config dicts.
    """
    config_dir = repo_root / "rtr-vuln-config"
    if not config_dir.is_dir():
        sys.exit(f"ERROR: config directory not found: {config_dir}")

    pattern = f"{cve}-*.yaml" if not vuln_type else f"{cve}-{vuln_type}.yaml"
    configs = []
    for f in sorted(config_dir.glob(pattern)):
        with f.open() as fh:
            configs.append(yaml.safe_load(fh))

    if not configs:
        sys.exit(f"ERROR: no config found for {cve}"
                 + (f" vuln-type={vuln_type}" if vuln_type else "")
                 + f" in {config_dir}")
    return configs

def validate_configs(configs: list[dict]):
    """Confirm each mitigation-type in the configs has a known survey script."""
    for cfg in configs:
        for m in cfg.get("mitigations", []):
            mt = m["mitigation-type"]
            if mt not in SURVEY_SCRIPT_MAP:
                sys.exit(f"ERROR: unknown mitigation-type '{mt}' in config for "
                         f"{cfg['cve']} — no survey script available")

# ---------------------------------------------------------------------------
# Spotlight — get vulnerable host AIDs
# ---------------------------------------------------------------------------

def get_vulnerable_aids(cve: str, client_id: str, client_secret: str,
                        target_cids: list[str] | None = None) -> list[str]:
    """
    Query CrowdStrike Spotlight for all host AIDs with an open exposure
    to the given CVE. Handles pagination automatically.

    If target_cids is provided, the Spotlight filter is scoped to those
    CID IDs. If None, the query runs across all CIDs visible to the
    parent credential.
    """
    spotlight = SpotlightVulnerabilities(client_id=client_id,
                                        client_secret=client_secret)
    aids = []
    after = None

    cve_filter = f"cve.id:'{cve}'+status:'open'"
    if target_cids:
        cid_clause = "+".join(f"cid:'{c}'" for c in target_cids)
        cve_filter = f"{cve_filter}+({cid_clause})"

    while True:
        params = {
            "filter": cve_filter,
            "facet": "host_info",
            "limit": 400,
        }
        if after:
            params["after"] = after

        resp = spotlight.query_vulnerabilities_combined(**params)
        if resp["status_code"] != 200:
            sys.exit(f"ERROR: Spotlight API returned {resp['status_code']}: "
                     f"{resp['body']}")

        body = resp["body"]
        for vuln in body.get("resources", []):
            aid = vuln.get("aid")
            if aid:
                aids.append(aid)

        pagination = body.get("meta", {}).get("pagination", {})
        after = pagination.get("after")
        if not after or not body.get("resources"):
            break

    return list(set(aids))  # deduplicate

# ---------------------------------------------------------------------------
# Devices — enrich host metadata
# ---------------------------------------------------------------------------

def get_host_metadata(aids: list[str], client_id: str,
                      client_secret: str) -> dict[str, dict]:
    """
    Fetch host metadata from the Devices API in batches.
    Returns a dict keyed by AID.
    """
    hosts_api = Hosts(client_id=client_id, client_secret=client_secret)
    metadata = {}

    for i in range(0, len(aids), DEVICES_BATCH_SIZE):
        batch = aids[i:i + DEVICES_BATCH_SIZE]
        resp = hosts_api.get_device_details_v2(ids=batch)
        if resp["status_code"] != 200:
            print(f"WARN: Devices API error for batch {i}: {resp['body']}",
                  file=sys.stderr)
            continue
        for device in resp["body"].get("resources", []):
            aid = device.get("device_id")
            if aid:
                metadata[aid] = device

    return metadata

def extract_host_fields(device: dict) -> dict:
    """Map CrowdStrike device fields to report schema fields."""
    # Collect all known IP addresses
    all_ips = []
    local_ip = device.get("local_ip")
    external_ip = device.get("external_ip")
    if local_ip:
        all_ips.append(local_ip)
    for iface in device.get("network_interfaces", []):
        ip = iface.get("local_ip")
        if ip and ip not in all_ips:
            all_ips.append(ip)
    if external_ip and external_ip not in all_ips:
        all_ips.append(external_ip)

    return {
        "asset-id": device.get("device_id"),
        "cid": device.get("cid"),
        "hostname": device.get("hostname"),
        "ip-addrs": {
            "local": local_ip,
            "external": external_ip,
            "all": all_ips,
        },
        "kernel-version": device.get("os_kernel_version"),
        "uname-a": None,            # populated by RTR survey
        "mitigation-status": "unknown",
        "mitigations": [],
        "rtr-status": "pending",
        "rtr-error": None,
    }

# ---------------------------------------------------------------------------
# RTR — batch survey
# ---------------------------------------------------------------------------

def upload_cloud_script(script_name: str, repo_root: Path,
                        rtr_admin: RealTimeResponseAdmin):
    """
    Upload the survey script to CrowdStrike RTR cloud scripts, overwriting
    any previously uploaded version. Script content is read from
    <repo_root>/rtr-vuln-scripts/. This keeps the cloud copy in sync with the
    repo on every run without a separate upload step.
    """
    script_path = repo_root / "rtr-vuln-scripts" / script_name
    if not script_path.is_file():
        sys.exit(f"ERROR: RTR survey script not found: {script_path}")

    content = script_path.read_text()

    # Delete existing version if present, then create fresh.
    resp = rtr_admin.list_scripts()
    for s in resp["body"].get("resources", []):
        if s["name"] == script_name:
            rtr_admin.delete_scripts(ids=s["id"])
            break

    rtr_admin.create_scripts(
        name=script_name,
        platform=["linux"],
        permission_type="private",
        content=content.encode(),
    )

def run_rtr_survey(aids: list[str], mitigation_type: str,
                   mitigation_data: list[str],
                   client_id: str, client_secret: str,
                   repo_root: Path) -> dict[str, dict]:
    """
    Open an RTR batch session against the given AIDs, run the appropriate
    survey script with mitigation_data as arguments, and return raw results
    keyed by AID.
    """
    script_name = SURVEY_SCRIPT_MAP[mitigation_type]
    rtr = RealTimeResponse(client_id=client_id, client_secret=client_secret)
    rtr_admin = RealTimeResponseAdmin(client_id=client_id,
                                     client_secret=client_secret)

    upload_cloud_script(script_name, repo_root, rtr_admin)

    results = {}

    # Process in batches of RTR_BATCH_SIZE
    for i in range(0, len(aids), RTR_BATCH_SIZE):
        batch_aids = aids[i:i + RTR_BATCH_SIZE]

        # Open batch session. Offline hosts time out and are reported as unknown;
        # the runner does not queue or wait for them.
        init_resp = rtr.batch_init_sessions(
            host_ids=batch_aids,
            queue_offline=False,
        )
        if init_resp["status_code"] != 201:
            print(f"WARN: RTR batch init failed: {init_resp['body']}",
                  file=sys.stderr)
            for aid in batch_aids:
                results[aid] = {"error": "batch_init_failed"}
            continue

        batch_id = init_resp["body"]["batch_id"]
        cmd_args = " ".join(mitigation_data)

        # Execute survey script
        exec_resp = rtr_admin.batch_active_responder_command(
            base_command="runscript",
            command_string=(
                f"runscript -CloudFile='{script_name}'"
                f" -CommandLine='{cmd_args}'"
            ),
            batch_id=batch_id,
            timeout=RTR_TIMEOUT_S,
        )

        if exec_resp["status_code"] not in (200, 201):
            print(f"WARN: RTR runscript failed: {exec_resp['body']}",
                  file=sys.stderr)
            for aid in batch_aids:
                results[aid] = {"error": "runscript_failed"}
            continue

        # Collect per-host results
        for aid, host_result in exec_resp["body"].get("combined", {}).get(
                "resources", {}).items():
            stdout = host_result.get("stdout", "")
            stderr = host_result.get("stderr", "")
            complete = host_result.get("complete", False)

            if not complete:
                results[aid] = {"error": "timeout", "stderr": stderr}
            elif stderr:
                results[aid] = {"error": "script_error", "stderr": stderr}
            else:
                results[aid] = {"raw_stdout": stdout}

    return results

# ---------------------------------------------------------------------------
# Parse RTR stdout
# ---------------------------------------------------------------------------

SURVEY_START = "##RTR-SURVEY-START##"
SURVEY_END   = "##RTR-SURVEY-END##"

def parse_survey_output(raw_stdout: str,
                        mitigation_type: str) -> tuple[bool, list, str | None]:
    """
    Parse stdout from a survey script.

    Returns (complete, modules_list, uname_a_string).

    complete is False if ##RTR-SURVEY-END## is absent, indicating the script
    terminated prematurely on the target host. In that case modules_list and
    uname_a_string should not be trusted and the host should be marked unknown.
    """
    complete = SURVEY_END in raw_stdout

    if mitigation_type != "modprobe-block":
        # Placeholder for future mitigation types
        return complete, [], None

    # Strip sentinel lines; keep only data lines
    data_lines = [
        l.strip() for l in raw_stdout.splitlines()
        if l.strip() and l.strip() not in (SURVEY_START, SURVEY_END)
    ]

    modules = []
    uname_a = None

    try:
        if data_lines:
            modules = json.loads(data_lines[0])
        if len(data_lines) > 1:
            uname_obj = json.loads(data_lines[1])
            uname_a = uname_obj.get("uname_a")
    except json.JSONDecodeError as e:
        print(f"WARN: JSON parse error in survey output: {e}", file=sys.stderr)

    return complete, modules, uname_a

# ---------------------------------------------------------------------------
# Mitigation status classification
# ---------------------------------------------------------------------------

def classify_mitigation_status(mitigation_type: str,
                                modules: list[dict]) -> tuple[str, list[dict]]:
    """
    Given raw module observations from the survey script, return
    (mitigation_status, enriched_modules).

    mitigation_status is one of: full, partial, none, unknown
    """
    if not modules:
        return "unknown", []

    enriched = []
    for m in modules:
        block_entry = m.get("block_entry")
        loaded = m.get("loaded", False)

        # A module is effectively mitigated when it is blacklisted AND not loaded.
        effective = bool(block_entry) and not loaded

        enriched.append({
            "module": m["module"],
            "block-entry": block_entry,
            "loaded": loaded,
            "effective": effective,
        })

    all_effective = all(m["effective"] for m in enriched)
    any_block_entry = any(m["block-entry"] for m in enriched)
    any_loaded_despite_block = any(
        m["block-entry"] and m["loaded"] for m in enriched
    )

    if all_effective:
        status = "full"
    elif any_block_entry:
        # Some blocks present but not all modules covered, or needs reboot
        status = "partial"
    else:
        status = "none"

    return status, enriched

# ---------------------------------------------------------------------------
# Report assembly and output
# ---------------------------------------------------------------------------

def build_report(cve: str, vuln_type: str, host_records: list[dict],
                 spotlight_total: int) -> dict:
    surveyed = sum(1 for h in host_records if h["rtr-status"] != "pending")
    unreachable = sum(1 for h in host_records if h["rtr-status"] in ("timeout", "error"))
    return {
        "report-meta": {
            "cve": cve,
            "vuln-type": vuln_type,
            "generated-at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runner-version": "1.0.0",
            "spotlight-total-exposed": spotlight_total,
            "hosts-surveyed": surveyed,
            "hosts-unreachable": unreachable,
        },
        "hosts": host_records,
    }

def write_report(report: dict, output_dir: str, cve: str,
                 vuln_type: str, fmt: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{cve}-{vuln_type}-{ts}.{fmt}"
    out_path = Path(output_dir) / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w") as fh:
        if fmt == "json":
            json.dump(report, fh, indent=2)
        elif fmt == "yaml":
            yaml.dump(report, fh, default_flow_style=False, sort_keys=False)
        elif fmt == "csv":
            import csv
            writer = csv.DictWriter(fh, fieldnames=[
                "asset-id", "cid", "hostname",
                "ip-local", "ip-external",
                "kernel-version", "uname-a",
                "mitigation-status",
            ])
            writer.writeheader()
            for host in report["hosts"]:
                writer.writerow({
                    "asset-id": host.get("asset-id"),
                    "cid": host.get("cid"),
                    "hostname": host.get("hostname"),
                    "ip-local": host.get("ip-addrs", {}).get("local"),
                    "ip-external": host.get("ip-addrs", {}).get("external"),
                    "kernel-version": host.get("kernel-version"),
                    "uname-a": host.get("uname-a"),
                    "mitigation-status": host.get("mitigation-status"),
                })

    return out_path, ts

def write_errlog(host_records: list[dict], output_dir: str,
                 cve: str, vuln_type: str, ts: str) -> Path | None:
    """
    Write an error log for any hosts that produced stderr output during the
    RTR survey. Returns the log path, or None if there was nothing to log.
    """
    entries = [
        h for h in host_records
        if h.get("rtr-error") or h.get("rtr-status") in ("incomplete", "timeout", "error")
    ]
    if not entries:
        return None

    log_path = Path(output_dir) / f"{cve}-{vuln_type}-{ts}.errlog"
    with log_path.open("w") as fh:
        for h in entries:
            fh.write(f"aid: {h.get('asset-id', 'unknown')}\n")
            fh.write(f"hostname: {h.get('hostname', 'unknown')}\n")
            fh.write(f"rtr-status: {h.get('rtr-status', 'unknown')}\n")
            stderr = h.get("rtr-error", "")
            if stderr:
                fh.write("--- stderr ---\n")
                fh.write(stderr.rstrip())
                fh.write("\n")
            fh.write("\n")

    return log_path

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    client_id, client_secret = get_credentials()

    # Resolve repo root
    repo_root = Path(args.repo_root).resolve() if args.repo_root else REPO_ROOT_DEFAULT

    # --- Resolve target CIDs ---
    target_cids = resolve_target_cids(args.cids, client_id, client_secret)
    if target_cids:
        print(f"Scoping to {len(target_cids)} CID(s): {args.cids}", file=sys.stderr)
    else:
        print("Scoping to all CIDs under the parent.", file=sys.stderr)

    # --- Load previous report (optional) ---
    prev_full = {}
    if args.previous_report:
        print(f"Loading previous report from {args.previous_report} ...",
              file=sys.stderr)
        prev_full = load_previous_report(args.previous_report)
        print(f"  {len(prev_full)} host(s) previously fully mitigated — "
              "will be skipped", file=sys.stderr)

    # --- Load and validate CVE configs ---
    print(f"Loading configs for {args.cve} ...", file=sys.stderr)
    configs = load_cve_configs(repo_root, args.cve, args.vuln_type)
    validate_configs(configs)
    print(f"  Loaded {len(configs)} config(s): "
          + ", ".join(c["vuln-type"] for c in configs), file=sys.stderr)

    # Determine effective vuln-type label for the report filename
    vuln_type_label = args.vuln_type or "+".join(c["vuln-type"] for c in configs)

    # --- Get vulnerable host AIDs ---
    if args.hosts:
        print(f"Loading host list from {args.hosts} ...", file=sys.stderr)
        aids = [line.strip() for line in Path(args.hosts).read_text().splitlines()
                if line.strip()]
        spotlight_total = len(aids)
    else:
        print(f"Querying Spotlight for hosts vulnerable to {args.cve} ...",
              file=sys.stderr)
        aids = get_vulnerable_aids(args.cve, client_id, client_secret, target_cids)
        spotlight_total = len(aids)
        print(f"  {spotlight_total} host(s) found", file=sys.stderr)

    if not aids:
        print("No vulnerable hosts found — nothing to do.", file=sys.stderr)
        sys.exit(0)

    # --- Filter out previously fully-mitigated hosts ---
    carried_forward = []
    if prev_full:
        remaining = []
        for aid in aids:
            # asset-id from Spotlight matches device_id; build a temporary
            # record to look up by aid directly
            if aid in prev_full:
                rec = dict(prev_full[aid])
                rec["carried-from-previous-report"] = True
                carried_forward.append(rec)
            else:
                remaining.append(aid)
        skipped = len(aids) - len(remaining)
        if skipped:
            print(f"  Skipping {skipped} fully-mitigated host(s) from previous report",
                  file=sys.stderr)
        aids = remaining

    if not aids and not carried_forward:
        print("All hosts fully mitigated per previous report — nothing to survey.",
              file=sys.stderr)
        sys.exit(0)

    # --- Fetch host metadata ---
    print(f"Fetching metadata for {len(aids)} host(s) ...", file=sys.stderr)
    metadata = get_host_metadata(aids, client_id, client_secret)
    host_records = {}
    for aid in aids:
        device = metadata.get(aid, {"device_id": aid})
        host_records[aid] = extract_host_fields(device)

    if args.dry_run:
        print(f"Dry run — skipping RTR. {len(aids)} host(s) would be surveyed.",
              file=sys.stderr)
        report = build_report(args.cve, vuln_type_label,
                              list(host_records.values()), spotlight_total)
        out_path, _ = write_report(report, args.output_dir, args.cve,
                                   vuln_type_label, args.output_format)
        print(f"Report written: {out_path}", file=sys.stderr)
        return

    # --- RTR survey ---
    for cfg in configs:
        for mitigation in cfg.get("mitigations", []):
            mt = mitigation["mitigation-type"]
            md = mitigation["mitigation-data"]

            print(f"Running RTR survey: {mt} ({len(md)} item(s)) "
                  f"on {len(aids)} host(s) ...", file=sys.stderr)

            rtr_results = run_rtr_survey(
                aids, mt, md, client_id, client_secret, repo_root
            )

            # Parse and classify per host
            for aid, result in rtr_results.items():
                record = host_records[aid]
                err = result.get("error")

                if err:
                    record["rtr-status"] = err
                    record["rtr-error"] = result.get("stderr") or err
                    continue

                complete, modules, uname_a = parse_survey_output(
                    result["raw_stdout"], mt
                )

                if not complete:
                    record["rtr-status"] = "incomplete"
                    record["rtr-error"] = "survey script terminated prematurely (no end marker)"
                    record["mitigation-status"] = "unknown"
                    continue

                status, enriched = classify_mitigation_status(mt, modules)

                if uname_a:
                    record["uname-a"] = uname_a
                record["rtr-status"] = "success"
                record["mitigation-status"] = status
                record["mitigations"].append({
                    "mitigation-type": mt,
                    "modules": enriched,
                })

    # --- Write report and error log ---
    all_host_records = list(host_records.values()) + carried_forward
    report = build_report(args.cve, vuln_type_label,
                          all_host_records, spotlight_total)
    out_path, ts = write_report(report, args.output_dir, args.cve,
                                vuln_type_label, args.output_format)
    errlog_path = write_errlog(all_host_records, args.output_dir,
                               args.cve, vuln_type_label, ts)

    # Summary to stderr
    statuses = [h["mitigation-status"] for h in report["hosts"]]
    summary = (
        f"\nSurveyed: {len(aids)}"
        f"  Full: {statuses.count('full')}"
        f"  Partial: {statuses.count('partial')}"
        f"  None: {statuses.count('none')}"
        f"  Unknown: {statuses.count('unknown')}"
    )
    if carried_forward:
        summary += f"  Skipped (prev full): {len(carried_forward)}"
    print(summary, file=sys.stderr)
    print(f"Report written: {out_path}", file=sys.stderr)
    if errlog_path:
        print(f"Error log written: {errlog_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
