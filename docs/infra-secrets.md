# SecOps Infra — Secrets Management

## Overview

The secrets surface for deploying and maintaining SecOps base infrastructure is intentionally small. Most configuration data used in VM provisioning and application deployment does not require secret storage. This document covers the two areas that do: OpenStack credentials and the short list of secrets required by Ansible during VM bootstrapping.

---

## What Is (and Isn't) a Secret

The majority of data items used in Terraform and Ansible — hostnames, IP addresses, tenant names, package lists, service configuration — are not sensitive and do not need to be treated as secrets. They can be stored plainly in the Git repository alongside the playbooks and runbooks.

The following categories **do** require secret handling:

- OpenStack credentials (used by Terraform to manage infrastructure)
- A small set of bootstrap secrets consumed by Ansible when populating new VMs

---

## OpenStack Secrets

Terraform requires credentials to authenticate against OpenStack and manage tenant resources. These are provided via environment variables and must not be committed to the repository.

---

## Ansible Bootstrap Secrets

When a new VM is provisioned, Ansible requires a small number of secrets to complete the initial configuration. These are passed at bootstrap time and include items such as:

- Any credentials needed to pull from internal package or configuration sources during the initial run

These secrets should be stored in 1Password and fetched via the CLI at runtime. They are not embedded in Terraform or Ansible playbooks directly.

---

## Handling and Storage

Infrastructure provisioning and maintenance of SecOps VMs is infrequent and does not benefit from GitHub Actions or a CI/CD pipeline. These operations are performed using shell scripts run from the operator's workstation or a maintenance host. The security boundary for these operations is the access privileges of the operator and the host from which they are running.

### 1Password CLI

Secrets are stored in the company 1Password vaults and accessed at runtime using the [1Password CLI](https://developer.1password.com/docs/cli/) (`op`). When an operator runs a provisioning command, the CLI fetches the required secret from the vault. If the operator is not currently authenticated to 1Password, the tool will prompt them to authenticate using the standard 1Password mechanisms before proceeding.

This approach provides:

- A clear audit trail for every secret access, tied to the authenticated operator
- No need to store secrets locally or pass them around out-of-band
- A consistent retrieval mechanism that works within the existing workstation-based workflow
- A change history for each secret, including who made each change and when — 1Password retains previous versions, allowing a secret to be reverted to a prior value if needed

### Vault

All SecOps infra secrets are stored in the **`secops-infra`** vault.

### Secret Formats

Secrets may use any appropriate 1Password item type. Common formats include:

- **Note** — a simple text block, suitable for freeform credentials or configuration snippets
- **API Credential** — a JSON blob containing relevant fields such as user, id, key, token, and url

The CLI returns secrets as JSON objects, making them straightforward to decode and pass into the shell scripts that wrap the Terraform and Ansible processes.

### Naming Convention

Secret names follow a consistent format to avoid ambiguity as the number of secrets grows:

```
<datacenter>-<tenant|env>-<secret-name>
```

Where a secret applies across all datacenters, tenants, or environments, the respective component(s) should be set to `all`. For example:

| Secret name | Meaning |
|---|---|
| `yyz-prod-tcxsec-openstack` | OpenStack credentials for the prod-tcxsec tenant in the YYZ datacenter |
| `all-all-ansible-bootstrap-token` | Ansible bootstrap token used across all datacenters and environments |
| `yyz-all-package-repo-token` | Package repo token for all environments in YYZ |

### General Rules

- Secrets are never committed to the Git repository.
- Secrets are stored in 1Password and fetched via the CLI at runtime.
- Access to perform infrastructure operations is inherently constrained by what the operator's account and workstation are permitted to do — there is no separate service account or pipeline credential to manage.
- If a secret is believed to have been exposed, it should be rotated immediately and the relevant tenant owner notified.

---

## Evaluated and Rejected

**GitHub Secrets** was considered as a storage mechanism but was ruled out. It is too narrowly scoped — designed primarily for injecting secrets into CI/CD pipeline runs — and does not provide the access controls, audit capabilities, or operational flexibility expected of a proper secrets management solution. It is not a substitute for a secrets manager.

**OpenBao/Vault** was considered but is overly complex relative to the needs of SecOps infra. The operational overhead of deploying, maintaining, and securing a Vault cluster is not justified by a secrets surface this small. If the scope grows significantly, it remains a viable option to revisit.

---

## Future Considerations

The current approach is intentionally lightweight and suited to the narrow secrets surface of SecOps base infra. If that changes — for example, if the number of secrets grows significantly, secrets need to be shared across a broader set of services or users, or more granular access controls and rotation policies become necessary — the 1Password CLI approach may no longer be sufficient. In that case, a dedicated secrets manager such as OpenBao/Vault should be reconsidered.

### Vault Backup

As a backup measure, the `secops-infra` 1Password vault should be periodically dumped, encrypted, and pushed to OpenStack Ceph S3 or similar for off-platform storage. This provides a recovery path in the event that access to 1Password is lost or the vault is otherwise unavailable.

The encryption keys used to protect the vault dump must be stored somewhere other than 1Password itself — keeping them there would create a circular dependency that defeats the purpose of the backup. A suitable alternative location should be agreed upon by the team prior to implementing this process.
