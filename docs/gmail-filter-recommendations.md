# Gmail Inbox Cleanup: Filter Recommendations

Prepared for Jim Mercer. Based on an initial sample of ~100 recent inbox threads, then a follow-up pass covering the full current inbox (~200 threads) plus a look at what's already sitting in the existing vendor labels, to sanity-check priorities at scale.

**Limitation:** the Gmail connector I have access to can read your inbox and labels, but it can't create actual Filters (Settings > Filters and Blocked Addresses) — that API isn't exposed to me. So below are ready-to-paste filter recipes: the exact search string for the "Has the words" field, the label to apply, and whether to skip the inbox.

**Naming convention:** labels use a `category-detail` prefix (`hr-`, `helpdesk-`, `secops-`, etc.) so they sort together alphabetically in an IMAP folder list. This applies both to new labels and to the renames already applied to your existing ones, below.

## Label map: existing, renamed, and new

**Existing labels — renamed for consistent sort order**

✅ All done and confirmed live:

| Old name | New name | Note |
|---|---|---|
| `alienvault` | `secops-alienvault` | |
| `nessus` | `secops-nessus` | |
| `recorded-future` | `secops-recorded-future` | |
| `ice-aws` | `secops-ice-aws` | |
| `hacker1` | `secops-hacker1` | Renamed to `secops-hacker1` rather than the `secops-hackerone` originally suggested — functionally identical, just keeps the truncated vendor name. No action needed unless you want it fully spelled out. |
| `github` | `secops-github` | |
| `carta` | `hr-carta` | |

`secops-radware`, `secops-misc`, `secops-offboarding`, `secops-domains`, and `secops-maint` already fit the convention and were left as-is.

**Existing labels — decided**

| Current name | Action | Status |
|---|---|---|
| `info` | Delete | ✅ Done — no longer appears in your label list. |
| `concerns` | Rename to `wavelo-concerns` | ✅ Done — confirmed live. |
| `Archives.2020` | Leave untouched | No change needed. |
| `jira` | Renamed to `secops-jira` (same label, in place) | Note: this ended up as a straight rename rather than the "start fresh, drop old mail" approach discussed earlier — the label kept its same ID, so historical `jira`-labeled mail is still sitting under `secops-jira` rather than being dropped. That's fine functionally; just flagging that the old mail wasn't actually cleared out if you still want to do that separately. |

**Existing labels — still unclear category, not renaming without your input**

| Current name | Note |
|---|---|
| `misc` | Generic catch-all — could rename to `misc-general` for sort order, but not sure it's worth the churn unless you want it grouped near other `misc`-style labels. |

Note: the Gmail connector I have can create labels but can't delete or rename them — that's not exposed via this API, so all of the renames and the `info` deletion above were done manually via Settings → Labels. The `misc` label above is the only one still pending that same manual step, if you decide to rename it.

