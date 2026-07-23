# New SECO Ticket Scoping — Newly Surfaced Tier-1 Exposure

**Date: 2026-07-23** · Parent epic: [SECO-3668](https://wiki-tucows.atlassian.net/browse/SECO-3668) · Draft for review — nothing filed in Jira yet

Source: today's floating-IP cross-reference against the fresh Shepherd cache (see
`sg-audit-manager-update-2026-07-23.md`, Section 3d). These three tenant groups have
live-exposed (Tier 1: non-compliant rule + floating IP attached today), currently
unticketed non-compliant rules. Below is draft scope for each — summary,
affected rules, and a recommended fix — for review before filing.

---

## 1. `trs_monitoring` — new sub-task recommended

**Proposed title:** `trs_monitoring — remediate live-exposed default-pattern rules`
**Proposed parent:** SECO-3669 (Remediation story)

**Scope:** 10 non-compliant rules across 3 instances, all currently reachable via
floating IP.

| Instance | SG | Proto | Port | Source | Issue |
|---|---|---|---|---|---|
| metrics01 | ssh | tcp | 22 | 192.168.0.0/16 | Source is the *entire* 192.168.0.0/16 supernet, not the actual VPN CIDRs (192.168.6.0/23, 192.168.160.0/20) |
| metrics01 | web | tcp | 80 | 0.0.0.0/0 | Open to internet, no approved policy covers this |
| metrics01 | web | tcp | 443 | 0.0.0.0/0 | Same |
| puppet01 | puppet | tcp | 8140 | 0.0.0.0/0 | Puppet master port open to entire internet |
| puppet01 | ssh | tcp | 22 | 192.168.0.0/16 | Same broad-supernet issue as metrics01 |
| puppet01 | web | tcp | 80 | 0.0.0.0/0 | Open to internet |
| puppet01 | web | tcp | 443 | 0.0.0.0/0 | Same |
| swarm-m01 | ssh | tcp | 22 | 192.168.0.0/16 | Same broad-supernet issue |
| swarm-m01 | web | tcp | 80 | 0.0.0.0/0 | Open to internet |
| swarm-m01 | web | tcp | 443 | 0.0.0.0/0 | Same |

**Recommended fix:** two-part —
1. Narrow all `ssh` sources from `192.168.0.0/16` to the two actual VPN CIDRs
   (192.168.6.0/23, 192.168.160.0/20) — no functional change expected, since VPN
   clients only ever originate from those ranges.
2. For `web` (80/443, all 3 instances) and `puppet` (8140), determine whether
   internet exposure is actually required (e.g. is this a public-facing metrics
   dashboard, or should it sit behind the VPN too?) — needs a quick check with
   whoever owns `trs_monitoring` before deciding "narrow the policy" vs. "restrict
   the SG."

**Open question:** tenant owner not yet confirmed — needs the same outreach
question as the rejected SECO-3676/3677/3678 tickets (see main doc, Section 3a).

---

## 2. `tucows_billing` / `tucows_billing_prod` — new sub-task recommended

**Proposed title:** `tucows_billing(_prod) — remediate live-exposed lb01 rules`
**Proposed parent:** SECO-3669

**Scope:** 6 non-compliant rules across 1 instance (`lb01`), split across two
tenant variants (non-prod and prod).

| Tenant | Instance | SG | Proto | Port | Source | Issue |
|---|---|---|---|---|---|---|
| tucows_billing | lb01 | ssh | tcp | 22 | 10.0.0.0/8 | Broad RFC1918 supernet |
| tucows_billing | lb01 | ssh | tcp | 22 | 192.168.0.0/16 | Broad RFC1918 supernet |
| tucows_billing | lb01 | ssh | tcp | 22 | 172.16.0.0/12 | Broad RFC1918 supernet |
| tucows_billing | lb01 | web | tcp | 80 | 0.0.0.0/0 | Open to internet |
| tucows_billing | lb01 | web | tcp | 443 | 0.0.0.0/0 | Open to internet |
| tucows_billing_prod | lb01 | pingall | icmp | — | 0.0.0.0/0 | ICMP (ping) open to entire internet |

**Notable:** `lb01` in `tucows_billing` has *three separate* SSH rules, one for
each of the three RFC1918 supernets (10/8, 172.16/12, 192.168/16) — i.e. literally
all of private-address space is allowed to SSH in. This is a strong candidate for
consolidating into a single rule scoped to the actual OpenStack/VPN subnets that
legitimately need SSH access, rather than three separate blanket-supernet rules.

