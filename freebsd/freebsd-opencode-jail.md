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

This host's `/etc/jail.conf` already has:

```
.include "/etc/jail.conf.d/*.conf";
```

so per-jail config goes in its own file rather than being appended to the
main `/etc/jail.conf`. Create `/etc/jail.conf.d/opencode.conf`:

```
opencode {
    host.hostname = "opencode.local";
    ip4.addr      = "em0|198.18.51.27/24";
    path          = "/jails/opencode";

    exec.prepare = "
        mkdir -p /jails/opencode/compat/linux/dev/fd;
        mkdir -p /jails/opencode/compat/linux/dev/shm;
        mkdir -p /jails/opencode/compat/linux/proc;
        mkdir -p /jails/opencode/compat/linux/sys;
    ";
    exec.start  = "/bin/sh /etc/rc";
    exec.stop   = "/bin/sh /etc/rc.shutdown";

    mount.devfs;
    mount.fstab = "/etc/jail.conf.d/opencode.fstab";
    linux = "new";
}
```

`mount.fstab` is what actually mounts `linprocfs`/`linsysfs` — the two Linux
`/proc`/`/sys` equivalents that Bun (and any Linux binary run through the
Linuxulator) expects to exist. Create the matching fstab file it points to,
`/etc/jail.conf.d/opencode.fstab`:

```
devfs       /jails/opencode/compat/linux/dev      devfs       rw,late                    0 0
linprocfs   /jails/opencode/compat/linux/proc     linprocfs   rw,late                    0 0
linsysfs    /jails/opencode/compat/linux/sys      linsysfs    rw,late                    0 0
fdescfs     /jails/opencode/compat/linux/dev/fd   fdescfs     rw,linrdlnk,late           0 0
tmpfs       /jails/opencode/compat/linux/dev/shm  tmpfs       rw,late,mode=1777,size=1g  0 0
```

Notes on the jail.conf settings:

- `ip4.addr = "em0|198.18.51.27/24"` locks the jail to that one address. A
  process inside the jail binding to `0.0.0.0` will only actually be
  reachable on `198.18.51.27`, never on the host's other addresses.
- `linux = "new"` gives the jail its own private Linux emulation
  environment/branding rather than sharing the host's, keeping the Linux
  userland fully contained inside the jail's own filesystem.
- `mount.fstab` (like `mount.devfs`) is performed by the host's `jail(8)`
  framework at jail start/stop, not by anything running inside the jail —
  so no `allow.mount.*` permission bits are needed for it. Those bits only
  matter if a process *inside* the jail needs to call `mount(2)` itself,
  which isn't the case here.
- **`fdescfs` must use the `linrdlnk` option.** Without it, `readlink()` on
  `/dev/fd/N` returns `EINVAL` inside the jail, and Bun-based tools —
  opencode included — hang silently at startup with no output or error,
  because their working-directory resolution deadlocks on that failed
  `readlink`. Nothing about the failure looks like a mount problem, so
  this is worth getting right up front rather than debugging later.
