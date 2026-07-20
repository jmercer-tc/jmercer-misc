# Fresh FreeBSD Jail for opencode — Native Bun, No Linuxulator

Start-to-finish build of a **brand-new** jail at **198.18.51.28/32** to run opencode
(CLI/TUI and web mode) using native FreeBSD Bun — superseding the old Linuxulator-based
draft (`freebsd-opencode-jail.md`, jail `.27`, which hit a `preadv2 not implemented` dead
end under Linuxulator).

This document consolidates everything validated in the `.27` jail so far — the TUI's native
`@opentui/core` renderer needs a small patch set plus a custom-built FreeBSD `.so`, and one
unrelated package (`@ff-labs/fff-bun`) needs a lazy-load patch to avoid an eager top-level
crash on FreeBSD — **with one important correction**: `.27`'s "confirmed working" Bun install
(the `curl -fsSL https://bun.sh/install | bash` script) turned out to have installed a
**Linux ELF binary of Bun**, not a true native FreeBSD build. That only worked on `.27`
because `.27` still had the Linuxulator enabled (it started life as a Linuxulator jail), so
the Linux binary ran fine under Linux emulation. This jail deliberately has no Linuxulator,
so the exact same install script fails outright (`ELF interpreter
/lib64/ld-linux-x86-64.so.2 not found`). See section 6 for the real fix — building FreeBSD's
native `lang/bun` port, since no pre-built binary package exists for it yet. **Update: this is
now done and confirmed** — `bun 1.3.14` built from `lang/bun` and verified as a genuine native
FreeBSD ELF binary (section 6c). The build itself turned out to have its own hidden
Linux-ABI dependency (section 6c-i) — ironic given the whole point of this doc — but that's
isolated to the one-time build step and doesn't affect the resulting binary or the runtime
jail.

Status legend used throughout:
- **[confirmed]** — actually run and observed working on the `.27` jail. (Caveat added above:
  where this label was previously applied to Bun's install specifically, treat it as
  confirmed-under-Linuxulator-emulation, not confirmed-native — see section 6.)
- **[carried over]** — jail-scaffolding steps reused verbatim from the old guide; mechanically
  the same regardless of Linuxulator, just re-parameterized for the new IP/name.
- **[unverified]** — assembled from source-code inspection (byte-identical npm package + the
  user's own git diff), not yet run end-to-end. Flagged inline so you know what to double-check
  first.
- **[in progress]** — actively being worked out on `opencode-fbsd2` right now; not yet
  confirmed end-to-end, and the steps below may still change once the outcome is known.

---

## 0. Environment for this jail

| Item | Value |
|---|---|
| Jail IP | `198.18.51.28/32` |
| Jail name | `opencode-fbsd2` |
| Jail user | `oc-user` |
| opencode source | `/home/oc-user/wip/opencode-src` (fresh clone) |
| Web port | `4096` |
| Host | rep-laptop |

Anywhere the old `.27` doc used `198.18.51.27/24` + `opencode-fbsd` + `opencode`, this
guide uses the values above instead. The `/32` (vs `/24`) is deliberate — a single-address
alias, no subnet semantics implied.

---

## 1. Host network prep **[carried over]**

As root on rep-laptop, add the jail's IP as an alias on the appropriate interface. Confirm
the interface name first:

```sh
ifconfig -l
```

Then add the alias (replace `em0` with your actual interface):

```sh
ifconfig em0 alias 198.18.51.28/32
```

To persist across reboots, add to `/etc/rc.conf`:

```sh
sysrc ifconfig_em0_alias0="inet 198.18.51.28/32"
```

Verify:

```sh
ifconfig em0 | grep 198.18.51.28
```

---

## 2. Jail creation — no Linuxulator **[carried over, trimmed]**

Do **not** install `linux_base-*`, `linux-c7`, or enable `linux` module loading — none of
that is needed. Native Bun runs directly on FreeBSD.

### 2a. Lay down the base userland — non-interactive **[new]**

> **Hit this exact error on the first pass:** `mount.devfs: /jails/opencode-fbsd2/dev: No
> such file or directory` when running `service jail start` — the base userland was never
> actually extracted into `/jails/opencode-fbsd2`, so there's no `/dev` for `mount.devfs`
> to attach to. This step has to happen **before** `service jail start`, not after.

`bsdinstall jail` works but is interactive (a `dialog`-based distribution-set checklist and
mirror prompt). To skip that entirely, extract `base.txz` directly.

**[confirmed present on rep-laptop]** The installer already leaves a copy of `base.txz` on
disk at `/usr/freebsd-dist/base.txz` — no network fetch needed at all, and it guarantees an
exact version match with the running host (better than pulling a potentially different
point release from a mirror):

```sh
mkdir -p /jails/opencode-fbsd2
tar -xf /usr/freebsd-dist/base.txz -C /jails/opencode-fbsd2 --unlink
```

If that file isn't present on whatever host you're building this on, fall back to fetching
it over the network for the release the host is running:

```sh
mkdir -p /jails/opencode-fbsd2

REL=$(freebsd-version -u)   # e.g. 14.2-RELEASE
fetch -o /tmp/base.txz "https://download.freebsd.org/ftp/releases/amd64/amd64/${REL}/base.txz"
tar -xf /tmp/base.txz -C /jails/opencode-fbsd2 --unlink
rm /tmp/base.txz
```

Either way, that's the whole base system — no dialog, no prompts, no interactive mirror
selection. `--unlink` avoids `tar` choking on any pre-existing files if you ever re-run this
against the same directory.

If you'd rather use `bsdinstall` specifically (e.g. to match exactly how the `.27` jail was
built), it can also be driven non-interactively by pre-setting the distribution list and
site instead of accepting the dialog defaults:

```sh
mkdir -p /jails/opencode-fbsd2
export BSDINSTALL_CHROOT=/jails/opencode-fbsd2
export BSDINSTALL_DISTDIR=/tmp/bsdinstall_dist_opencode-fbsd2
export DISTRIBUTIONS="base.txz"
export BSDINSTALL_DISTSITE="https://download.freebsd.org/ftp/releases/amd64/amd64/$(freebsd-version -u)/"
bsdinstall distfetch
bsdinstall distextract
```

Either path leaves you with the same result: a populated `/jails/opencode-fbsd2`. The
`fetch`+`tar` version above is simpler and has fewer moving parts, so it's the recommended
default.

