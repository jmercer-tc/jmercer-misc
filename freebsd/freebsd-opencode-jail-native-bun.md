# Fresh FreeBSD Jail for opencode — Native Bun, No Linuxulator

Start-to-finish build of a **brand-new** jail at **198.18.51.28/32** to run opencode
(CLI/TUI and web mode) using native FreeBSD Bun — superseding the old Linuxulator-based
draft (`freebsd-opencode-jail.md`, jail `.27`, which hit a `preadv2 not implemented` dead
end under Linuxulator).

This document consolidates everything validated in the `.27` jail so far:
native Bun works fine, the TUI's native `@opentui/core` renderer needs a small patch set
plus a custom-built FreeBSD `.so`, and one unrelated package (`@ff-labs/fff-bun`) needs a
lazy-load patch to avoid an eager top-level crash on FreeBSD.

Status legend used throughout:
- **[confirmed]** — actually run and observed working on the `.27` jail.
- **[carried over]** — jail-scaffolding steps reused verbatim from the old guide; mechanically
  the same regardless of Linuxulator, just re-parameterized for the new IP/name.
- **[unverified]** — assembled from source-code inspection (byte-identical npm package + the
  user's own git diff), not yet run end-to-end. Flagged inline so you know what to double-check
  first.

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

Use `bsdinstall jail` (or your preferred jail-creation flow) to lay down a base FreeBSD
userland at e.g. `/jails/opencode-fbsd2`. Do **not** install `linux_base-*`,
`linux-c7`, or enable `linux` module loading — none of that is needed. Native Bun runs
directly on FreeBSD.

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

Enable and start it:

```sh
sysrc jail_list+="opencode-fbsd2"
service jail start opencode-fbsd2
jls
```

You should see `opencode-fbsd2` listed with IP `198.18.51.28`.

> Reminder for later teardown: removing a jail from autostart is `sysrc jail_list-="opencode-fbsd2"`,
> not editing the string by hand — avoids stray whitespace/duplicate entries in `rc.conf`.

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

```sh
jexec opencode-fbsd2 pw useradd oc-user -m -s /bin/sh -G wheel
jexec opencode-fbsd2 passwd oc-user
```

> **Critical caveat, confirmed the hard way on `.27`:** `jexec` does **not** source shell
> profiles or rc files, even for a login-shell user. Every command you run via
> `jexec -U oc-user opencode-fbsd2 ...` must explicitly export `HOME` and `PATH` itself —
> don't assume `~/.bun/bin` or anything else from `.profile`/`.bashrc` is on `PATH`. Every
> command block below that runs as `oc-user` starts with:
> ```sh
> export HOME=/home/oc-user
> export PATH="$HOME/.bun/bin:$PATH"
> ```

---

## 5. SSH access (optional but convenient) **[carried over]**

```sh
jexec opencode-fbsd2 sysrc sshd_enable="YES"
jexec opencode-fbsd2 service sshd start
```

Then from the host: `ssh oc-user@198.18.51.28`.

---

## 6. Install native Bun **[confirmed on .27, same procedure]**

As `oc-user` inside the jail (via `jexec -U oc-user opencode-fbsd2 sh` or over SSH):

```sh
curl -fsSL https://bun.sh/install | bash
```

This lands at `~/.bun/bin/bun`. Confirmed working version during `.27` testing: **Bun 1.3.14**.
No Linuxulator, no compat shims — it's a real FreeBSD build of Bun.

Verify:

```sh
export HOME=/home/oc-user
export PATH="$HOME/.bun/bin:$PATH"
bun --version
```

---

## 7. Clone and build opencode **[confirmed for install; TUI render unverified]**

```sh
export HOME=/home/oc-user
export PATH="$HOME/.bun/bin:$PATH"
mkdir -p ~/wip
cd ~/wip
git clone https://github.com/anomalyco/opencode.git opencode-src
cd opencode-src
```

### 7a. Patch `@ff-labs/fff-bun` (unrelated native-addon crash)

This package does an eager top-level `require()` of a prebuilt native addon that has no
FreeBSD build, crashing at import time before opencode even starts. Fix: lazy-load it,
matching the pattern already used elsewhere in this codebase for optional native addons:

```js
// before (crashes eagerly on unsupported platforms)
const native = require("./native-addon.node")

// after (lazy, matches this repo's existing lazy() pattern)
const native = lazy(() => {
  try {
    return require("./native-addon.node")
  } catch {
    return undefined
  }
})
```

Apply as a tracked Bun patch so `bun install` doesn't wipe it out:

```sh
bun patch @ff-labs/fff-bun
# edit the file bun patch tells you to edit, applying the lazy-load change above
bun patch --commit 'node_modules/@ff-labs/fff-bun'
```

This repo already has one patch of this kind tracked at
`patches/@ff-labs%2Ffff-bun@0.9.3.patch` — use it as your reference diff if you're
re-deriving this on a fresh clone rather than reusing patch files from the `.27` jail.

### 7b. Install dependencies

```sh
bun install
```

---

## 8. Build native FreeBSD `@opentui/core` **[unverified end-to-end — see checklist]**

opencode's TUI depends on `@opentui/core`, a Zig-native terminal rendering engine. The
published npm package (`@opentui/core@0.4.5`, confirmed pinned exactly in this repo's
`bun.lock`) only ships prebuilt binaries for `darwin`/`linux`/`win32`. Two things are needed:
a FreeBSD build of the native library, and a small patch so the JS loader accepts
`"freebsd"` as a valid platform.

### 8a. Shortcut — reuse the already-built `.so` from the `.27` jail

If the `.27` jail still exists, the fastest path is to just copy its already-built
`libopentui.so` instead of rebuilding from scratch:

```sh
# from the host
scp oc-user@198.18.51.27:/home/oc-user/.otui-assets/@opentui/core-freebsd-x64/libopentui.so /tmp/
scp /tmp/libopentui.so oc-user@198.18.51.28:/tmp/
```

Then on `.28`:

```sh
mkdir -p ~/.otui-assets/@opentui/core-freebsd-x64
mv /tmp/libopentui.so ~/.otui-assets/@opentui/core-freebsd-x64/
```

Skip to 8c if you do this.

### 8b. Building from source instead

Clone the standalone `opentui` monorepo (separate from opencode itself — it's the
upstream source for `@opentui/core`) and apply the three-file diff already validated
against a fresh checkout:

```sh
git clone https://github.com/sst/opentui.git ~/opentui
cd ~/opentui
```

Apply this diff (already hand-verified working, reproduced here in full):

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

Apply the same `NATIVE_FILE_NAMES`/platform-union edit to each of the three files listed
above — each occurrence looks like:

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

A small `python3` script does all three files in one shot:

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

```sh
export HOME=/home/oc-user
export PATH="$HOME/.bun/bin:$PATH"
export OTUI_ASSET_ROOT="$HOME/.otui-assets"
cd ~/wip/opencode-src
```

### 9a. Web mode sanity check **[expected to work — same as native Bun install, no @opentui/core render path involved]**

```sh
cd packages/opencode
bun run src/index.ts web --port 4096 &
curl -s -D - http://198.18.51.28:4096/ -o /dev/null
```

(Note: opencode's web server sends `server: cloudflare` / `cf-ray` response headers
regardless of actual network path — this is opencode's own deliberate behavior, not a sign
your traffic is going anywhere external. Don't be alarmed by it.)

### 9b. TUI sanity check **[unverified — first thing to confirm on return]**

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

1. Run section 9b (TUI sanity check) — this is the single biggest unverified piece.
2. Confirm the `bun patch --commit` in section 8c actually persisted correctly
   (`cat patches/@opentui%2Fcore@0.4.5.patch` should exist and contain the 3-file diff;
   re-run `bun install` once to confirm the patch reapplies cleanly rather than being
   silently dropped).
3. If 9b works: wire up section 10 (rc.d service) for real and test a reboot.
4. If 9b fails: capture the exact error — most likely culprits are either the
   `python3` regex not matching all three files cleanly (check its printed warnings) or
   a stale `.so` (arch/ABI mismatch) at `$OTUI_ASSET_ROOT/@opentui/core-freebsd-x64/libopentui.so`.
5. Once both CLI/TUI and web mode are confirmed working end-to-end on this fresh jail,
   fold the validated steps back into a single canonical guide, retiring both
   `freebsd-opencode-jail.md` (Linuxulator dead-end) and this document's "unverified"
   caveats.