- `exec.prepare` creates the mount-point directories before `mount.fstab`
  tries to mount onto them; the mounts fail if the target directories
  don't already exist.

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
```

> **This host already has other jails in `jail_list`.** Do NOT run
> `sysrc jail_list="opencode"` — the `=` form *overwrites* the whole
> variable and would drop every jail name already in there, so those
> jails would silently stop autostarting on the next reboot. Check what's
> there first, then append:
>
> ```
> sysrc jail_list          # see the current value before changing anything
> sysrc jail_list+="opencode"
> ```
>
> `sysrc`'s `+=` form appends to the existing space-separated list instead
> of replacing it.

`jail_enable="YES"` turns on the jail subsystem at boot. `jail_list` isn't
strictly required with the `jail.conf` format — if omitted, FreeBSD defaults
to starting every jail defined across `/etc/jail.conf` and everything it
`.include`s from `/etc/jail.conf.d/*.conf` — but since this host already
uses `jail_list` explicitly (rather than relying on the default), `opencode`
needs to be added to that existing list rather than left out, or it won't
autostart at all.

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

Install all of this as root, once, inside the jail:

```
jexec opencode pkg install -y \
    git \
    curl \
    jq \
    opentofu \
    ansible \
    python311 \
    py311-pip \
    rsync \
    bash \
    ripgrep \
    tmux \
    gmake \
    pkgconf \
    ca_root_nss
```

A few notes on why each package is there:

- `python311` / `py311-pip` — Ansible's own runtime dependency, and useful
  generally for scripting/collections that need extra Python libs.
- `bash` — many Ansible tasks and ops scripts assume bash even though the
  jail's default shell is `/bin/sh`; it's also set as the `opencode` user's
  own login shell in step 6.
- `ripgrep` — commonly used by terminal coding agents for fast in-repo
  search.
- `tmux` — handy for keeping long-running provisioning jobs alive across
  an SSH/PuTTY session.
- `gmake` / `pkgconf` — basic build tooling, in case anything needs to
  compile a small helper.

Run this after step 4 (installing `linux-rl9`) and **before** creating the
`opencode` user in step 6, since that step sets the user's login shell to
the `bash` package installed here — the shell binary needs to already exist
before `pw useradd` points a user at it.

## 6. Create the opencode user

The jail's own users/groups are ordinary FreeBSD ones (the `linux-rl9` tree
is only the Linux ABI support layer, not a separate OS). Use `bash` (from
step 5, installed as a native FreeBSD package at `/usr/local/bin/bash`) as
the login shell rather than the default `/bin/sh`:

```
jexec opencode pw groupadd opencode
jexec opencode pw useradd opencode -m -d /home/opencode -s /usr/local/bin/bash \
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

Add Bun's bin directory to the user's shell profile. Since the login shell
is now bash, a login shell (which is what an SSH session gives you) reads
`~/.bash_profile` first, falling back to `~/.profile` if that doesn't
exist — either works, so `/home/opencode/.profile` is fine to keep using:

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

Create a small script that starts opencode in web mode bound to `127.0.0.1`
inside the jail — never on the jail's real address — so it's only ever
reachable through an SSH tunnel. From the jail host, write it straight into
the jail's filesystem with a heredoc:

```
cat > /jails/opencode/home/opencode/opencode-web <<'EOF'
#!/bin/sh
#
# opencode-web - start opencode in web mode, bound to loopback only.
#
# Run this INSIDE the jail, logged in as the 'opencode' user. It listens
# on 127.0.0.1 so it's only reachable through an SSH tunnel, never
# directly on the jail's network address (198.18.51.27).
#
# --- PuTTY setup (do this once, on your workstation) ---
#   Session -> Host Name: 198.18.51.27   Port: 22
#   Connection -> SSH -> Auth -> Credentials: your private key
#       (or leave blank to use the 'opencode' user's password)
#   Connection -> SSH -> Tunnels:
#       Source port: 9090   Destination: 127.0.0.1:9090   Type: Local
#       -> click "Add"
#   Session -> Saved Sessions: give it a name (e.g. "opencode-jail") -> Save
#
# --- Each time you want to use it ---
#   1. Open PuTTY, load the saved session, connect, log in as 'opencode'.
#   2. Run this script inside that session:  ./opencode-web
#   3. On your workstation, open a browser to: http://localhost:9090
#
# If you use a different port than 9090, make sure the PuTTY tunnel's
# source/destination ports match what you pass as an argument below.
#
# Usage:
#   ./opencode-web           # listen on default port 9090
#   ./opencode-web 9191      # listen on a different port (update PuTTY tunnel too)

set -eu

PORT="${1:-9090}"

export PATH="$HOME/.bun/bin:$PATH"

exec opencode web --port "$PORT" --hostname 127.0.0.1
EOF
chmod +x /jails/opencode/home/opencode/opencode-web
chown opencode:opencode /jails/opencode/home/opencode/opencode-web
```

The script's header comments include the PuTTY tunnel configuration needed
to reach the resulting web UI from a local browser. In short: a saved PuTTY
session pointed at `198.18.51.27:22`, with an SSH local tunnel
(source `9090` → destination `127.0.0.1:9090`) configured under
Connection → SSH → Tunnels.

## 10. Day-to-day usage

**CLI / TUI mode**, from the jail host:

```
jexec -U opencode opencode /usr/local/bin/bash
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
- Missing `linrdlnk` on the `fdescfs` mount (see step 3) causes opencode to
  hang silently at startup rather than erroring — if that happens, check
  the fstab mount options before anything else.
- **Don't `nullfs`-mount a single file** (e.g. a config or credentials file
  like `auth.json`) into the jail. An atomic-replace `rename(2)` over a
  single-file `nullfs` target can wedge the host kernel in `_vn_lock`,
  and even `SIGKILL` won't free the stuck process — a full reboot is the
  only way out. If you want host/jail state shared (e.g. opencode's
  `~/.local/share/opencode` directory), `nullfs`-mount the containing
  *directory*, not the individual file. This has nothing to do with
  Linuxulator specifically — it applies to `nullfs` in general — but it's
  an easy trap to hit once you start sharing config between the host and
  this jail.