Note: a freshly-extracted `base.txz` has **no root password set** (locked) — that gets
fixed in 2c, once the jail is actually running (`jexec` needs a running jail to attach to,
so it can't happen here in 2a).

### 2b. Jail config

Minimal `/etc/jail.conf.d/opencode-fbsd2.conf`:

```
opencode-fbsd2 {
    host.hostname = "opencode-fbsd2";
    path = "/jails/opencode-fbsd2";
    ip4.addr = "198.18.51.28";
    interface = "em0";
    exec.start = "/bin/sh /etc/rc";
    exec.stop = "/bin/sh /etc/rc.shutdown";
    exec.clean;
    mount.devfs;
    allow.raw_sockets = 0;
}
```

### 2c. Enable and start it

```sh
sysrc jail_list+="opencode-fbsd2"
service jail start opencode-fbsd2
jls
```

You should see `opencode-fbsd2` listed with IP `198.18.51.28`.

> Reminder for later teardown: removing a jail from autostart is `sysrc jail_list-="opencode-fbsd2"`,
> not editing the string by hand — avoids stray whitespace/duplicate entries in `rc.conf`.

Now that the jail is actually running, `jexec` has something to attach to — set the root
password (noted back in 2a as deferred to here):

```sh
jexec opencode-fbsd2 passwd root
```

This one is expected to prompt interactively — that's fine. The non-interactive goal in 2a
was specifically about skipping `bsdinstall`'s distribution-set/mirror `dialog` UI, not
about eliminating every prompt everywhere; a simple password prompt run on its own is a
different kind of interactive step and doesn't need scripting around. (If you ever do want
this scripted too, `echo 'yourpassword' | jexec opencode-fbsd2 pw usermod root -h 0` sets it
non-interactively by reading the plaintext password from stdin — but there's no real need
to bother for a one-time setup step like this.)

### 2d. Fix DNS resolution inside the jail **[new]**

A fresh `base.txz` extraction has no `/etc/resolv.conf` — the jail can reach the network
(it has an IP and route via the host), but hostname lookups (e.g. `pkg install`, `git
clone`, `curl` against a domain name) will fail until DNS is configured. Point it at public
resolvers:

```sh
jexec opencode-fbsd2 sh -c 'cat > /etc/resolv.conf <<EOF
nameserver 8.8.8.8
nameserver 8.8.4.4
EOF'
```

Verify:

```sh
jexec opencode-fbsd2 host freebsd.org
```

Do this **before** section 3 — `pkg install` needs to resolve its package-repo mirror
hostname, and it'll fail with something like `Could not resolve host` otherwise.

---

## 3. Toolchain packages inside the jail **[carried over + zig added]**

```sh
jexec opencode-fbsd2 pkg install -y \
    git curl ca_root_nss bash sudo vim \
    zig \
    pkgconf gmake
```

`zig` is a new addition versus the old doc — it's required later to build `@opentui/core`'s
native renderer from source for FreeBSD (the upstream npm package only ships
darwin/linux/win32 binaries).

Note: FreeBSD's `pkg install zig` currently lands **0.16.0**, newer than the
`0.15.2` that `@opentui/core`'s `build.zig` officially lists as supported. Section 8 below
includes the one-line `SUPPORTED_ZIG_VERSIONS` patch needed to accept it.

---

## 4. Create the `oc-user` account **[carried over]**

Shell is `/usr/local/bin/bash` (installed via `pkg` in section 3, which runs before this
step):

```sh
jexec opencode-fbsd2 pw useradd oc-user -m -s /usr/local/bin/bash -G wheel
jexec opencode-fbsd2 passwd oc-user
```

`pw useradd -m` populates the home directory from `/usr/share/skel`, which includes a
`.profile` (copied in as `~/.profile`) but has no bash-specific skeleton file — bash as a
login shell reads `~/.bash_profile` instead, and won't pick up `.profile` on its own. Add a
`.bash_profile` that sources it, and also puts `~/.bun/bin` on `PATH` (Bun isn't installed
yet at this point in the guide — that happens in section 6 — but it's harmless to reference
the directory in `PATH` before it exists):

```sh
jexec opencode-fbsd2 sh -c '
cat > /home/oc-user/.bash_profile <<EOF
if [ -f "\$HOME/.profile" ]; then
  . "\$HOME/.profile"
fi
export PATH="\$HOME/.bun/bin:\$PATH"
EOF
chown oc-user:oc-user /home/oc-user/.bash_profile
'
```

**[confirmed]** `$HOME` is already set correctly for a login shell obtained via
`jexec -U oc-user opencode-fbsd2 /usr/local/bin/bash` (verified: `echo $HOME` →
`/home/oc-user`) — no need to `export HOME=...` by hand in that case. `$PATH`, once Bun is
installed in section 6, will also be correct automatically via this `.bash_profile`, without
needing to `export PATH=...` by hand either.

> **Caveat that still applies — confirmed the hard way on `.27`:** this only works for an
> actual **login shell** (`jexec -U oc-user opencode-fbsd2 /usr/local/bin/bash`, as used from
> section 6 onward). One-shot, non-login `jexec` invocations that specify a command directly
> (e.g. `jexec -U oc-user opencode-fbsd2 some-command`) do **not** go through
> `.bash_profile` at all, so `HOME`/`PATH` still need to be set explicitly in those:
> ```sh
> export HOME=/home/oc-user
> export PATH="$HOME/.bun/bin:$PATH"
> ```

---

## 4a. Copy the patch files into `oc-user`'s home directory **[new]**

The patch files referenced later in sections 7a/8b/8c
(`opentui-monorepo-freebsd-target.patch`, `opentui-core@0.4.5-freebsd-native-file-names.patch`,
`@ff-labs%2Ffff-bun@0.9.3-existing-reference.patch`, plus their `README.md`) live in the
`jmercer-misc` repo on GitHub — pushed there from jmercer-wavelo (the work laptop), not
present on rep-freebsd itself. Now that `oc-user`'s home directory exists, get them staged
before going any further.

**Chosen approach: manual copy.** Rather than cloning the repo on rep-freebsd, transfer the
four files directly from jmercer-wavelo to rep-freebsd by whatever means is convenient
(`scp`, a USB drive, etc. — jmercer-wavelo and rep-freebsd are deliberately kept separate,
per earlier discussion, so this is a manual hop between the two, not an automated pull).

