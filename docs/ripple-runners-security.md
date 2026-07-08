# Ripple Runners — Security Notes

## How the runners work

Wavelo has a standing pool of ripple runner instances which register themselves with GitHub
as available for wavelo GitHub Actions. When a workflow job needs a runner, GitHub selects
one from those registered, matching on labels so the right pool gets the right job.

When a job finishes, the runner instance deregisters from GitHub and exits. Nomad
continuously reconciles the pool back to its desired count, so it starts a replacement
container which registers itself as available for the next job.

Each replacement is a fresh container from the same Docker image, with a clean filesystem.
The runner workdir lives inside the container, and `/var/lib/docker` is a tmpfs mount, so
there is no filesystem residue from prior jobs. A post-job cleanup hook also scrubs the
workdir as an additional safeguard.

## Can one action pollute a subsequent action?

Local disk isolation is solid — a subsequent job on the same pool gets a genuinely clean
environment and cannot see anything written by a prior job.

The realistic pollution vectors are all **external** to the runner:

- **GitHub-managed state** — caches (`actions/cache`), secrets, and package registry
  artifacts persist across jobs by design.
- **Shared infrastructure** — any external system a job writes to (databases, internal
  registries, Vault, Consul) without cleaning up is visible to subsequent jobs.

## What to watch for in action code

The runner containers run with `privileged = true` (required for Docker-in-Docker). This
makes the following worth auditing in any workflow:

**Host filesystem writes.** Any `docker run` command with `-v` flags pointing to absolute
host paths (e.g. `/tmp`, `/etc`, `/var/lib/nomad`) could read or write the Nomad node's
filesystem directly and persist beyond the container's lifecycle.

**Docker socket exposure.** Steps that mount or reference `/var/run/docker.sock` interact
with the host Docker daemon rather than the inner DinD instance, potentially affecting
other containers on the same node.

**Privileged container escape techniques.** A privileged container can in principle
manipulate kernel namespaces or mount the host root filesystem. Look for steps using
`nsenter`, `mount`, `chroot`, or direct `/proc`/`/sys` manipulation.

**Shared tmpfs paths.** The `/var/lib/docker` tmpfs is scoped per container, but explicit
mounts of other host-level tmpfs paths could leak between jobs.

**In practice**, the highest-leverage audit targets are:

- Workflow steps that run raw `docker` commands (rather than standard GitHub Actions)
- Steps that use `sudo` or reference absolute paths outside the workdir
- Jobs that write to shared internal infrastructure without teardown
