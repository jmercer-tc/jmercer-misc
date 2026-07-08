# OpenStack Security Group Bypass via Allowed Address Pairs

---

## 1. Flaw Description

OpenStack provides a networking feature called **Allowed Address Pairs**, which is intended to permit a VM's port to send and receive traffic from additional IP or MAC addresses beyond its own assigned address. Legitimate use cases include virtual IP (VIP) failover, load balancers, and other high-availability configurations.

**The bypass:** When `0.0.0.0/0` is added as an allowed address pair on a VM's port, the underlying network enforcement layer (Open vSwitch, iptables, or OVN, depending on deployment) is instructed to permit all IP traffic originating from that port. This causes security group rules — which are normally evaluated at the port level — to be effectively circumvented. Any inbound or outbound restrictions defined in the instance's security groups no longer apply.

**In plain terms:** A user with the ability to modify a VM's port (including the VM owner, depending on RBAC configuration) can grant themselves unrestricted network access by adding a single address pair entry, regardless of what security group rules are in place.

**Risk summary:**

| Factor | Detail |
|---|---|
| **Impact** | Full bypass of network access controls for the affected VM |
| **Who can exploit it** | Any project member with port-update privileges |
| **Privilege required** | Standard user (no admin role needed by default) |
| **Detection difficulty** | Low — visible via port inspection, but not flagged by default |

---

## 2. Identifying Affected VMs

The following approach queries all ports in the environment and surfaces any that have a non-empty allowed address pairs list. The expected state for the vast majority of VMs is an empty list — any entry, not just `0.0.0.0/0`, should be explicitly reviewed and justified.

> **Admin access required:** Name resolution for all projects and servers requires admin credentials.

### Option A — Bash + jq

Builds in-memory name lookup tables before scanning ports, so output is fully resolved without additional per-row API calls.

```bash
#!/usr/bin/env bash

# Build associative arrays: UUID -> name
declare -A SERVER_NAMES PROJECT_NAMES

echo "Building server list..." >&2
while IFS=$'\t' read -r id name; do
    SERVER_NAMES["$id"]="$name"
done < <(openstack server list --all-projects -f value -c ID -c Name)

echo "Building project list..." >&2
while IFS=$'\t' read -r id name; do
    PROJECT_NAMES["$id"]="$name"
done < <(openstack project list -f value -c ID -c Name)

echo "Scanning ports..." >&2

printf "%-30s %-40s %-40s %s\n" "Project" "VM Name" "Port ID" "Address Pairs"
printf '%s\n' "$(printf '%.0s-' {1..130})"

openstack port list -f json \
  | jq -r '
      .[]
      | select(
          .allowed_address_pairs != null
          and (.allowed_address_pairs | length > 0)
        )
      | [.project_id, .device_id, .id, (.allowed_address_pairs | map(.ip_address) | join(","))]
      | @tsv
    ' \
  | while IFS=$'\t' read -r project_id device_id port_id aaps; do
      project_name="${PROJECT_NAMES[$project_id]:-unknown ($project_id)}"
      vm_name="${SERVER_NAMES[$device_id]:-unknown ($device_id)}"
      printf "%-30s %-40s %-40s %s\n" "$project_name" "$vm_name" "$port_id" "$aaps"
    done
```

### Option B — Python script (portable, no jq dependency)

