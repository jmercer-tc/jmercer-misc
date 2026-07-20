# Patches for FreeBSD-native opencode/opentui support

Companion patch files for `../freebsd-opencode-jail-native-bun.md`. Each entry below notes
what the patch is for, where it applies, and its verification status.

## `opentui-monorepo-freebsd-target.patch`

**Status: [confirmed]** — this is the exact diff the user validated in their own local
`~/opentui` checkout (the standalone `opentui` monorepo, upstream source for
`@opentui/core` — a separate repo from opencode itself).

Applies to a clone of `https://github.com/sst/opentui.git`, in `packages/core/`:
adds `freebsd`/`x86_64-freebsd` as a recognized build target across `scripts/build.ts`,
`src/node-asset-target.ts`, and `src/zig/build.zig` (including accepting Zig 0.16.0, which
is what FreeBSD's `pkg install zig` currently provides, newer than the officially listed
0.15.2).

Apply with:

```sh
cd ~/opentui
git apply ~/wip/jmercer-misc/freebsd/patches/opentui-monorepo-freebsd-target.patch
```

Only needed if you're building `libopentui.so` from source (guide section 8b). If you're
reusing the already-built `.so` from the `.27` jail (section 8a), skip this.

## `opentui-core@0.4.5-freebsd-native-file-names.patch`

**Status: real diff, generated mechanically — not yet applied+run end-to-end inside a
jail.** This is *not* hand-written: it was produced by taking a byte-identical copy of the
published `@opentui/core@0.4.5` npm package, applying the same regex edit described in the
guide, and running `diff -u` against the untouched original. So the diff content itself is
exact, but "does this actually make the TUI render on FreeBSD" is still the open item in the
guide's "what to pick up on return" checklist.

Applies to opencode's **installed** copy of `@opentui/core@0.4.5` (three built/bundled JS
files — `node-assets.js`, `chunk-bun-t2myhmwd.js`, `chunk-node-q0cwyvm9.js`), adding
`freebsd: "libopentui.so"` next to the existing `darwin`/`linux`/`win32` entries in
`NATIVE_FILE_NAMES`. This is what lets `getNativeAssetDescriptor()` accept `process.platform
=== "freebsd"` instead of throwing, so the later `OTUI_ASSET_ROOT` early-return in
`resolveNativeLibraryPath()` is actually reached.

Apply with (from `opencode-src`, after `bun patch @opentui/core` has been run once to get an
editable copy staged):

```sh
cd ~/wip/opencode-src
bun patch @opentui/core
patch -p1 -d node_modules/@opentui/core < ~/wip/jmercer-misc/freebsd/patches/opentui-core@0.4.5-freebsd-native-file-names.patch
bun patch --commit 'node_modules/@opentui/core'
```

(`patch -p1 -d node_modules/@opentui/core` strips the `node_modules/@opentui/core/` prefix
that's baked into the diff paths — adjust `-p` if you apply it a different way.)

## `@ff-labs%2Ffff-bun@0.9.3-existing-reference.patch`

**Status: pre-existing, unrelated to the FreeBSD work.** This is a copy of a patch that
already lives in `opencode-src` at `patches/@ff-labs%2Ffff-bun@0.9.3.patch`, tracked there
via `bun patch --commit` before any of this FreeBSD effort started. It reworks how
`@ff-labs/fff-bun` resolves its native binary path (dropping a `createRequire`-based
package.json lookup in favor of a direct platform-keyed `require()`).

It's included here only as a **reference example** of this repo's `patchedDependencies`
convention — not as a verified FreeBSD-specific fix. The guide's mention of a "lazy-load"
pattern for `@ff-labs/fff-bun` on FreeBSD is a description of the general technique, not a
claim that this specific patch is that fix — if `@ff-labs/fff-bun` does turn out to need a
FreeBSD-specific change, it still needs to be derived and captured as its own patch file,
separate from this one.
