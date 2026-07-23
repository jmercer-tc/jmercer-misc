# OpenStack Security Group Audit — Manager Update
**Date: 2026-07-23** · Epic: [SECO-3668](https://wiki-tucows.atlassian.net/browse/SECO-3668) · Prepared by Jim Mercer

---

## 1. Ticket status — SECO-3668 and downstream

Numbers pulled live from Jira today. Headline: **almost everything is still sitting in Backlog** — the investigation/analysis phase is far along, but very little has moved into active remediation yet.

| Ticket | Type | Summary | Status | Notes |
|---|---|---|---|---|
| SECO-3668 | Epic | OpenStack SG Audit & Remediation | Backlog | Parent epic |
| SECO-3655 | Story | Investigation | Backlog | |
| SECO-3656 | Sub-task | jmcdonald-dev publicly exposed VM | Backlog | Floating IP still assigned; CR-43285/CR-43375 in peer review |
| SECO-3670 | Sub-task | Share raw data with Shepherd team | Backlog | Files need re-attaching (CSV/scripts refreshed) |
| SECO-3669 | Story | Remediation (parent for tenant sub-tasks below) | Backlog | |
| SECO-3654 | Sub-task | VRRP sec-policy | Backlog | Linked SHEP2-812 |
| SECO-3657 | Sub-task | Wavelo GSLB virtual A10 | Backlog | |
| SECO-3667 | Sub-task | {qa,prod}_dish_db_replica cleanup | Backlog | Scope likely needs expanding to cover `dish_db_dwh` variants (see Section 2, "Remaining non-compliant sg-rules — overview," below) |
| SECO-3673 | Sub-task | dev_hoofprints default-SG cleanup | Backlog | Correctly scoped: 203 of 567 non-compliant rules are default-SG |
| SECO-3674 | Sub-task | prod_bareos default-SG | **Done** | Confirmed via fresh recount — 0 remaining default-SG rows |
| SECO-3675 | Sub-task | trs_ry_prod remediation | Backlog | |
| SECO-3676 | Sub-task | Global ICMP policy proposal (791 rules) | Backlog | **Rejected by Shepherd eng 2026-07-15** — "Not a feature/bug" |
| SECO-3677 | Sub-task | c18e / Wavelo Nomad tenants (~1,890 rules) | Backlog | **Rejected**, same reason/date |
| SECO-3678 | Sub-task | Consul policies (111 rules) | Backlog | **Rejected**, same reason/date |
| SECO-3680 | Sub-task | tch-ssh-tunnel / DMNS-554 | Backlog | |
| SECO-3681 | Sub-task | jmcdonald-dev decommission | Backlog | Blocked on Joe McDonald (CR-43285, CR-43375) |
| SECO-3683 | Sub-task | Remove 216.40.38.249/32, non-FIP VMs | Backlog, **on hold** | Premise was wrong — needs revision (see Section 3, "Challenges quantifying, organizing, and prioritizing remediation," below) |
| SECO-3684 | Sub-task | Remove 216.40.38.249/32, kafkapublic | Backlog, **on hold** | Same |
| SECO-3643 | Related | allowed_address_pairs monitoring proposal | **Ready for Development** | Only ticket actively queued |

**Downstream / linked tickets:**

| Ticket | Status | Assignee | Notes |
|---|---|---|---|
| SHEP2-812 | To Do | Ryan Bannon | VRRP protocol option, approved, no activity |
| SHEP2-813 | To Do | — | Sec-policy for existing bra2 rules |
| SHEP2-814 | To Do | — | Sec-policy for existing cnco rules |
| SHEP2-817 | To Do | Ryan Bannon | Mandatory ticket-reference field, approved, no activity |
| SHEP2-818 | To Do | — | Block rule additions to `default` SG |
| CR-43012 | Implementing | Jonathan Brunath | Release Train Dashboard public IPs |
| CR-43285 | Peer review | — | Remove jmcdonald-dev floating IP |
| CR-43375 | Peer review | — | Migrate timeoff bot off jmcdonald-dev (depends on CR-43285) |
| DMNS-554 | Backlog | — | Allowed-address-pairs security issue (tch-ssh-tunnel) |

The three rejected tickets (SECO-3676/3677/3678) have had **no activity since the 2026-07-15 rejection** — they need to be re-routed to tenant-owning teams rather than Shepherd engineering (see Section 3, "Challenges quantifying, organizing, and prioritizing remediation," below).

---

## 2. Remaining non-compliant sg-rules — overview

Cache refreshed today. **8,599 non-compliant ingress rules** on active VMs, across 332 tenants (bra2 + cnco) — essentially flat vs. the 8,600 recorded a week ago. That's expected: no remediation tickets have actually landed yet apart from SECO-3674.

Rather than one flat pile, the rules split into three risk tiers:

| Tier | Definition | Count | % of total | Instances |
|---|---|---|---|---|
| **Tier 1 — Live exposure** | Non-compliant + floating IP attached *today* | 173 | 2.0% | 40 |
| **Tier 2 — Loaded gun** | Non-compliant, sits in `default` SG, no floating IP *yet* | 911 | 10.6% | 455 |
| **Tier 3 — Everything else** | Non-compliant, no floating IP, not in `default` SG | 7,515 | 87.4% | 636 |

**Tier 1 top tenants:** prod_ops_services 93, trs_ry_prod 28, prod_hostedemail 14, trs_monitoring 10, jmcdonald-dev 8, tucows_billing/_prod 6, dish_db family 14.

**Cross-cutting root cause — the `default` security group:** 939 of the 8,599 rules (10.9%) sit in a security group literally named `default`; 927 of those (99%) are open to `0.0.0.0/0`. Cleaning up `default`-SG usage alone would resolve Tier 2 entirely, plus 28 Tier-1 rows, plus two-thirds of the ICMP finding (SECO-3676) — it's a single structural fix that pays down several separate findings at once.

---

## 3. Challenges quantifying, organizing, and prioritizing remediation

**a) The three biggest-volume tickets are dead-ended.** SECO-3676 (ICMP, 791 rules), SECO-3677 (c18e/Nomad gap, ~1,890 rules), and SECO-3678 (Consul, 111 rules) — together nearly 3,560 rules (~41% of all non-compliance) — were all rejected by Shepherd engineering on the same day with the same comment: "Not a feature/bug." These are policy-authorship asks, not code changes, so they need to go to the teams that *own* the affected tenants instead. Ownership is only confirmed for one family so far (hoofprints → Ting MSE Engineering); several others (prod_cne_dx, prod_elastic_services, the gopher/ops_dns/observability group) are still unconfirmed. This outreach has been **deliberately deferred** pending today's prioritization conversation.