```python
#!/usr/bin/env python3
import subprocess, json

def os_cmd(args):
    return json.loads(subprocess.check_output(["openstack"] + args + ["-f", "json"]))

print("Building lookup tables...", flush=True)
servers  = {s["ID"]: s["Name"] for s in os_cmd(["server", "list", "--all-projects"])}
projects = {p["ID"]: p["Name"] for p in os_cmd(["project", "list"])}
ports    = os_cmd(["port", "list"])

results = []

for port in ports:
    aaps = port.get("allowed_address_pairs") or []
    if aaps:
        device_id  = port.get("device_id", "")
        project_id = port.get("project_id", port.get("tenant_id", ""))
        results.append({
            "project":  projects.get(project_id, f"unknown ({project_id})"),
            "vm_name":  servers.get(device_id,   f"unknown ({device_id})"),
            "port_id":  port["id"],
            "aaps":     ", ".join(a["ip_address"] for a in aaps),
        })

if not results:
    print("No ports with allowed address pairs found.")
else:
    print(f"\n{'Project':<30} {'VM Name':<40} {'Port ID':<40} {'Address Pairs'}")
    print("-" * 130)
    for r in results:
        print(f"{r['project']:<30} {r['vm_name']:<40} {r['port_id']:<40} {r['aaps']}")

print(f"\nTotal ports with allowed address pairs: {len(results)}")
```

Run with: `python3 check_aap_bypass.py`

### Interpreting Results

Each row represents a port with one or more allowed address pairs configured. Since the expected state for most VMs is an empty list, every result should be reviewed. For each finding, determine whether the configuration is intentional and approved (document and exempt) or unauthorized (remove the address pair and notify the project owner). Pay particular attention to any entry of `0.0.0.0/0` or `::/0`, which represent a full security group bypass.

---

## 3. Strategy to Prevent New VMs from Using This Bypass

Prevention requires controls at two levels: **policy enforcement** (restricting who can set wildcard address pairs) and **ongoing detection** (catching it if it happens anyway).

### 3.1 Restrict Allowed Address Pairs via Neutron Policy

OpenStack Neutron's `policy.yaml` controls which roles are permitted to set allowed address pairs on ports. By default, regular users can set arbitrary values, including `0.0.0.0/0`.

**Recommended change:** Restrict the `create_port:allowed_address_pairs` and `update_port:allowed_address_pairs` policies to `admin` only, or to a dedicated trusted role.

In `/etc/neutron/policy.yaml` (location may vary by distribution):

```yaml
# Before (typical default — any project member can set address pairs)
"create_port:allowed_address_pairs": "rule:regular_user"
"update_port:allowed_address_pairs": "rule:regular_user"

# After (admin only)
"create_port:allowed_address_pairs": "rule:admin_only"
"update_port:allowed_address_pairs": "rule:admin_only"
```

After modifying, reload the Neutron API service:

```bash
systemctl restart neutron-server
```

> **Caution:** Evaluate the impact on any legitimate use of allowed address pairs in your environment (e.g., Octavia load balancers, HA pairs) before applying this change. Those services may need an exemption via a dedicated role.

### 3.2 Block Wildcard Entries Specifically (Targeted Alternative)

If a blanket admin-only restriction is too broad, a targeted approach is to implement a validation hook or an admission rule that explicitly rejects `0.0.0.0/0` and `::/0` as allowed address pair values, while still permitting specific host addresses.

This can be implemented via:
- A **Neutron API extension or middleware** (advanced)
- A **periodic enforcement script** that automatically removes wildcard entries and alerts (see Section 3.3)

### 3.3 Ongoing Monitoring

Regardless of policy changes, establish automated detection to catch any instances of this configuration going forward.

**Recommended approach:** Schedule the detection script from Section 2 to run on a regular interval (e.g., hourly or daily via cron or a CI pipeline), and alert on any results.

Example cron entry (runs daily at 06:00):

```
0 6 * * * /usr/local/bin/check_aap_bypass.py >> /var/log/openstack-aap-audit.log 2>&1
```

Alerts should be routed to the security or platform operations team for review. Each finding should be triaged to determine whether the configuration is:
- **Intentional and approved** (document and exempt)
- **Accidental or unauthorized** (remove the address pair and notify the project owner)

---

## Open Items

- [ ] Determine scope: run the detection query and document the current number of affected ports/VMs.
- [ ] Assess impact of policy change on legitimate workloads (Octavia, HA, etc.) before enforcing.
- [ ] Agree on the approved remediation path for currently affected VMs.
- [ ] Define the process for teams that have a genuine need for wildcard address pairs.
- [ ] Schedule ongoing monitoring.
