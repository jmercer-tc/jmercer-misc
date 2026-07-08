# SecOps API Usage

Audit of all outbound API calls across the secops-tools repos (`secops-tools`, `secops-tools-salt`, `secops_tools_terraform`). Credentials are stored in Vault and injected at runtime via Salt pillars or environment variables.

---

## 1. FreshService

**Script:** `secops-tools/csreport/src/secops/csreport/freshdesk.py`  
**Auth:** HTTP Basic (`FRESHSERVICE_API_KEY` + `'X'`)  
**Vault:** `secret/wwwint/reporting` → `freshservice_api_key`, `freshservice_domain`  
**Base URL:** `https://{freshservice_domain}.freshservice.com/api/v2`

| Endpoint | Purpose |
|---|---|
| `GET /assets?page=N&include=type_fields` | Pull full asset inventory (paginated) |
| `GET /asset_types` | Resolve asset type IDs to names |
| `GET /requesters/{user_id}` | Look up assigned user email by ID |

> **Known issue:** The API key currently in use returns 403 on `/requesters/{user_id}`. The key has permission to read assets but not requester profiles. Fix: either update the key to one with "View Requesters" permission, or create a dedicated service account with a scoped custom role. See also Option 2 in the code: fall back to `/agents/{user_id}` in case the user is an agent rather than a requester.

---

## 2. CrowdStrike — Asset Sync

**Script:** `secops-tools/csreport/src/secops/csreport/csreport.py`  
**Auth:** OAuth2 client credentials (via FalconPy SDK)  
**Vault:** `secret/wwwint/reporting` → `falcon_client_id`, `falcon_client_secret`  
**Base URL:** `https://api.crowdstrike.com`

| Endpoint | Purpose |
|---|---|
| `POST /oauth2/token` | Obtain access token |
| `GET /devices/queries/devices-scroll/v1` | Paginated list of all device IDs (up to 5000/page) |
| `GET /devices/entities/devices/v2` | Full device details in batches of 100 |

---

## 3. CrowdStrike — Sensor Package Downloader

**Script:** `secops-tools/falconloader/src/secops/falconloader/bin/pull_pkg.py`  
**Auth:** OAuth2 client credentials  
**Vault:** `secret/wwwint` → `falcon_download_id`, `falcon_download_secret`  
**Base URL:** `https://api.crowdstrike.com`

> Note: separate credentials from the asset sync above — intentional or worth consolidating?

| Endpoint | Purpose |
|---|---|
| `POST /oauth2/token` | Obtain access token |
| `GET /sensors/combined/installers/v1?filter=platform:'linux'` | List available Linux sensor packages |
| `GET /sensors/entities/download-installer/v1?id={sha256}` | Download specific installer |

---

## 4. Shepherd (OpenStack)

**Script:** `secops-tools/csreport/src/secops/csreport/osreport.py`  
**Auth:** Bearer tokens (with username/password fallback)  
**Vault:** `secret/wwwint/reporting` → `shepherd_token_bra2`, `shepherd_token_cnco`  
**Base URLs:** `https://shepherd-2.bra2.tucows.cloud` and `https://shepherd-2.cnco.tucows.cloud`

| Endpoint | Purpose |
|---|---|
| `POST /jwt_token` | Obtain token from username/password (fallback only) |
| `GET /region` | List regions |
| `GET /department` | List departments |
| `GET /project/department/{uuid}` | List projects per department |
| `GET /project/{uuid}/zone` | List zones |
| `GET /project/{uuid}/subnet` | List subnets |
| `GET /project/{uuid}/instance` | List instances |
| `GET /project/{uuid}/security_group` | List security groups |
| `GET /project/{uuid}/load_balancer` | List load balancers |
| `GET /project/{uuid}/floating_ip` | List floating IPs |

---

## 5. AlienVault USM — Event Downloader

**Script:** `secops-tools-salt/state/cron/files/download_alienvault_events.py`  
**Auth:** OAuth2 client credentials → Bearer token  
**Vault:** `secret/alienvault` → `apiuser`, `apikey`  
**Base URL:** `https://tucows-com-co1.alienvault.cloud/api/2.0`

> Note: the Access Audit Tool (below) also connects to AlienVault with a separate credential set (`secret/wwwint/audittool` → `AV_Username`/`AV_Password`). Worth confirming these are intentionally different accounts.

| Endpoint | Purpose |
|---|---|
| `POST /oauth/token?grant_type=client_credentials` | Obtain Bearer token |
| `GET /alarms` | Retrieve alarms |
| `GET /events?timestamp_gte=...&size=...&page=...` | Paginated event retrieval |

---

## 6. Access Audit Tool

**Config:** `secops-tools-salt/state/wwwint/files/audittool-config.yaml`  
**Vault:** `secret/wwwint/audittool`  
All credentials injected via Salt pillar (`AuditTool:*` keys).

