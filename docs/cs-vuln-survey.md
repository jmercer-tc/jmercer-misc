# Linux Fleet Vulnerability Quantification — Design Proposal

**Project:** CrowdStrike-Driven CVE Mitigation Inventory  
**Repo:** `waveloinc/secops-scripts` (proposed)  
**Date:** 2026-06-09  
**Author:** Jim Mercer  
**Status:** Draft for Review

---

## Executive Summary

This proposal describes a lightweight, extensible toolchain that answers a single operational question: **for a given CVE, which hosts in our Linux fleet are vulnerable, and what mitigations — if any — are in place?**

The toolchain leverages CrowdStrike Falcon's Spotlight vulnerability API and Real Time Response (RTR) to enumerate affected hosts and remotely survey their mitigation posture. Results are written to a structured, machine-readable report that downstream processes can enrich with asset metadata, business unit attribution, or ticket creation.

The design is intentionally minimal on the RTR side: remote scripts only collect facts; all logic, scoring, and classification runs locally after the data has been gathered. This keeps the RTR footprint small, auditable, and low-risk.

---

## Problem Statement

With increasing regularity, our Linux fleet is being identified as having vulnerabilities that expose us to risk. We need to be able to quickly identify the affected hosts, and categorize them by severity, business unit, and/or working group. We also need to be able to re-assess the situation on a daily, weekly, or monthly cadence, so that we can identify and report on our progress in mitigating the threats.

CrowdStrike Spotlight identifies which hosts are kernel-vulnerable to a given CVE based on the running kernel version. However, kernel-level vulnerabilities often have filesystem-based mitigations (e.g., blacklisting a kernel module in `/etc/modprobe.d/`) that may or may not be in place independently of a kernel upgrade.

Spotlight may also be useful in identifying and tracing non-kernel related CVEs, like problematic application settings, or vulnerable packages.

Spotlight alone cannot answer:

- Is a mitigation deployed on this host?
- Is the mitigation effective (module blocked *and* not currently loaded), or only partial (blocked but still resident in memory, requiring a reboot)?
- Which specific modules or config items are covered?
- How has the mitigation posture of the fleet changed over time?

Without this data, patch prioritisation and risk reporting are incomplete. A host that Spotlight marks *vulnerable* may already be mitigated; a host that has a blacklist entry may still have the module loaded from before the entry was written. And without repeatable, timestamped reports, there is no way to measure whether remediation efforts are making progress.

---

## Solution Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    rtr-vuln-runner.py                        │
│                                                              │
│  1. Parse CLI args (CVE-ID, optional vuln-type, host list)   │
│  2. Fetch CVE config YAML from config repo                   │
│  3. Query Spotlight API → vulnerable host AIDs               │
│  4. Fetch host metadata (hostname, IPs, kernel) from Hosts   │
│     API                                                      │
│  5. Batch RTR session → run survey script(s) per host        │
│  6. Collect raw survey output                                │
│  7. Compute mitigation-status per host                       │
│  8. Write structured report (JSON/CSV/YAML)                  │
└──────────────────────────────────────────────────────────────┘
         ▲                          ▲
         │                          │
  CVE config YAML            RTR survey scripts
  (config repo)              (rtr-vuln-scripts/ in repo)
```

The runner is invoked on demand or in a CI/scheduled context from within a local clone of the repo. CVE configs and RTR survey scripts are read directly from the repo directory — no network fetch of repo content is required at runtime. Report data is self-contained and requires no live CrowdStrike connection to read.

---

## Repository Layout

```
waveloinc/secops-scripts/
├── rtr-vuln-runner.py              # Main orchestrator (this proposal)
├── rtr-vuln-scripts/
│   ├── rtr-survey-modprobe-block.sh   # Survey: kernel module blacklist + load state
│   ├── rtr-survey-config-option.sh    # (future) Survey: config file option presence
│   └── rtr-survey-package-version.sh  # (future) Survey: package installed/version
├── rtr-vuln-config/
│   ├── CVE-2026-31431-kernel.yaml
│   ├── CVE-2024-1086-kernel.yaml
│   └── ...
└── reports-data/                   # .gitignored; populated by runner at runtime
    └── CVE-2026-31431-kernel-20260609T143201Z.json  # example output