End state required before continuing: all four files present at
**`/home/oc-user/patches/`** inside the jail (i.e. `/jails/opencode-fbsd2/home/oc-user/patches/`
from the host's point of view), owned by `oc-user`:

- `opentui-monorepo-freebsd-target.patch`
- `opentui-core@0.4.5-freebsd-native-file-names.patch`
- `@ff-labs%2Ffff-bun@0.9.3-existing-reference.patch`
- `README.md`

If you land the files somewhere else on rep-freebsd first (e.g. `/tmp` via `scp`), move them
into place and fix ownership — since the jail's filesystem is an ordinary directory tree
from the host's perspective, a plain `mv`/`cp` works, no jail networking required:

```sh
mkdir -p /jails/opencode-fbsd2/home/oc-user/patches
mv /tmp/*.patch /tmp/README.md /jails/opencode-fbsd2/home/oc-user/patches/
chown -R oc-user:oc-user /jails/opencode-fbsd2/home/oc-user/patches
```

Verify from inside the jail:

```sh
jexec -U oc-user opencode-fbsd2 ls -la /home/oc-user/patches
```

> **Don't use `~/patches` here** — `~` gets expanded by the shell you're typing this into on
> the host (running as root, whose `$HOME` is `/root`), *before* `jexec` ever runs, not by
> anything inside the jail. That's why `ls -la ~/patches` resolves to `/root/patches`
> instead of `oc-user`'s home — it's a distinct trap from the "jexec doesn't source shell
> profiles" caveat noted earlier, though it rhymes with it. Stick to absolute paths
> (`/home/oc-user/...`) in one-shot `jexec -U oc-user ...` commands, or wrap in
> `sh -c 'export HOME=/home/oc-user; ...'` if you want `~` to resolve inside the jail.

You should see all three `.patch` files plus `README.md`. Sections 7a, 8b, and 8c below now
assume these are already sitting in `~/patches` — the inline diffs are kept alongside as a
fallback/reference in case you need to re-derive one by hand.

---

## 5. SSH access (optional, not required by this guide) **[carried over]**

```sh
jexec opencode-fbsd2 sysrc sshd_enable="YES"
jexec opencode-fbsd2 service sshd start
```

Then from the host: `ssh oc-user@198.18.51.28`. This is purely a convenience if you want an
SSH-based terminal for your own use later — everything from section 6 onward in this guide
is written assuming `jexec`, not SSH, so feel free to skip this section entirely.

---

## 6. Install native Bun **[in progress]**

Everything from here through section 9 assumes a single persistent interactive shell,
opened as `oc-user` inside the jail via `jexec` (not SSH):

```sh
jexec -U oc-user opencode-fbsd2 /usr/local/bin/bash
```

Stay in that one shell session for the rest of sections 6-9 — the `cd` state (and anything
beyond what `.bash_profile` already sets up) carries over from one command to the next
within it. If the session ever gets closed, just re-run the `jexec` line above to get back
in — since this is a login shell, section 4's `.bash_profile` sets `HOME`/`PATH` correctly
again automatically, no manual `export` needed on re-entry.

### 6a. What doesn't work: the `bun.sh` curl script

```sh
curl -fsSL https://bun.sh/install | bash
```

**Do not use this on this jail.** It lands a binary at `~/.bun/bin/bun`, but running it
fails immediately:

```
ELF interpreter /lib64/ld-linux-x86-64.so.2 not found, error 2
Abort trap
```

`bun.sh`'s install script only ships Linux and macOS builds — on FreeBSD it silently
downloads the Linux x86_64 build, which needs the Linux dynamic linker
(`/lib64/ld-linux-x86-64.so.2`) to run. That path only exists under the Linuxulator, which
this jail deliberately doesn't have. (This is exactly why it appeared to work on `.27` — see
the note at the top of this document.) If you hit this, `rm -rf ~/.bun` to clean up the
unusable Linux binary before continuing below.

### 6b. What also doesn't work (yet): `pkg install bun`

FreeBSD does have a native `lang/bun` port (confirmed via FreshPorts), but as of this
writing it's brand new (added 2026-04-28, last touched 2026-06-30) and has **no pre-built
binary package** in either the default quarterly repo or the `latest` repo — FreshPorts
itself notes "Package not present on quarterly... will be in the next quarterly branch but
not the current one." Both of these were tried and confirmed empty:

```sh
# quarterly (the jail's default repo) — confirmed: "No packages available to install matching 'bun'"
jexec opencode-fbsd2 pkg install -y bun

# latest branch, via a repo override — also confirmed empty once the override syntax was
# fixed to include mirror_type (pkg+ URLs require it explicitly):
jexec opencode-fbsd2 sh -c '
cat > /usr/local/etc/pkg/repos/FreeBSD.conf <<EOF
FreeBSD: {
  url: "pkg+http://pkg.FreeBSD.org/\${ABI}/latest",
  mirror_type: "srv",
  signature_type: "fingerprints",
  fingerprints: "/usr/share/keys/pkg",
  enabled: yes
}
EOF
pkg update -f
pkg install -y bun
'
```

If you tried the `latest` override, revert it afterward so the jail's other packages stay on
a single consistent branch:

```sh
jexec opencode-fbsd2 rm -f /usr/local/etc/pkg/repos/FreeBSD.conf
jexec opencode-fbsd2 pkg update -f
```

### 6c. Build `lang/bun` from the ports tree **[confirmed]**

Since no binary package exists yet, the port has to be built from source. **Correction to an
earlier assumption in this doc:** the ports system does *not* default to installing a port's
build dependencies (`llvm21`, `cmake`, `ninja`, `rust`, `node24`, `npm-node24`) as binary
packages automatically — plain `make install` builds everything from source unless told
otherwise, which for something like `llvm21`/`rust` can mean a multi-hour compile just to get
to the point of building `bun` itself. Two things fix that:

- **`make install-missing-packages`** — installs any missing dependencies via `pkg` (binary)
  before the main build runs, instead of compiling them from source.
- **`BATCH=yes`** — suppresses interactive `make config` / license-acceptance dialogs
  anywhere in the dependency chain (FreshPorts shows `lang/bun` itself has no config options,
  but some of its dependencies may still prompt for a license acceptance without this).

```sh
# populate /usr/ports inside the jail (shallow clone keeps it small)
jexec opencode-fbsd2 pkg install -y git
jexec opencode-fbsd2 git clone --depth 1 https://git.FreeBSD.org/ports.git /usr/ports

# pre-install dependencies as binary packages, then build only bun itself from source —
# fully non-interactive
jexec opencode-fbsd2 sh -c '
export BATCH=yes
export ASSUME_ALWAYS_YES=yes
cd /usr/ports/lang/bun
make install-missing-packages
make install clean
'
```

If you already had a plain `make install clean` running before reading this and it's visibly
compiling something huge (`llvm`, `rust`), it's worth `Ctrl-C`-ing it and restarting with the
sequence above rather than waiting it out — a from-source `llvm21`/`rust` build can take
hours on top of what building `bun` itself needs.

**For any future rebuild, use `make install package clean` instead of plain `make install
clean`** (see 6d) — `bsd.port.mk` has a `package` target that stages the build and produces a
distributable `.pkg` archive directly, without a separate `pkg create` step afterward. The
in-flight build on `opencode-fbsd2` right now was started with plain `make install clean`
(before this was worked out), so it still needs the manual `pkg create -o` step in 6d if it
succeeds — this simplification is for the *next* jail/rebuild, not this one.

**Resource use during the build is heavy — expect this, don't panic.** The build passes
`-Dllvm_codegen_threads=8` (matched to CPU count), so it runs that many parallel LLVM
codegen/optimization jobs at once; observed peak on rep-laptop was 100% across all 8 CPUs and
~40GB RAM during the LLVM object-codegen stage. That's well above the ~16GB the community
`8ff/bun-freebsd` project quotes as a rough minimum — evidently optimistic for full-parallelism
codegen. rep-laptop has 64GB total, so a 40GB peak still leaves ~24GB of headroom — shouldn't
swap under normal conditions. Not a sign of a problem by itself; only worth intervening if it
starts swapping heavily or a compiler process gets OOM-killed, in which case reducing
parallelism would be the next thing to try.

**Confirmed working on `opencode-fbsd2`** (after the `linprocfs`/`linsysfs` workaround in
6c-i). Verified:

```sh
jexec opencode-fbsd2 bun --version
# 1.3.14

jexec opencode-fbsd2 file $(jexec opencode-fbsd2 which bun)
# /usr/local/bin/bun: ELF 64-bit LSB executable, x86-64, version 1 (FreeBSD), dynamically
# linked, interpreter /libexec/ld-elf.so.1, for FreeBSD 15.1, FreeBSD-style, stripped

jexec opencode-fbsd2 pkg info bun
# Architecture: FreeBSD:15:amd64 — matches earlier ABI observation
# Shared Libs required: libc++.so.1, libc.so.7, libcxxrt.so.1, libexecinfo.so.1,
#   libgcc_s.so.1, libm.so.5, libthr.so.3 — all base-system libs, no run-depends on other
#   ports. Confirms the cached .pkg (6d) will stand alone on any same-release jail.
# Flat size: 100MiB
```

Genuine native FreeBSD ELF, dynamically linked against the real `/libexec/ld-elf.so.1` — not
the Linux ABI stub from 6a. `bun` landed at `/usr/local/bin/bun` automatically via ports/pkg,
which is already on `PATH` via `/usr/share/skel/dot.profile`, so section 4's `~/.bun/bin`
`PATH` addition is confirmed unnecessary (harmless no-op) rather than required.

### 6c-i. Blocking build failure: `zig obj` → `error: FileNotFound` **[root cause found, fix in progress]**

`make build` (and the combined `make install clean`) both reproducibly fail during bun's own
internal build step, not the ports dependency stage. Bun's build shells out to a bootstrap
Zig binary (`/usr/ports/lang/bun/work/oven-zig/bootstrap-x86_64-linux-musl/zig`) to
cross-compile `bun-zig.{0..7}.o` via `zig build obj`, targeting
`-Dtarget=x86_64-freebsd.14.3-none` with `-Dfreebsd_sysroot=/` and a generated libc descriptor
file. The ninja output shows a bare `error: FileNotFound` (no path given) immediately followed
by `FAILED: [code=1] bun-zig.0.o ... bun-zig.7.o` and `ninja: build stopped: subcommand
failed.` Confirmed reproducible across a clean `make clean` + `install-missing-packages` +
`make build` re-run, ruling out stale work-directory state.

