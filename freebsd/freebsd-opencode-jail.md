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
cat > /jails/opencode/home/opencode/opencode-web <<'__EOF__'
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
__EOF__
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

- **Confirmed blocker: opencode hangs permanently on any real network I/O
  under this Linuxulator setup.** This is not a jail misconfiguration —
  it's a genuine gap in FreeBSD's Linuxulator syscall translation.
  Symptom: opencode starts fine and looks normal, then hangs indefinitely
  (no error, no output) the moment it does anything involving a real
  network response. This reproduces identically on two unrelated
  operations — the auth/login token exchange, and an ordinary chat
  request — so it isn't specific to one code path. `procstat`/`dmesg` on
  the jail host show every opencode thread parked in `linux_sys_futex`
  except the event-loop thread sitting in `kqueue_scan`, plus this
  telltale `dmesg` line:

  ```
  linux: jid 3 pid 40387 (Worker): syscall preadv2 not implemented
  ```

  `sockstat` confirms the TCP connections themselves complete fine (both
  land on Cloudflare-fronted `:443` endpoints, almost certainly the Zen
  API) — the hang happens *after* the request goes out, while Bun's I/O
  layer is trying to read the response back, at the exact point it needs
  a `preadv2` call the Linuxulator doesn't implement. There's no jail-side
  fix: not `jail.conf`, not a `sysctl`, not switching between `linux-rl9`
  and `linux-c7`. **As of this writing, opencode running under
  Bun-via-Linuxulator — the whole approach this guide documents — is not
  usable for any workload that makes real outbound requests, which is
  effectively all of them.**

- **Untested next step: native `lang/bun` instead of Bun-via-Linuxulator.**
  Bun landed its own native FreeBSD x86_64/aarch64 build target upstream
  (`oven-sh/bun` PR #29676 — host clang +
  `--target=x86_64-unknown-freebsd14.3` cross-compile with WebKit
  prebuilts), closing Bun's long-standing FreeBSD tracking issue.
  FreeBSD's `lang/bun` port has picked this up and is being actively
  updated (1.3.14 as of May 2026) — a materially different situation from
  the older `lang/bun` referenced below, which was experimental and
  prone to `SIGILL` crashes. A native Bun build never goes through the
  Linuxulator at all, so the `preadv2` gap above wouldn't apply. Worth
  trying `pkg install bun` (or building `lang/bun` from ports for a newer
  version) and running opencode against that native binary instead of the
  `linux-rl9`-hosted one, **before** treating the Linuxulator route as the
  final architecture. Not yet verified against opencode specifically —
  this is the next thing to test, not a confirmed fix.

- Bun has no *official* native FreeBSD support as of the last stable
  release channel; this guide's setup depends on the Linuxulator + a
  Linux userland (`linux-rl9`/`linux-c7`) rather than a true native
  build. See the native `lang/bun` note above for why that may be
  changing.
- The FreeBSD `lang/bun` port historically was experimental, with
  reports of `SIGILL` crashes on some hardware — hence installing Bun
  inside the Linux userland via its own install script instead of trying
  the native port. See above: this may no longer be the right call given
  Bun's new native FreeBSD build target.
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

- **`jexec <jail> mount` cannot be used to verify `mount.fstab`/`mount.devfs`
  worked.** By default `enforce_statfs` is `2`, which restricts what a
  jailed process can see via `statfs()` (and therefore `mount`, `df`, etc.)
  to just the single mount point containing the jail's own root —
  everything mounted underneath that (the `devfs`/`linprocfs`/`linsysfs`/
  `fdescfs`/`tmpfs` compat mounts included) is invisible from inside the
  jail, even when every one of those mounts succeeded correctly. Running
  `jexec opencode mount | grep compat` will return **empty every single
  time**, regardless of whether the mounts are actually there — it's not
  a signal of failure, it's just what `enforce_statfs=2` does by design.
  This looks exactly like a broken `mount.fstab`, and it isn't one.

  To actually check whether the compat mounts are in place, run `mount`
  on the **host**, not through `jexec`:

  ```
  mount | grep compat
  ```

  From the host you'll see (for a correctly-configured jail):

  ```
  devfs on /jails/opencode/compat/linux/dev (devfs)
  linprocfs on /jails/opencode/compat/linux/proc (linprocfs, local)
  linsysfs on /jails/opencode/compat/linux/sys (linsysfs, local)
  fdescfs on /jails/opencode/compat/linux/dev/fd (fdescfs)
  tmpfs on /jails/opencode/compat/linux/dev/shm (tmpfs, local)
  ```

  (You'll likely also see a second, separate set of `linprocfs`/`linsysfs`/
  `devfs` entries at plain `/compat/linux/...` with no `/jails/opencode`
  prefix — those belong to the *host's own* Linuxulator setup from step 2,
  not this jail, and are unrelated.)

  If a config change to `jail.conf`/the fstab file doesn't seem to be
  taking effect, restart the jail (`service jail restart <jail>`) — since
  `mount.fstab`/`mount.devfs` are only evaluated at jail create/start —
  and then re-check with the host-side `mount`, not `jexec ... mount`.

## Addendum: completely removing the jail

Full teardown, run as root on the jail host. Roughly the reverse order of
setup, with a couple of extra checks since several of this guide's own
gotchas (nullfs, wedged Bun/opencode processes, `enforce_statfs` hiding
mount state) can also get in the way of a clean removal.