```

---

## CVE Config File Schema

Config files are YAML, one file per CVE+type combination. They are the single source of truth for what the runner should check and what RTR script handles each check.

**Filename convention:** `CVE-<ID>-<vuln-type>.yaml`

**Example — `CVE-2026-31431-kernel.yaml`:**

```yaml
# CVE-2026-31431: Copy/Fail and derivatives
# Kernel modules exploitable via af_alg and related sockets.
# Mitigated by blacklisting the relevant modules in /etc/modprobe.d/.
# Ref: https://nvd.nist.gov/vuln/detail/CVE-2026-31431

cve: CVE-2026-31431
vuln-type: kernel
description: "af_alg copy/fail family — arbitrary kernel write via AEAD socket"

mitigations:
  - mitigation-type: modprobe-block
    # RTR script: rtr-vuln-scripts/rtr-survey-modprobe-block.sh
    # Each item is a kernel module name passed as an argument to the script.
    mitigation-data:
      - algif_aead    # CVE-2026-31431 direct vector
      - esp4          # CVE-2026-46300 Fragnesia, same patch set
      - esp6
      - rxrpc
```

**Schema fields:**

| Field | Type | Description |
|---|---|---|
| `cve` | string | Canonical CVE identifier |
| `vuln-type` | enum | `kernel` \| `config` \| `package` (extensible) |
| `description` | string | Human-readable summary |
| `mitigations[].mitigation-type` | string | Matches an `rtr-vuln-scripts/rtr-survey-<type>.sh` filename |
| `mitigations[].mitigation-data` | list | Arguments passed to the survey script |

A single CVE config may contain multiple `mitigation-type` blocks if the CVE spans more than one remediation category.

---

## CrowdStrike API Integration

The runner uses the CrowdStrike Python SDK (`crowdstrike-falconpy`).

### Step 1 — Get Vulnerable Hosts (Spotlight API)

```
GET /spotlight/combined/vulnerabilities/v1
  ?filter=cve.id:'CVE-2026-31431'+status:'open'
  &facet=host_info
```

Returns a list of `aid` values (CrowdStrike Agent IDs) for hosts with open exposure to the CVE. The runner collects all AIDs across paginated results.

Optionally, the runner accepts `--hosts <file>` to scope the run to a pre-supplied list of AIDs, bypassing Spotlight. This is useful for re-scanning a targeted subset or validating a remediation wave.

### Step 2 — Enrich Host Metadata (Devices API)

```
POST /devices/entities/devices/v2
  body: { "ids": [ <aid>, ... ] }
```

Retrieves per-host metadata for report fields. The runner batches requests at 100 AIDs per call (API limit).

Relevant fields extracted:

| Report Field | CrowdStrike Source Field |
|---|---|
| `asset-id` | `device_id` |
| `cid` | `cid` |
| `hostname` | `hostname` |
| `ip-addrs` | `local_ip`, `external_ip`, `network_interfaces[].local_ip` |
| `kernel-version` | `os_kernel_version` |

`uname-a` is **not** available from the Devices API metadata; it is collected by the RTR survey script.

### Step 3 — RTR Batch Session

```
POST /real-time-response/combined/batch-init-session/v1
  body: { "host_ids": [ <aid>, ... ], "queue_offline": false }
```

Hosts that are offline or do not respond within the session timeout are marked `mitigation-status: unknown` and included in the report. The runner does not wait for them; re-run against the same host list once they are reachable.

For each `mitigation-type` in the CVE config, the runner reads the survey script from the local repo clone and uploads it to CrowdStrike RTR before executing. The upload overwrites any previously uploaded version of the same script, keeping the cloud copy in sync with the repo on every run.

```
POST /real-time-response/combined/batch-active-responder-command/v1
  body: {
    "base_command": "runscript",
    "command_string": "runscript -CloudFile='rtr-survey-modprobe-block.sh' -CommandLine='algif_aead esp4 esp6 rxrpc'",
    "batch_id": "<batch_id>"
  }