Ruled out:
- Stale/interrupted `work/`-directory state (recurred after a clean re-run).
- Upstream oven-sh/bun issue [#25756](https://github.com/oven-sh/bun/issues/25756) — different
  OS (Arch Linux), different error shape, unresolved/closed as "docs". Not the same bug.
- **FreeBSD 14.3-vs-15.x sysroot mismatch** (the zig target is hardcoded to
  `x86_64-freebsd.14.3-none`, while this jail is actually `15.1-RELEASE-p1`, confirmed via
  `freebsd-version`). The generated `build/release/freebsd-libc.txt` only lists generic paths
  (`/usr/include`, `/usr/lib`) with nothing 14.3-version-specific baked in, so this dead-ends
  too — not the cause.

**Actual root cause, confirmed via `truss -f` on the exact `zig build obj` invocation:** the
bootstrap Zig binary the port downloads
(`oven-zig/bootstrap-x86_64-linux-musl/zig`) is a **Linux** ELF binary, not FreeBSD. It runs at
all because FreeBSD's kernel-level Linux ABI translation is apparently already active on this
host (host-wide kernel module, most likely left loaded from `.27`'s earlier Linuxulator setup —
kernel modules aren't per-jail, so once loaded they stay active for every jail on rep-laptop
regardless of that jail's own intended design). The truss log shows the translated `linux_*`
syscalls succeeding for basic startup (mmap, arch_prctl, etc.), but then:

```
linux_open("/proc/sys/vm/overcommit_memory",0x0,00) ERR#-2 'No such file or directory'
linux_open("/sys/kernel/mm/transparent_hugepage/enabled",0x0,00) ERR#-2 'No such file or directory'
linux_readlink("/proc/self/exe",0x7fffffffa430,4096) ERR#-2 'No such file or directory'
```

(Note: truss reports Linux-ABI-translated syscall failures with a **negative** error code,
`ERR#-2`, not the `ERR#2` used for native BSD syscalls — easy to miss with a naive grep.)

This jail deliberately has no `linprocfs`/`linsysfs` mounted (the whole point of this doc was
avoiding Linuxulator plumbing), so those Linux-style `/proc`/`/sys` paths don't exist. The
`/proc/self/exe` failure is the fatal one: Zig's standard library resolves its own executable
path via `readlink("/proc/self/exe")` on Linux targets (`std.fs.selfExePath`), and maps a
failed lookup straight to `error.FileNotFound` — an exact match for the bare, path-less error
we've been seeing. Right after these three failed lookups the process does normal
allocator/thread setup (mmap/madvise/gettid) and then calls `exit_group(1)` directly — no
further diagnostics printed, consistent with an early, generic error path.

**Conclusion:** building `lang/bun` from ports has a genuine *build-time* dependency on Linux
ABI compatibility (specifically, a working `/proc/self/exe`), even though the resulting `bun`
binary itself is confirmed to target `x86_64-freebsd` and needs no Linux compat to run. This
doesn't contradict the "no Linuxulator at runtime" goal of this jail — it's isolated to the
one-time build step, which is exactly why section 6d's package-caching plan matters (pay this
cost once, reuse the `.pkg` forever after).

**Fix being tried now (Option A): temporarily mount `linprocfs`/`linsysfs` into this same
builder jail, retry the build, then unmount once it succeeds** — keeps the runtime jail
Linuxulator-free between builds:

```sh
kldstat | grep -i linux
mount -t linprocfs linproc /jails/opencode-fbsd2/proc
# /jails/opencode-fbsd2/sys is a symlink to usr/src/sys (standard FreeBSD skeleton layout);
# this jail has no /usr/src populated, so the target dir has to be created first or the
# linsysfs mount fails trying to follow the symlink ("No such file or directory")
mkdir -p /jails/opencode-fbsd2/usr/src/sys
mount -t linsysfs linsys /jails/opencode-fbsd2/sys
mount | grep opencode-fbsd2   # confirm both linprocfs and linsysfs show up
```

then retry the `make install-missing-packages` / `make install clean` sequence from 6c
(currently running — this is the in-flight build). Once it succeeds (and section 6d's package
is cached), unmount both:

```sh
umount /jails/opencode-fbsd2/proc
umount /jails/opencode-fbsd2/sys
```

**Option B (not tried, fallback if A has problems):** do the `lang/bun` ports build in a
separate, disposable Linuxulator-enabled builder jail (mirroring `.27`'s original setup), then
copy the resulting cached `.pkg` (section 6d) into this clean `opencode-fbsd2` runtime jail via
`pkg add` — cleaner separation, more setup up front.

### 6d. Cache the built package on the jail host **[confirmed]**

Done. Cached at `/usr/local/pkg-cache/bun-1.3.14_3.pkg` on rep-laptop (28MB, ABI
`FreeBSD:15:amd64`). The `linprocfs`/`linsysfs` mounts from 6c-i were also unmounted from
`opencode-fbsd2` afterward — confirmed clean (`mount | grep opencode-fbsd2` shows only
`devfs`). Any future jail rebuild on this same FreeBSD 15.1 host can skip the entire
multi-hour ports build: just copy this `.pkg` in and `pkg add` it (see below).

Since `lang/bun` has no upstream binary package yet, that multi-hour build is a one-off cost
worth not paying again — every future jail (a rebuilt `opencode-fbsd2`, or eventually retiring
`.27` in favor of a same-approach `opencode-fbsd`) can reuse the exact package this build just
produced. `bun`'s own port has no listed run-depends, so the resulting package should stand
alone at install time with no need to also cache the whole llvm/rust/node toolchain.

Build a distributable `.pkg` from the already-installed copy (run inside the jail, as root):

```sh
jexec opencode-fbsd2 mkdir -p /root/pkg-cache
jexec opencode-fbsd2 pkg create -o /root/pkg-cache bun
```

**For future rebuilds, skip this manual `pkg create` step entirely** — `bsd.port.mk` has its
own `package` target that stages the build and writes a `.pkg` archive directly, no separate
command needed. Use `make install package clean` instead of plain `make install clean` in 6c,
and the archive lands at `/usr/ports/packages/All/bun-*.pkg` inside the jail (i.e.
`/jails/<jail-name>/usr/ports/packages/All/bun-*.pkg` from the host) — just `cp` that straight
to `/usr/local/pkg-cache` on rep-laptop. The `pkg create -o` approach above is what this
*current* in-flight build needs (it was started before this shortcut was worked out), but
isn't the preferred method going forward.

This produces something like `/root/pkg-cache/bun-1.3.14_3.pkg` inside the jail. Copy it out
to a persistent spot on rep-laptop itself (**not** inside any jail's directory tree, so it
survives jail teardown/rebuild) — since the jail's filesystem is an ordinary directory tree
from the host's point of view, a plain `cp` works:

```sh
mkdir -p /usr/local/pkg-cache
cp /jails/opencode-fbsd2/root/pkg-cache/bun-*.pkg /usr/local/pkg-cache/
```

Packages are tied to a specific FreeBSD ABI (release + arch, e.g. `FreeBSD:15:amd64` —
confirm with `jexec opencode-fbsd2 pkg config ABI`), so this cached file is only valid for
future jails built from the same release; a different FreeBSD version would need its own
build. Worth naming/tagging the file with that ABI if you expect to eventually juggle more
than one release.

To reuse it in a future jail instead of rebuilding from ports, just copy it in and install
directly — no repo catalog needed for a single cached package:

```sh
# from the host, into the new jail's filesystem
cp /usr/local/pkg-cache/bun-*.pkg /jails/<new-jail-name>/root/

# then inside that jail
jexec <new-jail-name> pkg add /root/bun-*.pkg
```

(If this ever grows beyond one or two cached packages and juggling filenames/versions by
hand gets annoying, `pkg repo /usr/local/pkg-cache` will generate a proper repo catalog over
that directory, which you could then point a jail's `/usr/local/etc/pkg/repos/` config at as
a `file://` repo — not needed yet for just `bun`, but worth knowing if this cache grows.)

---

## 7. Clone and build opencode **[confirmed for install; TUI render unverified]**

```sh
mkdir -p ~/wip
cd ~/wip
git clone https://github.com/anomalyco/opencode.git opencode-src
cd opencode-src
```

### 7a. Fix `@ff-labs/fff-bun` (unrelated native-addon crash) **[confirmed — real fix is a source edit, not a dependency patch]**

This package has no FreeBSD build of its prebuilt native addon. The crash isn't inside
`@ff-labs/fff-bun` itself, though — it's in how opencode's own wrapper consumes it.
`packages/core/src/filesystem/fff.bun.ts` did an eager top-level `import { FileFinder, ... }
from "@ff-labs/fff-bun"`, which forces Bun to load the native binding at module-evaluation
time, before opencode even starts, on every platform including ones with no prebuilt
binary for it.

**Root cause detail:** the installed version is `@ff-labs/fff-bun@0.9.4` (see
`packages/core/package.json`). The pre-existing `patches/@ff-labs%2Ffff-bun@0.9.3.patch`
tracked in this repo (and copied to `~/patches` in section 4a) is for the *previous*
version and is unrelated to FreeBSD — it predates this investigation and isn't a
dependency-patch fix for this crash. Don't try to extend it; it's a red herring for this
specific problem.

**The actual, verified fix** is a plain source-level edit to opencode's own file —
no `bun patch` of the dependency needed at all. Change the top-level `import` of runtime
values to a type-only import, and wrap the actual `require()` in this codebase's existing
`lazy()` helper so the native module is only touched (and can fail safely) the first time
a caller actually needs it:

```ts
// packages/core/src/filesystem/fff.bun.ts — before
import {
  FileFinder,
  type DirItem, /* ...other types... */
} from "@ff-labs/fff-bun"

export function available() {
  return FileFinder.isAvailable()
}
export function create(opts: Init): Result<Picker> {
  const made = FileFinder.create(opts)
  // ...
}
```

```ts
// packages/core/src/filesystem/fff.bun.ts — after
import type {
  FileFinder as FileFinderType,
  DirItem, /* ...other types... */
} from "@ff-labs/fff-bun"
import { lazy } from "../util/lazy"

// @ff-labs/fff-bun ships prebuilt native bindings only for a subset of
// platforms (no FreeBSD build, for example). Load it lazily and tolerate a
// missing module so callers can fall back to the ripgrep-based search layer
// instead of crashing at import time.
const mod = lazy((): typeof import("@ff-labs/fff-bun") | undefined => {
  try {
    return require("@ff-labs/fff-bun") as typeof import("@ff-labs/fff-bun")
  } catch {
    return undefined
  }
})

export function available() {
  return mod()?.FileFinder.isAvailable() ?? false
}
export function create(opts: Init): Result<Picker> {
  const finder = mod()?.FileFinder as typeof FileFinderType | undefined
  if (!finder) return { ok: false, error: "@ff-labs/fff-bun native module is not available on this platform" }
  const made = finder.create(opts)
  // ...
}
```

This is a small, self-contained diff to a file opencode owns, so it's a good candidate to
upstream as a PR rather than carry as a local patch forever. Confirmed working: with this
change in place, importing `fff.bun.ts` (and everything that transitively imports it) no
longer throws at load time on a platform with no native binding.

### 7b. Install dependencies **[confirmed, with one extra prerequisite]**

```sh
bun install
```

**Extra prerequisite discovered on `opencode-fbsd2`:** `tree-sitter-powershell` (one of the
tree-sitter grammar packages opencode depends on) has no prebuilt FreeBSD binary and falls
back to compiling a native addon via `node-gyp`, which needs Python 3 — not present in this
minimal jail by default. Install it first:

```sh
jexec opencode-fbsd2 pkg install -y python3
```

With that in place, `bun install` completed cleanly: 2765 packages installed in ~34s, no
other native-addon build failures. (Order note: this subsection has to come *before* 7a's
`bun patch` commands in practice — `bun patch <pkg>` operates on an already-resolved
dependency in `node_modules`, so it can't run against an empty tree. Do 7b first, then 7a.)

---

## 8. Build native FreeBSD `@opentui/core` **[unverified end-to-end — see checklist]**

opencode's TUI depends on `@opentui/core`, a Zig-native terminal rendering engine. The
published npm package (`@opentui/core@0.4.5`, confirmed pinned exactly in this repo's
`bun.lock`) only ships prebuilt binaries for `darwin`/`linux`/`win32`. Two things are needed:
a FreeBSD build of the native library, and a small patch so the JS loader accepts
`"freebsd"` as a valid platform.

### 8a. Shortcut — reuse the already-built `.so` from the `.27` jail

If the `.27` jail still exists, the fastest path is to just copy its already-built
`libopentui.so` instead of rebuilding from scratch. Both jails' filesystems are ordinary
directory trees visible from the host, so this is a plain `cp` on **rep-freebsd** — no SSH,
no `scp`, no need for either jail's networking to be up:

```sh
# on rep-freebsd (the host), not inside either jail
mkdir -p /jails/opencode-fbsd2/home/oc-user/.otui-assets/@opentui/core-freebsd-x64
cp /jails/opencode-fbsd/home/oc-user/.otui-assets/@opentui/core-freebsd-x64/libopentui.so \
   /jails/opencode-fbsd2/home/oc-user/.otui-assets/@opentui/core-freebsd-x64/
chown -R oc-user:oc-user /jails/opencode-fbsd2/home/oc-user/.otui-assets
```

(Adjust `/jails/opencode-fbsd` if the `.27` jail's path differs — check with `jls` if
unsure.)

Skip to 8c if you do this.

### 8b. Building from source instead

Clone the standalone `opentui` monorepo (separate from opencode itself — it's the
upstream source for `@opentui/core`) and apply the three-file diff already validated
against a fresh checkout:

```sh
git clone https://github.com/sst/opentui.git ~/opentui
cd ~/opentui
```

Apply the patch copied over in section 4a:

```sh
git apply ~/patches/opentui-monorepo-freebsd-target.patch
```

The full diff is reproduced below too, in case you need to re-derive or hand-apply it:

```diff
diff --git a/packages/core/scripts/build.ts b/packages/core/scripts/build.ts
@@ -65,6 +65,7 @@ const variants: Variant[] = [
   { platform: "linux", arch: "arm64", abi: "musl" },
   { platform: "win32", arch: "x64" },
   { platform: "win32", arch: "arm64" },
+  { platform: "freebsd", arch: "x64" },
 ]
diff --git a/packages/core/src/node-asset-target.ts b/packages/core/src/node-asset-target.ts
@@ -1,5 +1,5 @@
 export type NodeAssetTarget = {
-  readonly platform: "darwin" | "linux" | "win32"
+  readonly platform: "darwin" | "linux" | "win32" | "freebsd"
   readonly arch: "arm64" | "x64"
   readonly libc?: "glibc" | "musl"
 }
@@ -13,6 +13,7 @@ export interface NativeAssetDescriptor {
 const NATIVE_FILE_NAMES = {
   darwin: "libopentui.dylib",
   linux: "libopentui.so",
+  freebsd: "libopentui.so",
   win32: "opentui.dll",
 } as const
diff --git a/packages/core/src/zig/build.zig b/packages/core/src/zig/build.zig
@@ -9,6 +9,7 @@ const SupportedZigVersion = struct {
 const SUPPORTED_ZIG_VERSIONS = [_]SupportedZigVersion{
     .{ .major = 0, .minor = 15, .patch = 2 },
+    .{ .major = 0, .minor = 16, .patch = 0 },
 };
@@ -27,6 +28,7 @@ const SUPPORTED_TARGETS = [_]SupportedTarget{
     .{ .zig_target = "aarch64-macos", .output_name = "aarch64-macos", .description = "macOS aarch64 (Apple Silicon)" },
     .{ .zig_target = "x86_64-windows-gnu", .output_name = "x86_64-windows", .description = "Windows x86_64" },
     .{ .zig_target = "aarch64-windows-gnu", .output_name = "aarch64-windows", .description = "Windows aarch64" },
+    .{ .zig_target = "x86_64-freebsd", .output_name = "x86_64-freebsd", .description = "FreeBSD x86_64" },
 };
```

Build:

```sh
cd ~/opentui/packages/core
bun run build
```

Stage the resulting `.so` where opencode's loader will find it via `OTUI_ASSET_ROOT`:

```sh
mkdir -p ~/.otui-assets/@opentui/core-freebsd-x64
cp dist/libopentui.so ~/.otui-assets/@opentui/core-freebsd-x64/
```

### 8c. Patch opencode's *installed copy* of `@opentui/core`

The upstream diff in 8b changes `opentui`'s own source tree — it doesn't touch the
already-published `@opentui/core@0.4.5` package that opencode actually installs from npm.
That installed copy needs the equivalent 1-line `NATIVE_FILE_NAMES`/platform-union patch
applied to its **built/bundled** JS output, in three files (confirmed identical across a
fresh npm download and this repo's actual Bun-isolated-linker install):

```
node_modules/@opentui/core/node-assets.js
node_modules/@opentui/core/chunk-bun-t2myhmwd.js
node_modules/@opentui/core/chunk-node-q0cwyvm9.js
```

(Bun's isolated linker means the real files live under
`node_modules/.bun/@opentui+core@0.4.5+<hash>/node_modules/@opentui/core/`, but running
`bun patch @opentui/core` resolves the right path automatically regardless of the hash —
don't try to hand-construct that path.)

Start the patch session:

```sh
cd ~/wip/opencode-src
bun patch @opentui/core
```

This prints something like:
```
To patch @opentui/core, edit the following folder:

  node_modules/@opentui/core

Once you're done with your changes, run:

  bun patch --commit 'node_modules/@opentui/core'
```

Apply the patch copied over in section 4a — this is a **real, mechanically-generated diff**
(produced by applying the edit to a byte-identical copy of the published npm package and
diffing against the original), so it should apply cleanly:

```sh
patch -p1 -d node_modules/@opentui/core < ~/patches/opentui-core@0.4.5-freebsd-native-file-names.patch
```

(`-p1 -d node_modules/@opentui/core` strips the `node_modules/@opentui/core/` prefix baked
into the diff paths.)

If it doesn't apply cleanly for some reason (e.g. a different `@opentui/core` patch version
than 0.4.5), fall back to the manual edit — each occurrence of `NATIVE_FILE_NAMES` looks
like:

```js
var NATIVE_FILE_NAMES = {
  darwin: "libopentui.dylib",
  linux: "libopentui.so",
  win32: "opentui.dll"
};
```

becomes:

```js
var NATIVE_FILE_NAMES = {
  darwin: "libopentui.dylib",
  linux: "libopentui.so",
  freebsd: "libopentui.so",
  win32: "opentui.dll"
};
```

or run this `python3` script, which does all three files in one shot:

```python3
import re, pathlib

base = pathlib.Path("node_modules/@opentui/core")
targets = ["node-assets.js", "chunk-bun-t2myhmwd.js", "chunk-node-q0cwyvm9.js"]

pattern = re.compile(
    r'(\{\s*darwin:\s*"libopentui\.dylib",\s*\n\s*linux:\s*"libopentui\.so",)(\s*\n\s*win32:)'
)
replacement = r'\1\n  freebsd: "libopentui.so",\2'

for name in targets:
    path = base / name
    text = path.read_text()
    new_text, count = pattern.subn(replacement, text)
    if count != 1:
        print(f"WARNING: {name} matched {count} times (expected 1) — check manually")
    else:
        path.write_text(new_text)
        print(f"patched {name}")
```

Run it, then commit the patch so it survives future `bun install` runs:

```sh
python3 patch_opentui.py
bun patch --commit 'node_modules/@opentui/core'
```

This creates a `patchedDependencies` entry, same convention as the existing
`patches/@ff-labs%2Ffff-bun@0.9.3.patch` in this repo.

> **Why this alone is sufficient — no Node 26 / `--experimental-ffi` needed:**
> `resolveNativeLibraryPath()` in `@opentui/core`'s Bun-runtime chunk checks
> `resolveAssetRootPath(asset.key)` — which returns the file path early (via
> `$OTUI_ASSET_ROOT/<packageName>/<fileName>`) **before** ever reaching the hardcoded
> darwin/linux/win32 fallback chain. The only reason the platform check needs patching at
> all is that `getNativeAssetDescriptor()` throws on an unrecognized `process.platform`
> *before* that early-return is reached — it's a guard, not the actual resolution path.
> The user's own `run-node26.mjs`/Node-26 harness (in the separate `opentui` monorepo
> checkout) is a **different, standalone test tool** for testing `opentui` outside of
> Bun — opencode itself always runs under Bun, so that harness is not part of this flow.

---

## 9. Set `OTUI_ASSET_ROOT` and sanity-check

`HOME`/`PATH` are already correct via `.bash_profile` (section 4) in this login shell;
`OTUI_ASSET_ROOT` is new and still needs to be set explicitly:

```sh
export OTUI_ASSET_ROOT="$HOME/.otui-assets"
cd ~/wip/opencode-src
```

### 9a. Web mode sanity check **[blocked in the jail by a TDZ crash — see 9a-i; not reproducible off-FreeBSD]**

```sh
cd packages/opencode
bun run src/index.ts web --port 4096 &
curl -s -D - http://198.18.51.28:4096/ -o /dev/null
```

(Note: opencode's web server sends `server: cloudflare` / `cf-ray` response headers
regardless of actual network path — this is opencode's own deliberate behavior, not a sign
your traffic is going anywhere external. Don't be alarmed by it.)

On `opencode-fbsd2`, this command actually crashes: a reference error / temporal-dead-zone
(TDZ) style crash pointing at `directories.ts:160`, thrown during module evaluation before
the listener ever comes up. See 9a-i for the investigation so far.

### 9a-i. TDZ crash at `directories.ts:160` — investigation so far **[unresolved; likely FreeBSD/ports-bun-specific, not a source bug — resume here tomorrow]**

**Symptom:** running `bun run src/index.ts web ...` in the jail throws a TDZ-shaped
reference error during startup, referencing `directories.ts:160` (a `database.ts` binding
read before its module finished initializing). This looks exactly like a circular-import
evaluation-order bug: `directories.ts` and `database.ts` import each other (directly or
transitively), and if the engine evaluates them in the wrong order relative to a live
binding read, you get exactly this crash.

**What's been ruled out so far** (all done as isolated repro scripts, run with a plain
`bun run`, no jail involved):

- A synthetic two-module repro with the *same shape* of circular, same-name binding
  (`mod-a.ts` / `mod-b.ts`, both exporting/reading a `node` binding, static `import`)
  evaluates in the correct order and does **not** crash.
- Importing `directories.ts` alone, in isolation, loads fine.
- Importing `project.ts` alone, in isolation, loads fine.
- Importing `WebCommand` (from `cli/cmd/web.ts`) alone, in isolation, loads fine — this is
  the actual entry point `bun run src/index.ts web` goes through, via a dynamic
  `import("../../server/server")` inside the handler.
- Replicating **all 31** of `packages/opencode/src/index.ts`'s top-level imports in one
  synthetic file, in the same order as the real file, loads fine — `ALL IMPORTS LOADED OK`.
- **Most significant:** running the actual, unmodified `opencode-src` checkout's real
  `web` command end-to-end (`bun run packages/opencode/src/index.ts web --port <N>`, full
  real dependency graph, `bun install`ed for real) starts up cleanly and serves requests
  (`HTTP 401`, as expected with no password set) — confirmed on **both** stable Bun
  `1.3.14` and canary Bun `1.4.0`, both on Linux (this rep-laptop's own sandbox, not the
  jail).
- Ran `madge --circular` across `packages/opencode/src` for a static view: the codebase
  does have a lot of circular imports (124 detected file-groups) — this is evidently just
  how this codebase is written, not inherently a bug — but nothing in that output isolates
  a single obvious `directories.ts ⇄ database.ts` cycle distinct from the rest. Given the
  crash won't even reproduce on Linux, static analysis alone isn't going to be conclusive
  here; it needs to be reproduced live to bisect properly.

**Working conclusion:** every attempt to reproduce this off of FreeBSD, including running
the exact real source tree through two different Bun versions, has failed to crash. That
shifts the likely root cause away from "opencode has a source-level circular-dependency
bug" and toward "the FreeBSD ports-built `bun` binary (section 6c) evaluates this
particular circular-import graph differently than upstream Linux/macOS Bun does" — e.g. a
build-flag or JavaScriptCore-configuration difference in the ports build, since Bun has no
officially supported FreeBSD binaries and the ports build is the only way to run it there.
This is **not yet proven** — it's the leading hypothesis given the evidence, not a
confirmed root cause.

**Next steps (resume here):**

1. From inside the jail (not off-FreeBSD — this doesn't reproduce anywhere else), get the
   exact version info of the ports-built `bun` (`bun --version`, and if available
   `bun --revision` for the underlying engine commit) and compare against the Linux
   `1.3.14`/`1.4.0` builds already tested clean here.
2. If the jail's `bun` is a *different* underlying revision than what's cached
   (`bun-1.3.14_3.pkg` from section 6d), consider whether that cached package should be
   rebuilt, or whether the crash is reproducible with a freshly-built one from a clean
   `/usr/ports` checkout.
3. Since this can't be reproduced outside the jail, the bisection has to happen live there:
   comment out chunks of `routes/instance/httpapi/server.ts`'s ~100+ imports (Account,
   Agent, Auth, BackgroundJob, Session*/Share* families, Storage, Worktree, etc.) directly
   in the jail and re-run 9a until the crash disappears, then narrow from there. This is
   the same bisection strategy already validated as sound (it's how `directories.ts` and
   `project.ts` were cleared individually) — it just needs to run where the crash actually
   happens.
4. If a FreeBSD-ports-bun-specific engine bug is confirmed (rather than anything fixable in
   opencode's own source), the right outcome is: (a) file it upstream against the `lang/bun`
   port and/or Bun itself with a minimal repro, and (b) document a workaround here (e.g. a
   specific bun version/build known to be safe, or restructuring the specific import cycle
   defensively in opencode even though it's not required on other platforms — belt-and-braces,
   since eliminating an unnecessary circular import is harmless even if it's not the "real"
   bug).
5. Once whichever fix/workaround is found, re-run 9a for real confirmation, then move to 9b.

### 9b. TUI sanity check **[unverified — blocked behind 9a-i; second thing to confirm once 9a is unblocked]**

```sh
cd ~/wip/opencode-src/packages/opencode
OTUI_ASSET_ROOT="$HOME/.otui-assets" bun run --conditions=browser src/index.ts
```

If the patch set in section 8 is correct, this should render the TUI instead of throwing
`Unsupported OpenTUI Node asset target: freebsd-x64` or a missing-asset error.

---

## 10. Persistent `opencode web` service — draft, untested

`/usr/local/etc/rc.d/opencode_web` (inside the jail):

```sh
#!/bin/sh
# PROVIDE: opencode_web
# REQUIRE: NETWORKING
# KEYWORD: shutdown

. /etc/rc.subr

name="opencode_web"
rcvar="opencode_web_enable"
pidfile="/var/run/${name}.pid"
command="/usr/sbin/daemon"
command_args="-P ${pidfile} -r -f /home/oc-user/.bun/bin/bun run /home/oc-user/wip/opencode-src/packages/opencode/src/index.ts web --port 4096"

load_rc_config $name
: ${opencode_web_enable:="NO"}

run_rc_command "$1"
```

```sh
chmod +x /usr/local/etc/rc.d/opencode_web
sysrc opencode_web_enable="YES"
service opencode_web start
```

This has not actually been run yet — treat as a starting point, not a confirmed recipe.
In particular, verify `daemon(8)`'s `-f` flag semantics and whether `OTUI_ASSET_ROOT`
needs to be threaded through explicitly (rc scripts don't inherit an interactive shell's
env) — likely needs `env OTUI_ASSET_ROOT=... command_args=...` wrapping if the web path
ever touches `@opentui/core` (probably doesn't, but double check).

---

## 11. Known rough edges

- **nullfs / `enforce_statfs`**: if you ever bind-mount host directories into this jail
  (e.g. to share `~/wip` instead of cloning fresh), you may need
  `sysrc jail_opencode-fbsd2_enforce_statfs="1"` or equivalent, and `nullfs` mounts can
  trip up tools that expect real device IDs. Not needed for the plain clone-inside-jail
  approach this guide uses, but worth knowing if you shortcut with mounts instead.
- **Bun's isolated linker layout**: don't assume flat `node_modules/@opentui` hoisting.
  Real package content lives under `node_modules/.bun/<pkg>+<version>+<hash>/...`; use
  `bun patch <pkg>` (which resolves via the lockfile) rather than hand-constructing paths.
- **`jexec` and shell profiles**: covered above in section 4, but worth repeating — always
  export `HOME`/`PATH` explicitly in one-shot `jexec -U oc-user ...` commands.

---

## 12. Teardown

```sh
# inside the jail, as root, stop services first
jexec opencode-fbsd2 service opencode_web stop 2>/dev/null

# from the host
service jail stop opencode-fbsd2
sysrc jail_list-="opencode-fbsd2"
rm -rf /jails/opencode-fbsd2

# remove the host-side IP alias
ifconfig em0 -alias 198.18.51.28
sysrc -x ifconfig_em0_alias0
```

---

## What to pick up on return

1. ~~Confirm section 6c-i's Option A fix...~~ **Done.** `bun 1.3.14` confirmed as a genuine
   native FreeBSD ELF binary (section 6c) after mounting `linprocfs`/`linsysfs` (section
   6c-i, Option A) and re-running `make install clean`. Root cause: the ports build's
   bootstrap Zig is a Linux binary needing a working `/proc/self/exe`.
2. ~~Do section 6d (cache the built `bun` package)...~~ **Done.** Cached at
   `/usr/local/pkg-cache/bun-1.3.14_3.pkg` on rep-laptop; `linprocfs`/`linsysfs` unmounted
   from `opencode-fbsd2` again, confirmed clean.
3. ~~Move on to section 7...~~ **Done.** Section 7a's real fix identified and applied:
   not a `bun patch` of the dependency, but a source edit to opencode's own
   `packages/core/src/filesystem/fff.bun.ts` (type-only import + `lazy()`-wrapped
   `require`). Confirmed this stops the eager-crash-on-unsupported-platform behavior.
   Section 7a rewritten to match.
4. **Blocked here — resume with this first:** section 9a's web-mode sanity check crashes
   in the jail with a TDZ-shaped reference error at `directories.ts:160`. Extensive
   isolated-repro work (see new section 9a-i) has ruled out the obvious candidates
   (isolated module loads, a synthetic same-shape circular-import repro, and — most
   tellingly — running the *actual* real `opencode-src` dependency graph's `web` command
   end-to-end on **both** Bun `1.3.14` and Bun `1.4.0` on Linux, neither of which crashes).
   Leading hypothesis: this is specific to the FreeBSD ports-built `bun` binary, not a
   source bug in opencode — but that's not confirmed yet, since nothing outside the jail
   can reproduce it to test against. **Next concrete action:** go back into
   `opencode-fbsd2` and bisect `routes/instance/httpapi/server.ts`'s ~100+ imports live,
   in the one place the crash actually happens. Full detail and a numbered next-steps list
   is in section 9a-i.
5. Run section 9b (TUI sanity check) — still blocked behind 9a-i, since 9a needs to pass
   first.
6. Confirm the `bun patch --commit` in section 8c actually persisted correctly
   (`cat patches/@opentui%2Fcore@0.4.5.patch` should exist and contain the 3-file diff;
   re-run `bun install` once to confirm the patch reapplies cleanly rather than being
   silently dropped).
7. If 9b works: wire up section 10 (rc.d service) for real and test a reboot.
8. If 9b fails: capture the exact error — most likely culprits are either the patch not
   applying cleanly to a different `@opentui/core` version than 0.4.5 (check `patch`'s
   output, or the `python3` fallback's printed warnings) or a stale `.so` (arch/ABI
   mismatch) at `$OTUI_ASSET_ROOT/@opentui/core-freebsd-x64/libopentui.so`.
9. Once both CLI/TUI and web mode are confirmed working end-to-end on this fresh jail,
   fold the validated steps back into a single canonical guide, retiring both
   `freebsd-opencode-jail.md` (Linuxulator dead-end) and this document's "unverified"
   caveats.
