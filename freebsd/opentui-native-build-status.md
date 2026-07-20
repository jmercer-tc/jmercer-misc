# Native FreeBSD build of libopentui — status handoff

Last updated: 2026-07-19

## Goal

Get opencode running under a native FreeBSD Bun (not Linuxulator — that path is blocked by a confirmed `preadv2` hang, see `freebsd-opencode-jail.md`). The immediate sub-goal is getting OpenTUI's native Zig/C++ render library (`libopentui`) to build and actually load on FreeBSD, since no upstream prebuilt exists and opencode depends on it.

## Environment

- Host: `rep-laptop`, FreeBSD 15.1-RELEASE-p1, ABI `FreeBSD:15:amd64`
- Jail: `opencode-fbsd`, filesystem visible from host at `/jails/opencode-fbsd/...`
- Jail user: `oc-user` (uid/gid 20001), home `/home/oc-user`, shell `/usr/local/bin/bash`
- Repo: `/home/oc-user/opentui` inside the jail
- **Important gotcha**: `jexec -u oc-user opencode-fbsd <cmd>` fails with `jexec: oc-user: no such user`, even though the account genuinely exists (confirmed via `/etc/passwd`, `/etc/master.passwd`, `pw usershow`) and `pwd_mkdb -p /etc/master.passwd` does not fix it. **Use `jexec -U oc-user opencode-fbsd <cmd>` (capital U) instead — this works reliably.** Root cause of the lowercase `-u` failure specifically is still unconfirmed (possibly a login-class/`login.conf` issue) but not worth chasing further since `-U` is sufficient.
- Bun: real native FreeBSD build at `~/.bun/bin/bun` (v1.3.14). This is **not** a pkg/ports package — it came from oven-sh/bun's GitHub Release assets (`bun-freebsd-x64-baseline.zip`, "baseline" = no AVX2 dependency). `~/.bun/bin` is not on PATH by default in non-login jexec shells, so every invocation needs `export PATH=$HOME/.bun/bin:$PATH` first.
- Zig: `zig015` (0.15.2) installed via `pkg install zig015` — this is the version OpenTUI's `build.zig` actually targets. FreeBSD ports conveniently keep exact-version-pinned packages (`zig014`, `zig015`) alongside the rolling `zig` port (currently 0.16.0), which has an incompatible `Build`/`Compile` API. Installing `zig015` replaces the rolling `zig` at `/usr/local/bin/zig` due to a pkg conflict — that's expected and fine.
- Node: `node26` (26.4.0) installed via `pkg install node26` — this is an exact match for `NODE26_VERSION = "v26.4.0"` hardcoded in `packages/examples/scripts/node26.mjs`. Resolves as `/usr/local/bin/node`. Much cleaner than the Bun situation — a real ports package, no manual binary wrangling.

## What's been solved