```

---

## CrowdStrike SDK Data vs. RTR Survey Data

Several fields available through the CrowdStrike Python SDK (Devices API) are incomplete or ambiguous for the purposes of vulnerability assessment. The RTR survey scripts exist partly to collect more reliable versions of this data directly from the host.

### IP Addresses

The Devices API returns multiple IP addresses per host: `local_ip`, `external_ip`, and one or more addresses from `network_interfaces`. In practice it can be difficult to determine which of these is the address the host's owner would recognise as its "primary" IP.

The `external_ip` field records the address the host appears to connect from when it calls home to the CrowdStrike backend. On hosts sitting behind a NAT or SNAT gateway — which is common in cloud and data-centre environments — this will be the gateway's address, not the host's own. It is therefore unreliable as an identifier and should not be used as a primary key for asset correlation. Matching `asset-id` to an FQDN or ownership record via a CMDB or DNS lookup is a more reliable approach.

The report captures all available IP addresses under `ip-addrs.all` and surfaces `local_ip` and `external_ip` separately, leaving the determination of which is "primary" to the enrichment step.

### Kernel Version

The `os_kernel_version` field returned by the Devices API reflects what the Falcon sensor last recorded, which may lag behind the running kernel or reflect a different version string than what the OS itself reports.

More importantly, some Linux distributions maintain multiple kernel variants simultaneously (e.g., a distro kernel alongside a hardware-enablement or cloud-optimised kernel), and the naming conventions differ by distribution and vendor. Whether a specific kernel string represents a vulnerable or patched build often requires cross-referencing the vendor's advisory, and the SDK field alone may not provide enough detail to make that determination reliably.

`uname -a` provides a more complete and authoritative picture: it reports the exact running kernel string as the OS sees it, including build metadata that is sometimes the only reliable way to distinguish a patched kernel from an unpatched one of the same base version. This is why the RTR survey script collects `uname -a` even when `os_kernel_version` is available from the SDK — both are included in the report, and the RTR-sourced value should be treated as the more authoritative of the two.

---

## RTR Survey Scripts

Survey scripts are intentionally narrow. They **only collect facts** and emit JSON to stdout. All decision logic (is this host mitigated?) runs in the Python runner after data collection.

Every survey script emits a start sentinel as its first line and an end sentinel as its last line:

```
##RTR-SURVEY-START##
... data ...
##RTR-SURVEY-END##
```

The runner checks for the presence of `##RTR-SURVEY-END##` in the collected output. If it is absent, the script is assumed to have terminated prematurely on the target host — due to a crash, timeout, or the host going away mid-run — and the host is marked `rtr-status: incomplete` / `mitigation-status: unknown`. Partial data from an incomplete run is discarded rather than used.

### `rtr-survey-modprobe-block.sh`

Surveys the presence of module blacklist/deny entries in `/etc/modprobe.d/` and whether each module is currently loaded.

```bash
#!/usr/bin/env bash
# rtr-survey-modprobe-block.sh
# Usage: rtr-survey-modprobe-block.sh <module1> [module2 ...]
# Emits: start sentinel, JSON array of per-module observations,
#        uname -a object, end sentinel
#
# Mitigation-status logic is intentionally NOT done here.
# The caller (rtr-vuln-runner.py) evaluates status from the facts below.

# Emit start sentinel before set -euo so it appears in stdout even if
# the script exits early due to a shell error.
printf '##RTR-SURVEY-START##\n'

set -euo pipefail

modules=("$@")
sep=""
printf '['

for mod in "${modules[@]}"; do
  # Search all modprobe.d files for blacklist/install-null entries
  block_entry=$(grep -rh \
    -e "^[[:space:]]*blacklist[[:space:]]\+${mod}[[:space:]]*$" \
    -e "^[[:space:]]*install[[:space:]]\+${mod}[[:space:]]\+/bin/false" \
    -e "^[[:space:]]*install[[:space:]]\+${mod}[[:space:]]\+/dev/null" \
    /etc/modprobe.d/ 2>/dev/null | head -1 || true)

  # Check if the module is currently resident in the kernel
  loaded_line=$(lsmod 2>/dev/null | awk -v m="$mod" '$1==m {print $0}' | head -1 || true)

  # Emit compact JSON for this module
  printf '%s{"module":"%s","block_entry":%s,"loaded":%s}' \
    "$sep" \
    "$mod" \
    "$([ -n "$block_entry" ] && printf '"%s"' "$(echo "$block_entry" | sed 's/"/\\"/g')" || echo 'null')" \
    "$([ -n "$loaded_line" ] && echo 'true' || echo 'false')"

  sep=","
done

printf ']\n'

# Collect uname -a while we're here (avoids a second RTR round-trip)
uname_a=$(uname -a 2>/dev/null || echo "unknown")
printf '{"uname_a":"%s"}\n' "$(echo "$uname_a" | sed 's/"/\\"/g')"

printf '##RTR-SURVEY-END##\n'
```