| Service | Auth | Vault key(s) | URL |
|---|---|---|---|
| Active Directory | LDAP bind | `AD_Username`, `AD_Password` | `ldaps://brasrvdc05.int.tucows.com:636` |
| AlienVault | Username/password | `AV_Username`, `AV_Password` | `tucows-com-co1.alienvault.cloud/api/2.0` |
| AWS | App ID + private key | `AWS_App_Id`, `AWS_Private_Key` | GitHub repo (`AWS_Repo_Owner`/`AWS_Repo_Name`) |
| CrowdStrike | OAuth2 | `Crowdstrike_Client_Id`, `Crowdstrike_Client_Secret` | `https://api.crowdstrike.com` |
| GitHub | GitHub App (JWT) | `Github_AppId`, `Github_Private_Key` | `https://api.github.com` |
| GSuite/GCP | Service account JSON | `GCP_Password` (delegated: `GCP_Delegated_User`) | Google APIs |
| HiBob (HRIS) | Basic auth | `HiBoB_Username`, `HiBoB_Password` | `https://api.hibob.com/v1` |
| Hover | Password | `HoverAdmins_Password` | (internal) |
| LDAP (cloud) | Anonymous read | — | `ldaps://ldap-primary.tucows.cloud` |

GitHub orgs monitored: `tucowsinc`, `TucowsTCX`, `tinginc`, `tinginternet`, `tingmobile`, `tucowsdomains`, `tucowsdomainsretail`, `tucowsdomainswholesale`, `tucowstcx-test-exampleou`, `tucowstcx-test-org`, `waveloinc`

> Note: CrowdStrike appears here with a third distinct credential pair, separate from the asset sync and sensor downloader. Worth auditing whether these three sets of CrowdStrike creds are intentional.

---

## 7. GitHub — Repository Monitor (repomon)

**Script:** `secops-tools/repomon/src/secops/gitrepomon/bin/update_repolist.pl`  
**Auth:** Bearer token  
**Vault:** `secret/wwwint` → `gitrepomon_token`; read from `gitrepomon.ini`  
**Base URL:** `https://api.github.com`

| Endpoint | Purpose |
|---|---|
| `GET /orgs/{org}/members` | List org members |
| `GET {user.repos_url}` | List repos per user |
| `GET /repos/{user}/{repo}` | Repo details |
| `GET /repos/{user}/{repo}/commits` | Recent commits |

---

## 8. Zabbix JSON-RPC

**Script:** `secops-tools-salt/state/zabbix/files/scripts/zabbixUsers.py`  
**Auth:** Username/password → session token  
**Vault:** `secret/zabbix` → `admin` (password); username hardcoded as `Admin`  
**Base URL:** `https://{zabbixServer}/api_jsonrpc.php`

| Method | Purpose |
|---|---|
| `user.login` | Authenticate and get session token |
| `user.get` | List all users |
| `user.create` | Create user accounts |

> Note: SSL verification is disabled in this script.

---

## 9. OPA (Open Policy Agent) — Internal Only

**Scripts:** `csreport/opaloader.py`, `website/api/class.OSReport.php`  
**Auth:** None (localhost)  
**Base URL:** `http://localhost:8181`

| Endpoint | Direction | Purpose |
|---|---|---|
| `PUT /v1/policies/{name}` | Write | Push `.rego` policy files (opaloader watches `/var/lib/opa`) |
| `DELETE /v1/policies/{name}` | Write | Remove stale policies |
| `POST /v1/data/policy/{name}/allow` | Read | Evaluate policy decisions (called from PHP) |

---

## Vault Secret Map

| Vault Path | Keys | Used By |
|---|---|---|
| `secret/wwwint/reporting` | `freshservice_api_key`, `freshservice_domain`, `falcon_client_id`, `falcon_client_secret`, `shepherd_token_bra2`, `shepherd_token_cnco` | freshdesk.py, csreport.py, osreport.py |
| `secret/wwwint` | `falcon_download_id`, `falcon_download_secret`, `gitrepomon_token`, `gitrepomon_email`, `pkgrepo_signing_key`, `pkgrepo_signing_key.pub` | falconloader, repomon |
| `secret/wwwint/audittool` | `AD_Username/Password`, `AV_Username/Password`, `AWS_App_Id/Private_Key/Repo_*`, `Crowdstrike_Client_Id/Secret`, `GCP_Delegated_User/Password`, `Github_AppId/Private_Key`, `HiBoB_Username/Password`, `HoverAdmins_Password` | audittool |
| `secret/alienvault` | `apiuser`, `apikey` | download_alienvault_events.py |
| `secret/zabbix` | `admin` | zabbixUsers.py |
| `secret/s3_siem` | `access_key`, `secret_key` | S3 SIEM mount |
| `secret/docker` | `authelia_session`, `authelia_storage`, `authelia_jwt`, `graylog_pw_secret`, `graylog_root_pw` | docker services |
| `secret/oidc-broker` | `appcred-service-dev`, `shepherd_token` | OIDC broker |
| `secret/saltstack` | `id_secops-packages`, `id_secops-packages.pub`, `id_secops-audit-tool`, `id_secops-audit-tool.pub` | Salt SSH keys |