**b) A previously-load-bearing assumption turned out to be wrong.** SECO-3683/3684 assumed `216.40.38.249/32` was dead-letter cnco SNAT leftover. It's actually the live Mowat office VLAN 74 SNAT IP — actively used by ops staff. Both tickets are on hold pending a rewrite; this cost real analysis time and is a good example of why the tenant/rule data needs independent verification before tickets go out.

**c) Existing tickets don't cover the volume you'd expect.** Even if every currently-open, non-rejected ticket were executed today, it only accounts for a small slice of the 8,599 — most of the count sits in patterns that have no ticket yet at all (ephemeral ports 32768-60999 from anywhere: 394 rules; port 8080 from RFC1918 supernets: 449; Kafka 9092-93 from RFC1918: 224; a single NTP server misconfigured as a source: 173 — an easy win). These are drafted as a future "policy right-sizing" bundle but not yet filed.

**d) Newly surfaced, currently unticketed exposure.** Today's floating-IP cross-reference surfaced three tenants with live exposure that were previously off the radar entirely: `trs_monitoring` (10 rules), `tucows_billing`/`tucows_billing_prod` (6 rules), and the `dish_db_dwh` variants (8 rules, likely an SECO-3667 scope expansion rather than a new ticket).

**Proposed path (drafted, not yet actioned) — four phases:**
1. **Phase 0** — one sub-task per Tier-1 (live-exposure) tenant, highest count first
2. **Phase 1** — one consolidated `default`-SG cleanup ticket (closes Tier 2 + the Tier-1/default overlap)
3. **Phase 2** — bundle the unticketed Tier-3 patterns (ephemeral ports, port 8080, NTP, Kafka) + re-route the rejected SECO-3676/3677/3678 content to tenant owners
4. **Phase 3** — deferred architecture work (block `default`-SG rule additions, broader policy right-sizing) once compliance is largely closed out

---

## 4. Open question for this meeting: what determines priority order?

This is the crux worth deciding together. Four different, defensible ways to sort the same 8,599 rules give four different "what to do first" answers:

| Prioritization lens | What it optimizes for | What it captures | Trade-off |
|---|---|---|---|
| **Exposure (Tier 1)** | Actual live risk right now | 173 rules (2.0%) — small, but these are internet-reachable *today* | Fixing all of Tier 1 barely moves the headline non-compliance number |
| **Structural risk (Tier 2 / default-SG)** | Rules that *could* become exposed with zero warning (any VM can get a floating IP without re-triggering an SG review) | 911 rules (10.6%), cross-cutting across many other findings | Not urgent today, but the "loaded gun" framing exists precisely because that can change silently |
| **Easiest to fix** | Fast, low-effort wins | E.g. single-source NTP (173 rules, one config change), the four RFC1918-scoped patterns (~1,240 rules combined) | Doesn't touch actual risk at all — these are almost entirely Tier 3, already lowest-priority by exposure |
| **Most rules closed per ticket** | Biggest visible dent in the total count | prod_mse alone is 1,341 rules (15.6% of everything) — but it's Tier 3: no floating IP, not in default SG | Best "number go down" optics, weakest correlation with actual exposure reduction |

The tension in one sentence: **the rules that are riskiest (Tier 1/2) are a small fraction of the total, while the rules that would move the compliance percentage the most (Tier 3, e.g. prod_mse) are already the lowest-risk ones.** Optimizing for either one alone tells a different story to leadership — "we closed our worst exposure" vs. "we cut non-compliance by X%."

The phased plan described above in Section 3 ("Challenges quantifying, organizing, and prioritizing remediation") is one attempt to sequence both (urgent-small first, then structural, then volume) rather than picking one lens exclusively — but that sequencing hasn't been signed off yet. Also unresolved: **prod_ops_services** is simultaneously your largest Tier-1 tenant (93 live-exposed rules) *and* part of the c18e/Nomad family whose owner-outreach is on hold pending (a) above — so "fix the riskiest thing first" and "outreach for that family is deferred" are currently in direct conflict for this one tenant.

---

## Bottom line for the meeting
- Investigation is mature (332 tenants / ~20,000 rules analyzed, tiered by risk, root-caused to a `default`-SG structural pattern); remediation execution has barely started (1 of 19 SECO sub-tasks done).
- ~41% of known non-compliance is currently blocked on a rejected ticket path and needs re-routing to tenant-owning teams — a resourcing/outreach ask, not an engineering one.
- The main decision needed: adopt a sequencing philosophy (risk-first, effort-first, or volume-first) so tickets can start moving instead of stacking up in Backlog. Recommendation on the table is the 4-phase plan from Section 3 ("Challenges quantifying, organizing, and prioritizing remediation"), but the exposure-vs-volume tension discussed in Section 4 ("Open question for this meeting: what determines priority order?") is the part that most needs a management call.