**Output example:**

```
##RTR-SURVEY-START##
[
  {"module":"algif_aead","block_entry":"blacklist algif_aead","loaded":false},
  {"module":"esp4","block_entry":null,"loaded":true},
  {"module":"esp6","block_entry":null,"loaded":false},
  {"module":"rxrpc","block_entry":null,"loaded":false}
]
{"uname_a":"Linux web01 5.15.0-101-generic #111-Ubuntu SMP ..."}
##RTR-SURVEY-END##
```

---

## Mitigation Status Logic

The runner evaluates status from the raw survey data **after** RTR collection. Logic is centralised in the Python runner, not spread across shell scripts.

For `mitigation-type: modprobe-block`, the rules are:

| Condition | Status |
|---|---|
| All required modules: block entry present AND `loaded: false` | **full** |
| All required modules: block entry present, but ≥1 module still `loaded: true` | **partial** — blacklisted but not yet effective; reboot required |
| Some modules blocked, some not | **partial** |
| No modules have a block entry | **none** |

"Required modules" are the items listed under `mitigation-data` in the CVE config.

---

## Report Output Schema

**Filename conventions:**

```
CVE-<ID>-<vuln-type>-<YYYYMMDDTHHMMSSz>.json      # report data
CVE-<ID>-<vuln-type>-<YYYYMMDDTHHMMSSz>.errlog     # stderr from RTR sessions (if any)
```

Both files share the same timestamp so a report and its error log are trivially paired. The `.errlog` file is only written if at least one host produced stderr output; it is omitted on clean runs.

**Errlog format** — one entry per host that produced stderr, separated by blank lines:

```
aid: a1b2c3d4e5f6...
hostname: web-prod-07
rtr-status: incomplete
--- stderr ---
bash: write error: No space left on device
```

Example: `CVE-2026-31431-kernel-20260609T143201Z.errlog`

**Top-level structure:**

```json
{
  "report-meta": {
    "cve": "CVE-2026-31431",
    "vuln-type": "kernel",
    "generated-at": "2026-06-09T14:32:01Z",
    "runner-version": "1.0.0",
    "spotlight-total-exposed": 142,
    "hosts-surveyed": 138,
    "hosts-unreachable": 4
  },
  "hosts": [ ... ]
}
```

**Per-host record:**

```json
{
  "asset-id": "a1b2c3d4e5f6...",
  "cid": "abc123...",
  "hostname": "web-prod-07",
  "ip-addrs": {
    "local": "10.20.30.40",
    "external": "203.0.113.12",
    "all": ["10.20.30.40", "172.16.5.2"]
  },
  "kernel-version": "5.15.0-101-generic",
  "uname-a": "Linux web-prod-07 5.15.0-101-generic #111-Ubuntu SMP ...",
  "mitigation-status": "partial",
  "mitigations": [
    {
      "mitigation-type": "modprobe-block",
      "modules": [
        {
          "module": "algif_aead",
          "block-entry": "blacklist algif_aead",
          "loaded": false,
          "effective": true
        },
        {
          "module": "esp4",
          "block-entry": null,
          "loaded": true,
          "effective": false
        },
        {
          "module": "esp6",
          "block-entry": null,
          "loaded": false,
          "effective": false
        },
        {
          "module": "rxrpc",
          "block-entry": null,
          "loaded": false,
          "effective": false
        }
      ]
    }
  ],
  "rtr-status": "success",
  "rtr-error": null
}
```

**`mitigation-status` values:**

