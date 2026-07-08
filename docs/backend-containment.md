# Backend Containment (Draft)

## Problem

We have an ongoing, and growing, problem with supply-chain exploits. While it is very difficult to control (with precision) the various artifacts that are being used to build and run our backends, one common element of supply-chain exploits is that they generally have the goal of exfiltrating information: secrets and tokens at a minimum, but that blast area will expand over time.

---

## Proposal

Backend systems should be contained in such a way that, at a minimum, we have a full picture of what external systems our internal systems communicate with. Once that visibility is in place, the same mechanisms can be used to progressively constrain what internal systems are permitted to communicate with externally.

---

## Context: Our Connectivity Profile

The vast majority of our internal systems communicate with each other, internal traffic dominates. A relatively small number of systems require access to external endpoints, and the bulk of those are **build-time** requirements (e.g. GitHub, package registries) as opposed to ongoing **run-time** requirements (e.g. Temporal, Stripe, T-Mobile).

This profile works in our favor: the surface area we need to control is small and well-defined.

---

## Approach

We will implement outbound containment on a **tenant-by-tenant basis**, in three phases:

**Phase 1 — Visibility (Transparent Proxy)**
Switch outbound connectivity to route through a transparent proxy. No behavior changes for internal systems. The goal is to build a complete, empirical map of what external systems each tenant communicates with, and whether that communication is build-time or run-time in nature.

**Phase 2 — Control (Non-Transparent Proxy)**
Using the inventory from Phase 1, stand up non-transparent proxies — one per tenant or per logical grouping. Internal systems connect to these proxies explicitly when requiring outbound connectivity. Allowlists are initialized from observed traffic, then reviewed and tightened.

**Phase 3 — Hardening (No Default Route)**
Remove the default route to the internet from internal systems entirely. All outbound traffic must flow through an approved proxy. Any attempt by a system to connect to an unapproved destination is either blocked outright or triggers an alert. This ensures that if an exploit begins executing internally, it is stopped — or at minimum detected — the moment it attempts unauthorized outbound communication.

Once a plan is developed, it can and should be applied equally across OpenStack, AWS, and Proxmox clusters, although each environment will have its own specific implementation.

---

## Expected Outcomes

- **Full visibility** into internal-to-external communication patterns across all tenants.
- **Reduced exfiltration risk**: compromised systems cannot freely phone home to attacker infrastructure.
- **Reverse access hardening**: internal systems without a default route cannot be used as ingress points by attackers.
- **Incremental rollout**: each phase delivers standalone value, with no big-bang cutover required.
- **Audit trail**: proxy logs provide forensic evidence if an incident does occur.