**Recommended fix:**
1. Replace the three broad-supernet SSH rules with specific OpenStack subnet /
   VPN CIDRs (per standing guidance: avoid 10.0.0.0/8, 172.16.0.0/12,
   192.168.0.0/16 in new policy).
2. Web (80/443) is presumably intentional for a load balancer named `lb01` —
   confirm it's meant to be public, and if so this may need a policy exception
   rather than a rule change (billing infra fronted by a public LB is plausible,
   but should be confirmed, not assumed).
3. ICMP-from-anywhere on the prod variant — low risk but easy to narrow or drop
   if not needed for monitoring.

**Open question:** same tenant-ownership outreach gap as `trs_monitoring` above.

---

## 3. `dish_db_dwh` variants — recommend as SECO-3667 scope expansion, not a new ticket

**Not proposed as a new ticket.** SECO-3667 already covers `{qa,prod}_dish_db_replica`
cleanup under the same parent story (SECO-3669), and this is the same underlying
pattern (Dish partner Postgres access) just under differently-named tenants that
weren't in the original ticket's scope.

**Scope:** 8 non-compliant rules across 8 instances, split across two tenants.

| Tenant | Instance | SG | Proto | Port | Source |
|---|---|---|---|---|---|
| nonprod_dish_db_dwh | pgsql-dish-dwh-mse-01 | pgsql-dish-dwh-mse-sg | tcp | 55432 | 67.214.55.0/24 |
| nonprod_dish_db_dwh | pgsql-dish-int-mse-01 | pgsql-dish-dwh-mse-sg | tcp | 55432 | 67.214.55.0/24 |
| nonprod_dish_db_dwh | pgsql-dish-pte-mse-01 | pgsql-dish-pte-mse-sg | tcp | 55432 | 67.214.55.0/24 |
| nonprod_dish_db_dwh | pgsql-dish-pte-turbine-01 | pgsql-dish-pte-turbine-sg | tcp | 55432 | 67.214.55.0/24 |
| prod_dish_db_dwh | pgsql-dish-dwh-accts-01 | pgsql-dish-dwh-mse-sg | tcp | 55432 | 67.214.56.0/24 |
| prod_dish_db_dwh | pgsql-dish-dwh-billing-01 | pgsql-dish-dwh-mse-sg | tcp | 55432 | 67.214.56.0/24 |
| prod_dish_db_dwh | pgsql-dish-dwh-mse-01 | pgsql-dish-dwh-mse-sg | tcp | 55432 | 67.214.56.0/24 |
| prod_dish_db_dwh | pgsql-dish-dwh-turbine-01 | pgsql-dish-dwh-turbine-sg | tcp | 55432 | 67.214.56.0/24 |

**Note:** unlike the two groups above, these sources are *not* broad RFC1918
supernets — they're specific /24s (67.214.55.0/24 non-prod, 67.214.56.0/24 prod)
that read as a partner/customer network, consistent with "dish" partner naming.
This looks like intentional partner DB access on a non-standard Postgres port
(55432) that just hasn't been formally approved as a Shepherd policy yet — a
policy-approval ask, not a "close an accidental hole" fix.

**Recommended action:** expand SECO-3667's scope (or re-title it, e.g.
"{qa,prod}_dish_db_replica + dish_db_dwh cleanup") to include these 8 rules,
rather than opening a separate ticket — same partner, same port pattern, same
likely resolution path (formal policy approval for 55432 from the two dish
partner /24s).

---

## Summary for filing

| Group | Rules | Instances | Action |
|---|---|---|---|
| trs_monitoring | 10 | 3 | New sub-task under SECO-3669 |
| tucows_billing / _prod | 6 | 1 | New sub-task under SECO-3669 |
| dish_db_dwh variants | 8 | 8 | Expand SECO-3667 scope (no new ticket) |

All three groups share the same open blocker: **tenant ownership isn't confirmed**
for `trs_monitoring` or `tucows_billing` yet — same outreach gap flagged for the
rejected SECO-3676/3677/3678 tickets. Worth deciding at tomorrow's meeting whether
outreach should be batched across all of these rather than done ticket-by-ticket.