*(The two `[Gmail]/Trash/...` entries in your label list aren't separate labels — they're just Gmail's mirror of trashed messages that happen to carry the `alienvault`/`secops-radware` label. Nothing to rename there.)*

**New labels proposed in this doc**

| Label | Skip inbox? | Purpose |
|---|---|---|
| `helpdesk-approvals` | No | Approval requests needing your sign-off |
| `helpdesk-resolved` | Yes | FYI-only ticket-resolved notices |
| `newsletters-marketing` | Yes | Perkopolis, Grafana, Docebo, Atlassian survey, AWS marketing, Meraki, Visa/Cybersource, LevelBlue marketing |
| `newsletters-training` | Yes | Infosec Institute training/poll mail |
| `secops-github-monitoring` | Yes | Daily GitHub repo monitoring report |
| `secops-phishnotify` | Yes | PhishNotify "Reported Emails Summary" |
| `secops-crowdstrike` | No | CrowdStrike TAM/support notices |
| `hr-hibob` | Yes | HiBob time-off/report notices |
| `meetings-notes` | Yes | Auto-generated Gemini meeting notes |
| `billing-exacthosting` | Yes | Exact Hosting invoices |
| `tools-tempo` | Yes | Tempo timesheet reminders |
| `lists-it-isac` | Optional | Genuine opt-in IT-ISAC AI SIG mailing list |
| `confluence-digest` | Yes | Weekly Confluence content digest |

## Update: "already working" labels turned out to be Thunderbird-dependent, not real Gmail filters

The note below originally said `nessus`, `recorded-future`, `secops-radware`, `github`, `jira`, and `hacker1` were "already working" — catching real volume with no filter needed. That was true only because Thunderbird had its own local message filters moving mail into those label-folders over IMAP, which (for Gmail) both applies the label and removes `INBOX` in one step. There was never an underlying Gmail Filter doing this server-side.

When those Thunderbird filters were removed, all four active ones stopped sorting simultaneously — Jira, GitHub, HackerOne, and Recorded Future mail all started piling back into the inbox unlabeled. See the new section 1 below for real Gmail-side recipes to replace them. (Nessus, ICE-AWS, and Radware weren't sending anything in the days right after the Thunderbird filters were removed, so it's not confirmed whether they're also affected — worth a spot-check, and likely the same underlying issue.)

## Priorities, revised after the larger sample

The bigger review changed the priority order from my first pass:

- **Helpdesk approval/resolved traffic and Perkopolis's triple-alias marketing mail are your two biggest noise sources** — bigger than the small sample suggested. These are the highest-value filters to set up first.
- **The AlienVault → LevelBlue rebrand gap is real but low-volume** (only a couple of messages total). Worth fixing for correctness, but it's a "whenever" fix, not urgent.
- A few moderate-volume senders only showed up in the larger review: CrowdStrike TAM notices, Exact Hosting invoices, and Tempo timesheet reminders. Added as their own recipes below.
- Infosec Institute's training/marketing mail is higher-volume (9+ in the sample) than first estimated — comparable to Docebo.

## Filter recipes

**1. Replace Thunderbird-only sorting with real Gmail filters (urgent — currently flooding the inbox)**

These four were never real Gmail Filters (see note above) — they need to be created from scratch, not just restored:

```
from:jira@wiki-tucows.atlassian.net
```
Action: Apply label `secops-jira` (new label — starting fresh rather than reusing/renaming the old `jira` label). Skip Inbox. Keep it as one label covering everything from Jira, including "Pending approval" mail — this is a separate system from the helpdesk approvals workflow below and doesn't need the same actionable/FYI split.

Since this is a clean start, don't check "Also apply filter to matching conversations" for this one — the existing `jira`-labeled mail is being deleted rather than migrated, so there's nothing old to backfill. Once `secops-jira` is confirmed working on new mail, delete the old `jira` label (and its messages, if desired) via Settings → Labels.

```
from:notifications@github.com
```
Action: Apply label `github` (or `secops-github`), Skip Inbox.

```
from:no-reply@hackerone.com
```
Action: Apply label `hacker1` (or `secops-hackerone`), Skip Inbox. Highest current volume of the four.

```
from:alert@recordedfuture.com
```
Action: Apply label `recorded-future` (or `secops-recorded-future`), Skip Inbox.

For each, check "Also apply filter to matching conversations" at creation time to backfill what's piled up since the Thunderbird filters were removed.

**2. Helpdesk — split into actionable vs. FYI**

✅ `helpdesk-approvals` is set up and working correctly (label applied, inbox visibility preserved as intended).

✅ `helpdesk-resolved` is set up and working correctly.

**3. Newsletters / webinar marketing (largest pure-noise bucket)**

```
from:(customerservice@perkopolis.com OR update@grafana.com OR customereducation@docebo.com OR events@docebo.com OR contactus@docebo.com OR info@e.atlassian.com OR aws-marketing-email-replies@amazon.com OR noreply@meraki.com OR donotreply@notifications.visaacceptance.com OR experts@comms.levelblue.com)
```
Action: Apply new label `newsletters-marketing`, Skip Inbox.

✅ `newsletters-training` (Infosec Institute) is set up and working correctly.

Worth calling out: Perkopolis and Infosec Institute mail lands **three times each** — once per alias (`@tucows.com`, `@tucowsinc.com`, `@wavelo.com`). A filter can bundle it out of your inbox, but it won't stop the triplication. If you want that gone entirely, unsubscribing via the link in one or two of those emails (per alias) is the only real fix — a filter can't merge duplicate sends across different recipient addresses.

**4. Automated security reports**

✅ `secops-github-monitoring` and ✅ `secops-phishnotify` are both set up and working correctly.

```
from:(TAM-Team-noreply@crowdstrike.com OR do-not-reply@crowdstrike.com)
```
Action: Apply new label `secops-crowdstrike`. Keep in inbox — these are TAM/support notices worth seeing as they come in, just worth a dedicated label.

**5. HR / HiBob notices**

```
from:no-reply@hibob.com
```
Action: Apply new label `hr-hibob`, Skip Inbox. FYI confirmations (time-off approvals, scheduled reports) — nothing actionable once sent.

**6. Auto-generated meeting notes**

```
from:gemini-notes@google.com
```
Action: Apply new label `meetings-notes`, Skip Inbox. One of these per standup/meeting — useful as reference, not something that needs inbox space.

**7. Billing / invoices**

```
from:help@exacthosting.com
```
Action: Apply new label `billing-exacthosting`, Skip Inbox.

**8. Internal tools**

```
from:no-reply@tempo.io
```
Action: Apply new label `tools-tempo`, Skip Inbox. Timesheet reminders — FYI only.

**9. Genuine mailing list — IT-ISAC AI SIG**

Not spam, a real opt-in working group. Label for easy reference but leave it in the inbox since meeting notes/slide decks tend to be time-sensitive:
```
from:it-isac.org
```
Action: Apply new label `lists-it-isac`. Skip inbox optional — your call.

## The AlienVault/LevelBlue fix (low priority, do whenever)

```
from:(@levelblue.com OR @comms.levelblue.com)
```
Action: Apply your `alienvault` label (or `secops-alienvault` if you've done the rename above). Keep `cybersupport@levelblue.com` ticket-update messages visible in the inbox (may need a response) — only the marketing mail from `experts@comms.levelblue.com` is safe to skip inbox.

## Notes for IMAP client use

Since you read mail through an IMAP client rather than Gmail's web UI day-to-day:

- Gmail exposes each label as an IMAP folder, but a label isn't an exclusive folder — a message keeps living in "All Mail" regardless of which labels it has. Nothing described above deletes or hides anything; it's all still searchable in All Mail as a fallback.
- "Skip Inbox" removes the `INBOX` label rather than moving the message anywhere, so the message will disappear from your IMAP "INBOX" folder but remain fully visible under the label's own folder and in All Mail.
- New labels have a "Show in IMAP" checkbox under Gmail Settings > Labels. Check that it's enabled for each new label above, or it won't appear as a folder in your client even though the filter is working correctly.
- Thunderbird doesn't pick up new/renamed/deleted labels automatically — after making changes in Gmail, right-click the account name → **Subscribe...** → **Refresh** to re-fetch the folder list. A rename or delete can occasionally leave a stale, empty "ghost" folder behind locally; unsubscribe/remove it if so.
- Your Thunderbird account has "Keep messages in all folders on this computer" unchecked and nothing selected for offline use, so it's running as a thin client — messages are fetched live rather than cached. This doesn't change the Subscribe/Refresh step above, but it does mean any new or ghost folders carry no local data, so there's nothing to clean up beyond removing the folder itself.

## How to add these in Gmail

Settings (gear icon) → **See all settings** → **Filters and Blocked Addresses** → **Create a new filter**. Paste the query into the search field, click "Create filter," then check "Apply the label" (creating a new one if needed) and "Skip the Inbox" where noted above.

## Re-running this triage yourself (methodology, for future reference)

Since your Thunderbird setup won't auto-sort anything new that doesn't already match a filter, unlabeled senders will keep accumulating in your inbox over time. You mentioned doing this on a weekly-ish cadence manually — here's the process that produced this doc, condensed so you (or a future assistant session) can repeat it without needing this specific conversation's history.

**1. Find what's new and unlabeled**

The fastest signal is: what's sitting in the inbox that isn't already covered by a filter? A few ways to spot it:

- Sort/scan the inbox by sender and look for repeat senders you don't recognize as already-labeled. Anything appearing 3+ times in a few weeks is worth a filter.
- In Gmail search, you can approximate "stuff my filters aren't catching" by searching `in:inbox` and eyeballing which threads *don't* already carry one of your category labels (Gmail's search UI doesn't do "has no label" cleanly, so this is manual scanning, not a single magic query).
- Check whether existing filters are still catching what they should: search `label:secops-nessus` (etc., for any label) and confirm the volume looks consistent with past patterns — a sudden drop can mean a vendor changed their sending address.
- It's also worth glancing at "All Mail" occasionally for anything that never even reaches "inbox" state but also never got labeled — e.g. mail that arrived filtered by Gmail's own spam heuristics rather than your filters.
- If a whole batch of previously-sorted senders suddenly starts flooding the inbox all at once (rather than one sender drifting), don't assume the Gmail filter broke — check whether the sorting was actually happening via a Thunderbird client-side filter instead. A Thunderbird "move to folder" rule on a Gmail IMAP account applies the label *and* removes it from Inbox in one step, which looks identical to a real Gmail Filter until you disable or lose the Thunderbird rule. Jira, GitHub, HackerOne, and Recorded Future all turned out to be running this way as of this review — worth confirming each label in the taxonomy below actually has a filter under Settings → Filters and Blocked Addresses, not just a Thunderbird rule.

**2. Decide: fold into an existing label, or create a new one**

For each recurring/new sender you find, ask in order:

1. Does it clearly belong to one of the existing category prefixes below (same vendor family, same functional purpose)? If so, extend that label's filter query to include the new `from:` address rather than creating a new label. (Edit the filter: Settings → Filters and Blocked Addresses → find it → edit → add `OR from:new-address@example.com` to the existing "Has the words" query.)
2. If it doesn't fit an existing bucket, is the volume sustained (roughly 2+ per week, or a recognizable recurring pattern) rather than a one-off? If yes, create a new label with a `category-detail` name matching the taxonomy below, plus a new filter recipe (see format used throughout this doc: search query → label → skip-inbox y/n).
3. If it's low-volume and doesn't fit anywhere, it's fine to leave it unlabeled/in-inbox rather than inventing a label for a single sender — that's what the `misc` label (or manual handling) is for.
4. For anything actionable (needs a reply/decision, like helpdesk approvals or vendor ticket updates), default to **not** skipping the inbox even if it's from a vendor you'd otherwise auto-file — visibility matters more than tidiness for those.

**3. Check for duplicate/multi-alias streams**

Some senders (vendor newsletters, HR/benefits platforms, security awareness training) will independently send the same message to more than one of your aliases (`@tucows.com`, `@tucowsinc.com`, `@wavelo.com`), because their subscriber list has you on file under multiple addresses. A filter can bundle these into one label, but it can't merge or de-duplicate the sends themselves — that only stops at the source.

To check for this on a given sender:

1. Search `from:sender-domain.com` and scan the `to:` field across results (or just look at recent threads with matching subjects/timestamps a few minutes apart) — repeated subjects landing within the same hour, addressed to different aliases, is the signature of a duplicate stream.
2. Open one copy of each duplicate and check the footer for an unsubscribe/preferences link — most marketing platforms (Klaviyo, Salesforce Marketing Cloud, etc.) generate a personalized link per recipient copy, and often state outright "This email was sent to: <address>" in the footer. That confirms unsubscribing is per-alias, not global.
3. Decide which alias to keep (usually your current primary/active one) and unsubscribe the others by opening the specific duplicate copy addressed to the alias you want to drop and using its unsubscribe link — not the copy you're keeping.
4. Watch for cases where a duplicate isn't actually a personal alias at all — e.g. a copy addressed to a shared/team distro (a greeting naming someone else, or an address like `secops@` rather than `jmercer@`) may be a legacy subscription tied to that shared mailbox rather than to you personally. Don't unsubscribe those unilaterally; flag it for whoever administers that address.

Perkopolis and Infosec Institute both had this pattern as of this review (resolved via manual unsubscribes rather than a filter fix), so treat them as already clean going forward — but it's worth spot-checking any new high-volume sender for the same issue before assuming a single filter has fully captured it.

**4. Current prefix taxonomy (keep new labels consistent with these)**

| Prefix | Used for |
|---|---|
| `secops-` | Security vendor feeds, tickets, monitoring reports (AlienVault/LevelBlue, Nessus, Recorded Future, ICE-AWS, HackerOne, GitHub, Jira, PhishNotify, CrowdStrike, misc/offboarding/domains/maint) |
| `hr-` | HR/compensation systems (HiBob, Carta) |
| `helpdesk-` | Internal IT helpdesk ticket traffic, split by actionable (`-approvals`) vs. FYI (`-resolved`) |
| `newsletters-` | Marketing/webinar/training mail with no action needed (`-marketing`, `-training`) |
| `meetings-` | Auto-generated meeting artifacts (Gemini notes) |
| `billing-` | Vendor invoices |
| `tools-` | Internal tool notifications (Tempo) |
| `lists-` | Genuine opt-in mailing lists/working groups (IT-ISAC) |
| `wavelo-` | Internal Wavelo-specific labels (e.g. `wavelo-concerns`) |
| `confluence-` | Confluence digest-style notifications |

When in doubt, prefer reusing a prefix over inventing a new one — the whole point of the convention is that IMAP folders in Thunderbird sort together by category, and a proliferation of one-off prefixes defeats that.

**5. After making changes**

- New filters: Settings → Filters and Blocked Addresses → Create a new filter (see "How to add these in Gmail" above).
- New labels: make sure "Show in IMAP" is checked (Settings → Labels) or Thunderbird won't show the folder.
- In Thunderbird: right-click the account → **Subscribe...** → **Refresh** to pick up new/renamed/removed folders. Remove any stale ghost folders left behind by a rename/delete.
- Optionally, jot a one-line note (sender + label + date) somewhere so the next pass has a changelog — this doc doesn't currently track that, but there's nothing stopping you from appending a running "Change log" section here if that'd help.
