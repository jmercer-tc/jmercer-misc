# Proposal: Monitoring and Alerting for `allowed_address_pairs` Misuse

**Date:** July 8, 2026  
**Author:** Jim Mercer  
**Status:** Draft

---

## Problem Statement

The OpenStack `allowed_address_pairs` parameter is a port-level attribute that, when set, permits a virtual machine to send and receive traffic using IP addresses other than its own assigned port IP. This is an essential capability for a small number of legitimate use cases in our infrastructure.

However, it can be abused. A VM with `allowed_address_pairs` set to `0.0.0.0/0` — or to an IP range it should not claim — can bypass the security group and security group rule regime enforced by Shepherd. Shepherd's callback mechanism validates that security group rules comply with approved policies at the time of creation, but has no visibility into `allowed_address_pairs` configuration on neutron ports. A malicious or misconfigured instance using this parameter can effectively circumvent security controls that Shepherd works to enforce.

An audit of our current OpenStack infrastructure identified **23 instances** with `allowed_address_pairs` configured, across both bra2 and cnco. Of these, 22 are load balancers or ADC (Application Delivery Controller) appliances with legitimate operational requirements. One instance — `tch-ssh-tunnel-1` — was identified as anomalous: an SSH tunnel VM with `0.0.0.0/0` in `allowed_address_pairs` with no legitimate justification. This instance is currently being remediated.

---

## Scope of This Proposal

This proposal describes a **monitoring and alerting** solution. It does not prevent a VM from being configured with non-compliant `allowed_address_pairs` entries — it detects and reports them after the fact. Remediation remains a manual process, initiated by the alert and carried out by the responsible team.

No changes are required to OpenStack, the IaaS platform, or Shepherd. The solution operates entirely outside the infrastructure stack, consuming data via the Shepherd API and DNS.

---

## Interaction Between `allowed_address_pairs` and Security Group Rules

**`allowed_address_pairs` wins. Security group rules do not apply to traffic using claimed IPs.**

A concrete example: `tch-ssh-tunnel-1` had `0.0.0.0/0` in its `allowed_address_pairs`. Its security group rules restricted inbound access on port 2222 to three specific IP addresses. Yet the instance was reachable on port 2222 from the general internet — because `allowed_address_pairs = 0.0.0.0/0` disabled the anti-spoofing filter at the port level, causing OpenStack to stop enforcing security group rules for traffic arriving at that VM.

In plain terms: a VM with `0.0.0.0/0` in `allowed_address_pairs` has no effective network access controls, regardless of what security group rules are defined. The security group rules are present but not enforced. Any IP on the internet can reach any open port on that VM.

---

## Legitimate Use Cases

The operational requirement for `allowed_address_pairs` is real but narrow. In our current infrastructure it is confined to three categories:

**Software and appliance load balancers** (`lb01a/b`, etc.) — HA load balancer pairs use `allowed_address_pairs` to hold shared virtual IP addresses (VIPs). Both nodes in a pair must be able to send and receive traffic for the VIP, regardless of which node currently owns it. This is fundamental to how active/standby HA works in OpenStack.

**A10 virtual ADCs** (`adc*`) — Virtual A10 Application Delivery Controllers serve public-facing VIPs directly on their interfaces (no NAT). OpenStack's anti-spoofing layer would otherwise drop traffic for IPs not assigned to the port. `allowed_address_pairs` is required to allow the ADC to legitimately handle this traffic.

**Kubernetes nodes** — Kubernetes assigns pod IP addresses from a pod CIDR that is separate from the node's own IP. When pods communicate across nodes, traffic leaves the node with the pod IP as source. OpenStack treats this as spoofed traffic unless `allowed_address_pairs` is configured with the pod CIDR on that node's port. This is applied automatically by the Kubernetes CNI plugin or CAPI at cluster provisioning time.

In each case, `allowed_address_pairs` is set to specific, known IP addresses or ranges — not to `0.0.0.0/0`. The use of `0.0.0.0/0` is never operationally justified.

---

## Why High-Level Controls Are Not Practical

Several approaches to preventing misuse at the platform level were considered:

**OpenStack `oslo.policy`** restricts which roles can set `allowed_address_pairs`, but only cluster-wide — it cannot be applied selectively per tenant. Restricting it globally would break all legitimate load balancer and ADC deployments.

**Disabling the `allowed-address-pairs` Neutron extension** removes the feature entirely for all tenants. This would make load balancer HA and direct ADC deployments impossible, causing significant operational impact.

**Shepherd enforcement** — Shepherd's Neutron callback intercepts security group rule creation but has no equivalent hook for port-level `allowed_address_pairs` modifications. Even if one were added, direct OpenStack CLI and API access would still bypass it, as demonstrated by existing instances of direct rule creation outside of Shepherd.

**Per-tenant restriction** is not supported natively by OpenStack. While conceptually desirable, it would require significant custom Neutron development.

The conclusion is that preventive control at the infrastructure level is not practical without disproportionate operational impact. The appropriate response is monitoring and alerting.

---

## Proposed Solution: `aap-monitor` — Daily Monitoring Script

### Approach

Implement a daily script that fetches live `allowed_address_pairs` data for all instances across all tenants and clusters, validates each entry against a defined set of rules, and alerts on any anomaly.

### The `aap-hosts` Whitelist

The core of the solution is a curated whitelist file — `aap-hosts` — containing the FQDNs of every VM legitimately authorised to use `allowed_address_pairs`. This avoids reliance on VM names or security group names, both of which are arbitrary and team-defined.

Each entry is either a bare FQDN, or an FQDN followed by one or more space-separated values — a CIDR, a specific IP, or `0.0.0.0/0`. Lines beginning with `#` are treated as comments and ignored.

`0.0.0.0/0` may be declared in `aap-hosts` where there is an operational justification. The PR approval process is the gate — declaring `0.0.0.0/0` requires an explicit, reviewed, documented entry. Any VM with `0.0.0.0/0` in `allowed_address_pairs` that does not have it declared in `aap-hosts` is an immediate alert.

```
# prod_mse_gslb - A10 GSLB pair (serves public VIPs directly)
adc04a.prod-mse-gslb.cnco2.tucows.systems
adc04b.prod-mse-gslb.cnco2.tucows.systems
adc05a.prod-mse-gslb.bra2.tucows.systems

# pte_hostedemail - HA load balancer pair
lb01a.pte-hostedemail.bra2.tucows.systems
lb01b.pte-hostedemail.bra2.tucows.systems

# lab_dkoo - K8s hub cluster nodes (pod CIDR per node)
hub-cp-0.lab-dkoo.cnco2.tucows.systems 10.1.3.0/24
hub-cp-1.lab-dkoo.cnco2.tucows.systems 10.1.5.0/24
hub-worker-0.lab-dkoo.cnco2.tucows.systems 10.1.1.0/24

# pte_hostedemail - LB requires 0.0.0.0/0 for <documented reason>
lb01a.pte-hostedemail.bra2.tucows.systems 0.0.0.0/0
```

A companion file — `aap-public-ips` — maintained in the same repository and subject to the same git/PR approval process, contains the list of Tucows-owned public IP ranges. Any `allowed_address_pairs` entry that falls within a range in `aap-public-ips` is considered acceptable for known AAP hosts. This file is maintained separately so that IP range changes (acquisitions, reassignments) can be managed independently of the host whitelist.

FQDNs should preferably be under `tucows.systems`, which is managed by OpenStack's DNS service and is therefore authoritative — only properly provisioned VMs will have records there. Other subdomains are permitted, provided the FQDN resolves to the VM's actual fixed IP address.

All changes to `aap-hosts` are made via pull request and require approval before merging. This means every addition, modification, or removal is tracked in git history and subject to review — the PR process serves as the approval and audit mechanism for whitelist changes.

**Validation:** At runtime, each FQDN is resolved via DNS and matched against the VM's fixed IP from the instance data. If the FQDN does not resolve, or resolves to the wrong IP, the entry is treated as invalid and the VM is flagged — providing natural detection of stale whitelist entries.

### Classification Logic

A VM is considered a **known AAP host** if and only if a FQDN in `aap-hosts` resolves via DNS to an IP that matches the VM's fixed IP as returned by the Shepherd/OpenStack API. The Shepherd API is the authoritative source for what a VM's fixed IP actually is — DNS resolution is checked against it, not the other way around.