1. **Sourcing a real FreeBSD Bun binary.** `pkg install bun` doesn't exist as a package at all; the fix was downloading the official GitHub Release asset directly.
2. **Getting the Zig/C++ core to actually compile for FreeBSD.** Forward-compat patching of the `0.16.0` toolchain against the `0.15.x`-era `build.zig` API was a dead end (cascading `std`/`Build` API mismatches). Installing the exact-pinned `zig015` package instead fixed this cleanly — `zig build` succeeds with exit code 0.
3. **Locating the actual build artifact.** `build.zig` has a "custom target" fallback path (triggered by passing a target string it doesn't recognize) that installs to a non-default location: `packages/core/src/zig/lib/x86_64-freebsd/libopentui.so`, not the default `zig-out`.
4. **Patching OpenTUI's TS-side platform allowlist.** `packages/core/src/node-asset-target.ts` hardcoded `"darwin" | "linux" | "win32"` in its `NodeAssetTarget` type and its `NATIVE_FILE_NAMES` map. Patched (via `sed`) to add `"freebsd"` to both. This file is shared between the Bun and Node runtime paths, so the patch covers both.
5. **Finding the asset-override mechanism.** `packages/core/src/platform/assets.ts` defines an `OTUI_ASSET_ROOT` env var and `resolveAssetRootPath(key)`, which both `runtime-assets.bun.ts` and `runtime-assets.node.ts` check *before* falling back to a hardcoded per-platform `import("@opentui/core-<platform>-<arch>")`. This lets us point directly at our locally-built `.so` without needing a real npm package or patching every per-platform branch. Asset laid out at `~/otui-assets/@opentui/core-freebsd-x64/libopentui.so`.
6. **Confirming the Bun-side blocker is a genuine, unrelated upstream Bun bug, not ours.** Running a minimal smoke test (`resolveRenderLib()` from `zig.ts`) under Bun fails with `bun:ffi dlopen() is not available in this build (TinyCC is disabled)`. Confirmed via web search that this exact error is independently reported on a completely different platform (GitHub issue Kilo-Org/kilocode #10541, Windows 11 ARM64), with no resolution or workaround documented — this is Bun's own FFI mechanism being broken in this build, not anything fixable on our end.
7. **Getting real dependencies installed.** `bun install` had never actually been run for this workspace before — we'd only been invoking scripts directly against source. Running `bun install` at the workspace root resolved everything correctly (`Checked 527 installs across 644 packages`), and confirmed `packages/core/node_modules/typescript` is a proper symlink to `typescript@5.9.3` (matching the `^5` pin in `package.json`).

## Current blocker (where we stopped)

Running the full package build (`bun run build` in `packages/core`, which is what would need to succeed before we can test the Node/`--experimental-ffi` path) now fails at a **different, new checkpoint**:

```
$ bun run build:native && bun run build:lib
$ bun scripts/build.ts --native
Building native prod binaries...
No matching supported target for native platform (x86_64-freebsd)
Error building native target: error.UnsupportedNativeTarget
error: the following build command failed with exit code 1:
.zig-cache/o/.../build /usr/local/bin/zig ... -Doptimize=ReleaseFast
Error: Zig build failed
```

This is a **different allowlist than the one we patched before**. `packages/core/scripts/build.ts` (the TS wrapper that invokes zig — separate from `build.zig` itself) has its own hardcoded `variants` array (only `darwin`/`linux`/`win32` combos, around lines 60-67), used at line 71 to find a `hostVariant` matching `process.platform`/`process.arch`. But the error message we got ("No matching supported target...", `error.UnsupportedNativeTarget`) does **not** match the wording of that check's own error (line 73: `Unsupported host platform for native builds: ...`) — so the actual failing check is most likely inside `build.zig` itself, on the Zig side. Working theory (not yet confirmed): `build.ts`'s `getZigTarget()` function has a `platformMap` that only remaps `darwin`/`win32`/`linux`, falling through to the raw platform string otherwise — so for `freebsd` it would produce a syntactically valid Zig target string like `x86_64-freebsd`. Unlike the deliberately-nonstandard string we used previously (which triggered `build.zig`'s permissive "custom target" fallback), this is a *real* recognized Zig target, which may be hitting a **stricter, separate validation path** in `build.zig` for native/host builds specifically.

**Immediate next step**: the command below was sent but its output was never received (we paused here to write this handoff). Run this first in the new session:

```
jexec -U oc-user opencode-fbsd grep -rniE "UnsupportedNativeTarget|No matching supported target" /home/oc-user/opentui/packages/core/src/zig/build.zig /home/oc-user/opentui/packages/core/scripts/build.ts
```

## A caution for the next session

Earlier in this session, a `find /home/oc-user/opentui -maxdepth 6 -path "*/node_modules/typescript/package.json"` came back empty, and that was wrongly taken as proof that no `typescript` package was installed anywhere. The real explanation was that `find` doesn't traverse into symlinked directories without `-L`, and Bun installs packages as symlinks into a global cache — so the check was structurally incapable of finding what it was looking for. `typescript@5.9.3` was correctly linked in via `bun install`. **Lesson: when a `find`/`grep` comes back empty in a way that seems to prove something significant, double-check it isn't a false negative from symlink traversal, quoting, or a wrong path assumption before building a diagnosis on top of it.**

## Working conventions for this investigation

- Prefer single, standalone commands (or a short handful) over large bundled shell scripts — easier to verify one result before deciding the next step, and avoids compounding a wrong assumption across several chained commands.
- Always use `jexec -U oc-user opencode-fbsd ...`, never `-u`.
- Any Bun invocation needs `export PATH=$HOME/.bun/bin:$PATH` first in that shell.
- The end goal once native-target building works: get `packages/core/dist` built, then run under `node26 --experimental-ffi` (via the `dev:node`/`run-node26.mjs` pattern already present in `packages/examples`) instead of Bun, to sidestep Bun's disabled-TinyCC `bun:ffi` limitation entirely.
