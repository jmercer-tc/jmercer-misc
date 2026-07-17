# Using OpenCode Zen with opencode

[OpenCode Zen](https://opencode.ai/docs/zen/) is the opencode team's own
hosted model gateway — a single provider/endpoint that gives you access to a
curated set of models (Anthropic, OpenAI, and others) through one API key and
one bill, without having to sign up with each model vendor separately. This
doc covers the whole flow end to end, starting from having no account at all,
through to using Zen as the model provider for opencode running in the
FreeBSD jail set up in `freebsd-opencode-jail.md`.

## 1. Create a Zen account

1. Go to **https://opencode.ai/auth** in a browser.
2. Sign in (this creates your account on first login — there's no separate
   "sign up" step).
3. Add billing details. Zen is pay-per-token, not a flat subscription — see
   [Pricing](#pricing--billing) below for how balance/auto-reload works.
4. Once billing is attached, generate an API key from the Zen dashboard and
   copy it somewhere safe. This key is what opencode will use to
   authenticate, not your login credentials.

## 2. Connect opencode to Zen

From inside an opencode CLI/TUI session (this works the same whether
opencode is running locally or inside the FreeBSD jail):

```
/connect
```

This opens the provider picker. Select **OpenCode Zen** from the list, then
paste the API key you generated in step 1 when prompted.

Once connected, credentials are written to:

```
~/.local/share/opencode/auth.json
```

(inside the jail, that's `/home/opencode/.local/share/opencode/auth.json`
for the `opencode` service user). You only need to run `/connect` once per
user/environment — it persists across sessions.

## 3. Pick a model

Still inside the TUI:

```
/models
```

This lists the models available through your connected providers, including
everything Zen currently offers. Select one to use for the current session.

Model identifiers under Zen follow the pattern `opencode/<model-id>`, e.g.:

```
opencode/gpt-5.5
opencode/claude-sonnet-5
```

`/models` is the easiest way to see the live, current list — Zen's catalog
changes over time, so treat any specific model name here as an example
rather than a fixed list.

## 4. Set a default model (optional)

To avoid picking a model every session, set one in opencode's config file.
Global config lives at:

```
~/.config/opencode/opencode.json
```

or you can drop a project-local `opencode.json` in a repo to override it
per-project. Relevant keys:

```json
{
  "model": "opencode/claude-sonnet-5",
  "small_model": "opencode/gpt-5-mini"
}
```

- `model` — the default model for normal use.
- `small_model` — an optional cheaper/faster model opencode uses internally
  for lightweight tasks (e.g. summarization), separate from your main model.

Both follow the same `<provider>/<model-id>` format; for Zen that provider
prefix is always `opencode`.

## Pricing / billing

- Zen is **pay-per-token** — you're billed per model based on that model's
  own per-token rate, not a flat opencode markup rate. Check the live pricing
  table on the Zen docs page for current per-model rates, since these track
  underlying vendor pricing and change over time.
- Billing runs on a **balance + auto-reload** model: your account holds a
  balance, and when it drops below **$5** it automatically reloads (default
  reload amount is **$20**, configurable in the dashboard).
- You can also set a **monthly usage limit** as a spending cap.
- **Bring-your-own-key** is supported as an alternative if you'd rather use
  your own Anthropic/OpenAI/etc. keys directly instead of routing spend
  through Zen — useful if you already have committed spend or enterprise
  pricing with a specific vendor.

## Privacy

Per opencode's Zen docs: prompts/completions routed through Zen are not used
for training, and are retained only transiently for operational purposes
(abuse prevention, debugging) rather than stored long-term. If this matters
for your use case (e.g. anything touching Proxmox/infra credentials or
internal VM configs), check the current privacy section on the Zen docs page
directly before relying on this, since retention/training policies are the
kind of thing that can change without much fanfare.

## For teams

Zen supports multi-seat accounts with **Admin** and **Member** roles, so a
team can share one Zen account/billing relationship while individual members
each connect with their own key. Not relevant for a single-user jail setup
like the one in `freebsd-opencode-jail.md`, but worth knowing if this ever
gets shared across more than one person.

## Using this with the FreeBSD jail setup

If you're running opencode inside the jail described in
`freebsd-opencode-jail.md`, do the `/connect` step above as the `opencode`
user inside the jail (either over the CLI login from step 10 of that guide,
or from a web-mode session via the SSH tunnel). The `auth.json` and
`opencode.json` files it writes live under `/home/opencode/...` inside the
jail's filesystem, so they persist across jail restarts along with
everything else in `/jails/opencode`.
