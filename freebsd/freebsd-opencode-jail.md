# Running opencode in a FreeBSD jail (via Linuxulator)

This documents the full process for running [opencode](https://opencode.ai) — a
terminal AI coding agent built on Bun — inside a dedicated FreeBSD jail. Bun has
no reliable native FreeBSD support, so the jail runs a Linux userland
(`linux-rl9`) under FreeBSD's Linuxulator compatibility layer, and opencode is
installed and executed inside that environment. The jail gets its own IP,
runs opencode as an unprivileged user, and both CLI and web-mode access are
gated behind SSH — no unauthenticated network listener at any point.

## Environment used in this guide

- Jail host interface: `em0`, host IP `198.18.51.25/24`
- Jail IP (alias on `em0`): `198.18.51.27/24`
- Jail name: `opencode`
- Jail path: `/jails/opencode`
- In-jail service/login user: `opencode`
- opencode web UI port: `9090` (bound to loopback only inside the jail)

Adjust interface name, IPs, and paths to match your actual host.

## 1. Host network prep

Add a persistent IP alias for the jail on the host's interface, in
`/etc/rc.conf`:

```
ifconfig_em0_alias0="inet 198.18.51.27/24"
```

Apply immediately without a reboot:

```
ifconfig em0 alias 198.18.51.27/24
```

## 2. Enable Linuxulator on the host

```
sysrc linux_enable=YES
service linux start
```

## 3. Create the jail

`/etc/jail.conf`:

```
opencode {
    host.hostname = "opencode.local";
    ip4.addr      = "em0|198.18.51.27/24";
    path          = "/jails/opencode";

    exec.start  = "/bin/sh /etc/rc";
    exec.stop   = "/bin/sh /etc/rc.shutdown";

    mount.devfs;
    allow.mount;
    allow.mount.devfs;
    allow.mount.procfs;
    allow.mount.linprocfs;
    allow.mount.linsysfs;
    linux = "new";
}
```

Notes on the jail.conf settings:

- `ip4.addr = "em0|198.18.51.27/24"` locks the jail to that one address. A
  process inside the jail binding to `0.0.0.0` will only actually be
  reachable on `198.18.51.27`, never on the host's other addresses.
- `linux = "new"` gives the jail its own private Linux emulation
  environment/branding rather than sharing the host's, keeping the Linux
  userland fully contained inside the jail's own filesystem.
- The `allow.mount.*` lines are required so `linprocfs`/`linsysfs` (Linux's
  `/proc` and `/sys` equivalents) can be mounted inside the jail — Bun/Node
  style runtimes expect these to exist.

Create the jail root filesystem and start the jail:

```
mkdir -p /jails/opencode
bsdinstall jail /jails/opencode      # installs a base FreeBSD userland
service jail start opencode
```

### Start the jail automatically on reboot

By default `service jail start` only starts it for the current boot. To have
it come up automatically after a reboot, add to `/etc/rc.conf`:

```
sysrc jail_enable="YES"
sysrc jail_list="opencode"
```

`jail_enable="YES"` turns on the jail subsystem at boot. `jail_list` isn't
strictly required with the `jail.conf` format — if omitted, FreeBSD defaults
to starting every jail defined in `/etc/jail.conf` — but setting it
explicitly to `opencode` is worth doing anyway: it means if you ever define
other jails in the same `jail.conf` later, they won't autostart unless you
deliberately add them to the list too.

No changes are needed for Linuxulator itself — `linux_enable="YES"` (from
step 2) already persists in `/etc/rc.conf`, and FreeBSD's boot ordering
starts the `linux` compat service before the jail service on its own.

## 4. Install the Linux userland inside the jail

```
jexec opencode pkg install linux-rl9
```

This installs a RockyLinux 9 userland under `/compat/linux` inside the jail,
which the Linuxulator uses to satisfy Linux binaries' runtime dependencies
(shared libs, `/proc`, `/sys`, etc.) via FreeBSD's ELF interpreter path
fallback.

> If you hit `SIGILL` (illegal instruction) crashes when running Bun on some
> hardware — a known rough edge with Bun-on-FreeBSD as of this writing — try
> `linux-c7` (CentOS 7 base) instead of `linux-rl9`.

## 5. Pre-populate the toolchain opencode will actually use

opencode's own agent runtime is self-contained, but every real *action* it
takes — running `git`, invoking IaC tooling, hitting an API, configuring a
VM — goes through its bash tool, which just shells out to whatever binaries
already exist on `PATH`. opencode does not bundle these and will not
install them for you on demand in any structured way; if a command is
missing, the shell call simply fails with "command not found," and the
agent's ability to fix that itself is unreliable at best and undesirable at
worst (an agent reaching for `pkg`/root to self-heal is not something to
lean on in a jail you've deliberately locked down). So pre-populate rather
than discover gaps mid-session.

This matters for jail architecture too: only the `opencode`/`bun` binary
itself needs the Linux ABI layer (`/compat/linux`, from `linux-rl9`) to run.
Any child process opencode spawns — `git`, `tofu`, `ansible`, `curl`,
`jq`, etc. — resolves through the calling user's normal FreeBSD `PATH`,
not through `/compat/linux`. So this tooling gets installed as ordinary
FreeBSD packages at the jail level, same as anything else in a FreeBSD
jail.

Given the intended use here — provisioning Proxmox VMs and configuring
FreeBSD/Ubuntu guests on them — the toolchain is:

- **OpenTofu** for IaC/provisioning against the Proxmox API (MPL-licensed,
  native FreeBSD package; drop-in HCL/provider compatible with Terraform,
  e.g. the `bpg/proxmox` or `telmate/proxmox` providers)
- **Ansible** for configuring the VMs once they exist (agentless over SSH,
  works against both FreeBSD and Ubuntu targets)
- **curl + jq** for any direct Proxmox REST API calls outside of OpenTofu

`freebsd/bootstrap-jail-packages.sh` (in this repo) installs all of this as
root, once, inside the jail:

```
jexec opencode sh /path/to/bootstrap-jail-packages.sh
```

It installs: `git curl jq opentofu ansible python311 py311-pip rsync bash
ripgrep tmux gmake pkgconf ca_root_nss`. A few notes on why each is there:

- `python311` / `py311-pip` — Ansible's own runtime dependency, and useful
  generally for scripting/collections that need extra Python libs.
- `bash` — many Ansible tasks and ops scripts assume bash even though the
  jail's default shell is `/bin/sh`.
- `ripgrep` — commonly used by terminal coding agents for fast in-repo
  search.
- `tmux` — handy for keeping long-running provisioning jobs alive across
  an SSH/PuTTY session.
- `gmake` / `pkgconf` — basic build tooling, in case anything needs to
  compile a small helper.

Run this after step 4 (installing `linux-rl9`) and before or after creating
the `opencode` user — order doesn't matter since these are jail-wide
packages, not user-specific installs.

## 6. Create the opencode user

The jail's own users/groups are ordinary FreeBSD ones (the `linux-rl9` tree
is only the Linux ABI support layer, not a separate OS):

```
jexec opencode pw groupadd opencode
jexec opencode pw useradd opencode -m -d /home/opencode -s /bin/sh \
    -c "opencode service/cli user"
jexec opencode passwd opencode
```

## 7. Install Bun + opencode as that user

Run the installers as the `opencode` user (not root) so everything lands
under `/home/opencode`:

```
jexec -U opencode opencode /compat/linux/bin/bash -c \
    "curl -fsSL https://bun.sh/install | bash"
jexec -U opencode opencode /compat/linux/bin/bash -c \
    "curl -fsSL https://opencode.ai/install | bash"
```

Add Bun's bin directory to the user's shell profile
(`/home/opencode/.profile` for `/bin/sh`):

```
export PATH="$HOME/.bun/bin:$PATH"
```

## 8. Enable SSH access to the jail

```
jexec opencode sysrc sshd_enable=YES
jexec opencode service sshd start
```

Set up key-based auth for the `opencode` user:

```
jexec -U opencode opencode mkdir -p /home/opencode/.ssh
# copy your public key into /home/opencode/.ssh/authorized_keys
# chmod 700 ~/.ssh, chmod 600 ~/.ssh/authorized_keys
```

If you're filtering with `pf`/`ipfw`, make sure port 22 to `198.18.51.27`
is allowed. Port 9090 (the opencode web port) should **not** need to be
opened on the firewall at all, since it's only ever bound to loopback
inside the jail (see below) and reached through the SSH tunnel.

## 9. The opencode-web script

`freebsd/opencode-web` (in this repo) starts opencode in web mode bound to
`127.0.0.1` inside the jail — never on the jail's real address. Copy it into
`/home/opencode/` inside the jail (e.g. via `scp`/`pscp`, or paste it in with
an editor over an SSH session), make it executable, and run it after logging
in as `opencode`.

The script's header comments include the PuTTY tunnel configuration needed
to reach the resulting web UI from a local browser. In short: a saved PuTTY
session pointed at `198.18.51.27:22`, with an SSH local tunnel
(source `9090` → destination `127.0.0.1:9090`) configured under
Connection → SSH → Tunnels.

## 10. Day-to-day usage

**CLI / TUI mode**, from the jail host:

```
jexec -U opencode opencode /bin/sh
opencode
```

**CLI / TUI mode or web mode**, remotely via PuTTY:

1. Open PuTTY, load the saved session for the jail, connect, log in as
   `opencode`.
2. For CLI mode: just run `opencode`.
3. For web mode: run `./opencode-web` (optionally `./opencode-web <port>`
   for a non-default port, matching the PuTTY tunnel's destination port),
   then browse to `http://localhost:9090` on your workstation.

Because opencode's web listener never leaves loopback inside the jail, and
the jail itself is only reachable via SSH, both CLI and web access are
gated by the same SSH authentication — there's no separate unauthenticated
surface exposed on the network.

## Known rough edges

- Bun has no official native FreeBSD support; this whole setup depends on
  the Linuxulator + a Linux userland (`linux-rl9`/`linux-c7`) rather than a
  true native build.
- The FreeBSD `lang/bun` port exists but is still experimental, with
  reports of `SIGILL` crashes on some hardware — hence installing Bun
  inside the Linux userland via its own install script instead of trying
  the native port.
- Upstream opencode has hardcoded platform checks that only allow
  `linux`/`darwin`/`win32`, tracked in the project's GitHub issues for
  native FreeBSD support (not yet merged as of this writing).