Any VM with `allowed_address_pairs` set that is **not** a known AAP host is immediately flagged as anomalous, regardless of what IPs are in its `allowed_address_pairs`.

For known AAP hosts, the entries in `allowed_address_pairs` are validated against the following rules:

The monitoring script checks whether each entry in `allowed_address_pairs` is accounted for by the VM's `aap-hosts` declaration. The rules are:

| Entry type | Verdict |
|---|---|
| IP, CIDR, or `0.0.0.0/0` explicitly declared in `aap-hosts` for this VM | Acceptable |
| IP or CIDR listed in `aap-public-ips` | Acceptable |
| RFC1918 IP within the instance's connected subnets | Acceptable |
| Any entry not covered by the above | **Alert** |

This means `0.0.0.0/0` is acceptable only when explicitly declared in `aap-hosts` for that VM — which requires a reviewed and approved PR. Any undeclared `0.0.0.0/0` is an immediate alert.

### Implementation

The script would run as a scheduled daily task and perform the following steps:

1. **Resolve `aap-hosts`** — DNS-resolve all FQDNs to build a set of known-good IP → FQDN mappings. Flag any unresolvable entries.

2. **Fetch all instances** — iterate all departments and tenants across both clusters via the Shepherd API, fetching `ports_json` for each instance (available via the single-instance endpoint `/v1/project/{project_id}/instance/{instance_id}`).

3. **For each instance with non-empty `allowed_address_pairs`:**
   - Check if the instance's fixed IP is in the resolved whitelist
   - If not on whitelist → alert immediately
   - If on whitelist → validate each `allowed_address_pairs` entry against the rules above

4. **Baseline comparison** — compare findings against the previous day's results. Alert only on **new** anomalies; suppress known ongoing issues to avoid alert fatigue.

5. **Output** — generate a daily digest containing:
   - New anomalies found (high priority)
   - Anomalies resolved since last run
   - Whitelist entries that failed DNS resolution
   - Summary count of known AAP hosts and their current status

### Alert Severity

| Condition | Severity |
|---|---|
| VM not on whitelist has any `allowed_address_pairs` | High |
| Known AAP host has `0.0.0.0/0` | High |
| Known AAP host has non-Tucows public IP | High |
| `aap-hosts` FQDN fails DNS resolution | Medium |
| `aap-hosts` FQDN resolves to wrong IP | Medium |
| Known AAP host has RFC1918 IP outside connected subnets | Low |

---

## Maintenance

All changes to `aap-hosts` are made via pull request against this repository and require peer approval before merging. Git history provides a full audit trail of every change, including who requested it, who approved it, and when.

**Adding a new AAP host:** When a new load balancer, ADC, or K8s cluster is deployed, the deploying team submits a PR adding the relevant FQDNs (and CIDRs where applicable) to `aap-hosts` before or as part of the deployment. This should be a documented requirement in the runbook for these workload types.

**Removing an AAP host:** When a VM is decommissioned, its DNS record under `tucows.systems` is removed. The `aap-hosts` entry will fail DNS resolution on the next monitoring run, generating a medium alert. A PR to remove the stale entry should be submitted promptly.

**New use cases:** If a workload type beyond load balancers, ADCs, and K8s nodes requires `allowed_address_pairs`, the team must submit a PR with documented justification before deployment. The PR review process serves as the approval gate.

**Updating public IP ranges:** Changes to Tucows-owned public IP allocations (new ranges, reassignments, retirements) are reflected by submitting a PR against `aap-public-ips`. This is managed independently of `aap-hosts` so that IP range changes do not require re-review of the host whitelist.

---

## Summary

The `allowed_address_pairs` parameter represents a small but real attack surface in our OpenStack infrastructure. The legitimate use cases are well-understood and limited to load balancers, ADCs, and Kubernetes nodes. High-level platform controls are not practical without significant operational impact. The proposed monitoring approach — a curated FQDN whitelist validated against live DNS, with daily automated comparison against all running instances — provides effective detection of misuse with low false-positive rates and a clear operational maintenance process.
