# SecOps Infrastructure Plan

## Overview

This document describes the plan for establishing infrastructure to support SecOps applications and data. Currently, services are running across multiple locations without a consistent organizational structure, and the split between **TCX** and **Wavelo** — both budgetary and organizational — has not been consistently reflected in how infrastructure was provisioned. Existing legacy infrastructure is largely ad-hoc. Going forward, the goal is to establish a consistent, well-defined pattern and keep all new work within it.

---

## OpenStack Tenants

### Environments

Four environments will be maintained, each serving a distinct purpose:

| Environment | Purpose |
|-------------|---------|
| **lab** | Individual use, experimentation, and personal development. Not backed up — data is subject to loss at any time. |
| **dev** | Established projects that have evolved from lab and are intended to eventually move into production. |
| **test** | Projects that are no longer in active development and are ready to move into production. |
| **prod** | Services that must be up and running at all times. |

### Tenant Naming and Ownership

To maintain a clear separation between Wavelo and TCX, existing LDAP groups will be used to own and control tenants.

**TCX/SecOps** — managed by `openstack_teamleads_security`:

- `lab-tcxsec`
- `dev-tcxsec`
- `test-tcxsec`
- `prod-tcxsec`

**Wavelo/SecOps** — managed by `openstack_teamleads_wavelobis`:

- `lab-wavsec`
- `dev-wavsec`
- `test-wavsec`
- `prod-wavsec`

These tenant names were chosen specifically to avoid conflict with any existing SecOps infrastructure. Tenants may remain empty until resources need to be migrated into them.

### Project-Specific Tenants

Where an application or service would benefit from isolation in its own tenant, the tenant name should follow the group naming convention, for example:

- `prod-tcxsec-opencti`

---

## VM and Server Design

### Access and Security

- **dev/test/prod** tenants will be gated by a `maint-01` host, which serves as an SSH jumpbox for accessing other VMs within the tenant.
- **lab** tenants will be relatively open. However, as workloads move from lab to dev, the operating environment — including ACLs and network controls — must be tightened accordingly.

### VM Naming Convention

VM names will follow the format:

```
<purpose>-NN
```

For example: `pgsql-01`, `swarmem-02`.

### Standard Services per Tenant

Each tenant will include a baseline set of services:

- `pgsql-01` — PostgreSQL database server
- `swarmctl-01` — Docker Swarm control node
- `swarmem-0x` — Swarm worker nodes (quantity as needed)

Additional VMs (e.g., Elasticsearch) may be provisioned where containerization is not practical.

### High Availability

Where appropriate, VMs should be built as **n+1** to support rolling upgrades and minimize the need for downtime. Where needed, OpenStack load balancers can be used to round-robin traffic across n+1 servers.

---

## Server and VM Administration

SecOps VM provisioning and maintenance is infrequent and does not benefit from GitHub Actions or a CI/CD pipeline. These operations will be performed using shell scripts, run from the operator's workstation or a maintenance host, using a combination of **Terraform** and **Ansible**. All configurations will be stored in a Git repository.

### Runbooks

Runbooks will be provided to cover the following procedures:

- Provisioning a new set of VMs and populating them with a base set of utilities
- Adding an application to an existing set of VMs (e.g., PostgreSQL)
- Upgrading existing VMs (rolling upgrades where n+1 is in place)
- Adding or changing a load balancer for a tenant

---

## Server Configuration

Ansible will be used to configure and populate VMs. The needs of SecOps infra are straightforward and better suited to Ansible than the more complex Salt Stack. Ansible's agentless, playbook-driven approach aligns well with the modular component concept that SecOps infra is aiming for — individual playbooks can be developed and applied independently, mapping cleanly to the discrete services and roles that make up each tenant.

A base playbook will be provided to bring a newly provisioned VM to a standard starting point. This includes populating the VM with a common set of utilities, initializing PAM and LDAP authentication, and applying standard log trimming configuration.

Additional playbooks will be developed to layer services onto a base VM as needed — for example, adding PostgreSQL, Docker Swarm, or other components. This keeps the configuration modular and allows services to be added incrementally without re-provisioning the VM from scratch.

---

## Applications

### Containerization

Applications should be packaged and deployed as containers to the Docker Swarm cluster. Each environment will be provided with:

- A **Docker Swarm cluster** for hosting containers
- A **PostgreSQL server** as a common external data store

Where Docker is not appropriate, additional full VMs will be considered on a case-by-case basis.

### Database Access

Applications using PostgreSQL must use distinct access credentials — separate database users and schemas/namespaces per application. Documentation and guidance will be provided.

---

## Monitoring

Zabbix will be deployed in the **dev** and **prod** environments. The dev Zabbix instance will monitor both dev and test; the prod instance will monitor prod.

Monitoring will primarily focus on availability and resource shortages — ensuring services are up and that VMs are not running low on CPU, memory, or disk.

---

## Migration and Cleanup

Existing services should be ported to containers or otherwise migrated to the new infrastructure. As each service is migrated, the old resources and tenants should be decommissioned and freed.