| Value | Meaning |
|---|---|
| `full` | All mitigations in place and effective |
| `partial` | Some mitigations present, or present but requiring reboot |
| `none` | No mitigations detected |
| `unknown` | RTR session failed or data was inconclusive |
| `incomplete` | Survey script started but did not emit the end sentinel — terminated prematurely |

---

## `rtr-vuln-runner.py` — Interface & Design

### CLI

```
usage: rtr-vuln-runner.py [-h] --cve CVE [--vuln-type {kernel,config,package}]
                          [--cids CID [CID ...]]
                          [--hosts HOSTS_FILE] [--previous-report FILE]
                          [--output-dir OUTPUT_DIR]
                          [--output-format {json,csv,yaml}]
                          [--repo-root PATH] [--dry-run]

arguments:
  --cve CVE-2026-31431        CVE identifier (required)
  --vuln-type kernel          Limit to one vuln-type (default: all types for CVE)
  --cids "Wavelo Prod" "TCX"  One or more CID names to limit scope (default: all CIDs
                              under the parent)
  --hosts aidlist.txt         Newline-delimited AID list; skips Spotlight query

  Host scope precedence (most specific wins):
    --hosts supplied   → use exactly those AIDs; --cids and Spotlight are ignored
    --cids supplied    → query Spotlight scoped to the named CIDs
    neither supplied   → query Spotlight across all CIDs under the parent
  --previous-report FILE      Prior report file; hosts with mitigation-status: full
                              are skipped and their previous data carried forward
  --output-dir ./reports-data Output directory (default: ./reports-data)
  --output-format csv         Report format: csv (default), json, yaml
  --repo-root PATH            Root of the local repo clone (default: directory of the script)
  --dry-run                   Resolve hosts and configs; skip RTR execution
```

### Processing Flow

```
1.  Parse args
2.  Load CVE config(s) from <repo-root>/rtr-vuln-config/
    └─ Error if no config found for --cve [--vuln-type]
3.  Confirm each mitigation-type has a matching <repo-root>/rtr-vuln-scripts/ file
4.  If --previous-report supplied:
    └─ Load prior report; index hosts by asset-id
5.  Resolve target CIDs:
    a. Query Flight Control API for all child CIDs under the parent
    b. If --cids supplied: match names against child CID list; error on no match
    c. If --cids omitted: use all child CIDs (default)
6.  Query Spotlight API for vulnerable AIDs, scoped to target CIDs
    (skip if --hosts supplied)
7.  Remove AIDs whose asset-id appears in previous report with
    mitigation-status: full  (those hosts are already mitigated)
    └─ Carry their previous report records forward into the new report
8.  Batch-fetch host metadata from Devices API (100 AIDs / request)
9.  Open RTR batch session (queue_offline=false)
10. For each mitigation block in CVE config:
    a. Upload survey script from local clone to CrowdStrike RTR (overwrite)
    b. Run script against batch session with mitigation-data as args
    c. Poll for completion (with timeout)
    d. Parse stdout JSON per host; check for end sentinel
11. For each host: compute mitigation-status from survey data
12. Assemble report object (surveyed hosts + carried-forward fully-mitigated hosts)
13. Write report file:  <output-dir>/<CVE>-<type>-<timestamp>.<format>
14. Print summary to stderr:
    Surveyed: 98  Full: 42  Partial: 67  None: 23  Unknown: 6  Skipped (prev full): 40
```

### Key Design Constraints

- **No logic in RTR scripts.** Survey scripts emit raw facts only. All classification runs in Python, making it testable without CrowdStrike access.
- **Fail gracefully on unreachable hosts.** Hosts that don't respond within the RTR timeout get `rtr-status: timeout` and `mitigation-status: unknown`. They are still included in the report.
- **No credentials in config files.** CrowdStrike API credentials are read from environment variables (`FALCON_CLIENT_ID`, `FALCON_CLIENT_SECRET`) or a credentials file outside the repo. Credentials must be generated from the parent CID to provide cross-CID host visibility.
- **Idempotent.** Re-running against the same CVE and host list produces a new timestamped file; it never overwrites a prior report.
- **Batch size limits.** RTR batch sessions support up to 5,000 hosts. The runner will automatically split larger host lists into sequential batches and merge results.

---

## Downstream Enrichment