### 1. Stop the jail

```
service jail stop opencode
```

This tears down the `mount.fstab`/`mount.devfs` entries (the `devfs`/
`linprocfs`/`linsysfs`/`fdescfs`/`tmpfs` compat mounts under
`/jails/opencode/compat/linux`) the same way the jail framework mounted
them at start — see the `enforce_statfs`/`mount` note above for why you
can't check this via `jexec`. Verify from the **host**:

```
mount | grep opencode
```

This should return nothing. If something is still mounted, the likely
cause is a `nullfs` mount you set up per the "Known rough edges" section
above (e.g. sharing `~/.local/share/opencode` between host and jail) —
unmount it explicitly:

```
umount /jails/opencode/<mount point>
```

If `service jail stop` hangs or a mount reports `busy`, it's very likely
the known `preadv2` hang: a wedged opencode/Bun `Worker` process sitting
in `linux_sys_futex` won't release cleanly. Check what's still running in
the jail first, rather than reaching straight for `umount -f`:

```
jexec opencode ps aux
```

Kill the hung process, then retry `service jail stop`. If it truly won't
release, unmount the compat filesystems manually, **innermost first**
(the reverse of the order they're listed in `opencode.fstab`):

```
umount /jails/opencode/compat/linux/dev/fd
umount /jails/opencode/compat/linux/dev/shm
umount /jails/opencode/compat/linux/dev
umount /jails/opencode/compat/linux/proc
umount /jails/opencode/compat/linux/sys
```

Only use `umount -f` as a genuine last resort — per the `nullfs`/
`_vn_lock` warning earlier in this doc, forcing things can wedge the host
kernel itself, at which point a reboot is the only way out. A normal
`umount` after killing the offending process should be enough here.

### 2. Remove the jail from autostart (`rc.conf`)

`jail_list` was appended to with `+=` when this jail was added, specifically
so it wouldn't clobber other jails already in the list (see step 3 of the
setup instructions above) — removal deserves the same care in reverse.
Check the current value first, don't hand-edit blindly:

```
sysrc jail_list
```

Then remove just the `opencode` entry, leaving every other jail name
intact:

```
sysrc jail_list-="opencode"
```

(`sysrc`'s `-=` form removes a single entry from a space-separated list
without touching the rest — the mirror of the `+=` used to add it.)

Leave `jail_enable="YES"` and `linux_enable="YES"` alone — both are
host-wide settings almost certainly still needed by other jails and/or the
host's own Linuxulator setup from step 2, not specific to this one jail.

### 3. Remove the host IP alias

If `198.18.51.27` isn't used by anything else on this host, remove the
persistent alias from `/etc/rc.conf`:

```
sysrc -x ifconfig_em0_alias0
```

(`-x` deletes the variable outright, rather than setting it to something.)
Then tear down the live alias without waiting for a reboot:

```
ifconfig em0 -alias 198.18.51.27
```

Skip this step if the same interface/alias name is shared with another
jail or service on this host — check before removing.

### 4. Remove the jail.conf.d files

```
rm /etc/jail.conf.d/opencode.conf
rm /etc/jail.conf.d/opencode.fstab
```

Since this host's `/etc/jail.conf` only does
`.include "/etc/jail.conf.d/*.conf";` rather than defining jails directly
(see step 3 of the setup instructions above), deleting these two files is
enough — there's nothing referencing `opencode` left in the main
`/etc/jail.conf` to clean up separately.

### 5. Remove the jail's root filesystem

First confirm whether `/jails/opencode` is a plain directory or its own
ZFS dataset. This setup was created via `mkdir -p /jails/opencode` +
`bsdinstall jail /jails/opencode` into that plain path, so it's almost
certainly just a directory on whatever filesystem `/jails` lives on, not
a separate dataset — but confirm rather than assume:

```
zfs list -H -o name /jails/opencode 2>/dev/null
```

If that prints a dataset name, destroy it that way instead of `rm -rf`:

```
zfs destroy -r zroot/jails/opencode   # adjust dataset name to match
```

If it's a plain directory (the expected case here), check for
immutable/system flags before attempting removal. `rm -rf` fails partway
through — leaving a half-deleted tree behind — if it hits a file with
`schg`/`sappnd`/`sunlnk`/etc. set, which can happen on parts of a base
install or a `linux-rl9`/`linux-c7` userland depending on how it was
built:

```
find /jails/opencode -flags +schg,sappnd,uappnd,uunlnk,sunlnk 2>/dev/null
```

If that lists anything, clear the flags recursively first — safe here
since the whole tree is being deleted regardless:

```
chflags -R noschg /jails/opencode
```

Then remove the tree:

```
rm -rf /jails/opencode
```

### 6. Sanity check

```
jls                                      # opencode should no longer be listed
mount | grep opencode                    # should be empty
ls /etc/jail.conf.d/ | grep opencode      # should be empty
grep opencode /etc/rc.conf                # should return nothing
```

Together these confirm removal at every layer this guide touched: jail no
longer running, no leftover compat/nullfs mounts, no leftover
`jail.conf.d` files, no leftover `rc.conf` state (`jail_list` entry, IP
alias), and the filesystem itself gone.