The report is intentionally minimal. Enrichment of `asset-id` to FQDN, business unit, owner, or ticket system is out of scope for the runner and should be handled by separate tooling consuming the report file.

Suggested downstream uses:

- **Asset correlation** — join `asset-id` to CMDB or DNS records to resolve FQDNs and ownership.
- **Ticket creation** — filter `mitigation-status: none` hosts and open Jira/ServiceNow tickets automatically.
- **Dashboard ingestion** — parse report JSON into Splunk, Elastic, or a custom dashboard for fleet-wide trend tracking.
- **Remediation validation** — re-run the runner after a remediation wave; diff the two timestamped reports to confirm coverage.

---

## Future Vuln-Types

The config schema and runner are designed to accommodate additional vuln-types without structural changes.

### `config` (planned)

Covers CVEs mitigated by adding or modifying a value in a config file (e.g., `sysctl`, `/etc/ssh/sshd_config`).

Example mitigation block:

```yaml
- mitigation-type: sysctl-value
  mitigation-data:
    - key: net.ipv4.conf.all.rp_filter
      expected-value: "1"
```

Survey script `rtr-survey-sysctl-value.sh` would emit whether the key exists and its current value.

### `package` (planned)

Covers CVEs mitigated by removing or upgrading a package.

```yaml
- mitigation-type: package-version
  mitigation-data:
    - package: openssl
      operator: ">="
      version: "3.0.2-0ubuntu1.15"
```

Survey script `rtr-survey-package-version.sh` would emit the installed version (if any).

A single CVE config may combine multiple types, e.g., a CVE that can be fixed either by kernel upgrade or by removing a userspace package.

---

## Security & Operational Considerations

**API credentials and multi-CID access.** The runner must be able to enumerate and survey hosts across all CIDs in the organisation. API credentials scoped to a single child CID will only see that CID's hosts. Credentials should be generated from the **parent CID** using CrowdStrike's Flight Control (MSSP) console, which provides cross-CID visibility. The runner passes these credentials to the falconpy SDK; no per-child-CID credential management is required.

**RTR permissions.** The API client used by the runner needs at minimum the following scopes: `Hosts: Read`, `Spotlight Vulnerabilities: Read`, `Real Time Response: Write`, and `Real Time Response (admin): Write`. These scopes must be granted on the parent CID credential so that they apply across child CIDs.

**Script review gate.** RTR survey scripts are read from the local repo clone and uploaded to CrowdStrike on every run, overwriting any prior version. This keeps the cloud copy in sync with the repo automatically. Scripts must be reviewed and merged via pull request before reaching the clone used to run the tool — the repo is the gate, not a separate upload step.

**Audit log.** All RTR sessions are logged by CrowdStrike. The runner should log its own session IDs and batch IDs to its run log to enable correlation.

**Rate limits.** The Spotlight API and RTR APIs have per-minute rate limits. The runner should implement exponential back-off on 429 responses.

**Sensitive output.** Report files may contain host topology data (IPs, kernel versions). Store output in a restricted-access location and treat as internal-confidential.

---

## Implementation Milestones

| Phase | Deliverable | Notes |
|---|---|---|
| 1 | CVE config schema + 2–3 seed configs | Required before any runner work |
| 2 | `rtr-survey-modprobe-block.sh` + unit tests | Testable without CrowdStrike |
| 3 | `rtr-vuln-runner.py` — Spotlight + metadata only | Dry-run mode, no RTR |
| 4 | `rtr-vuln-runner.py` — RTR integration + report output | First end-to-end run |
| 5 | CI scheduling + report archival | Ongoing operational use |
| 6 | `config` and `package` vuln-types | Per demand |

---

## Design Decisions

| Question | Decision |
|---|---|
| Config repo access model | Local clone required. Scripts read configs and RTR scripts directly from the filesystem; no runtime fetch from GitHub. |
| RTR script hosting | Upload fresh from the local clone on every run, overwriting any prior version. Always in sync with the repo; no separate upload step to manage. |
| Offline host handling | Emit `mitigation-status: unknown` and move on. Offline hosts are included in the report. Re-run to pick them up once reachable. |
| Report destination | Write to `reports-data/` in the local repo clone (gitignored). Archival and downstream distribution are handled separately.
