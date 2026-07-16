# Gmail Inbox Cleanup: Filter Recommendations

Prepared for Jim Mercer. Based on an initial sample of ~100 recent inbox threads, then a follow-up pass covering the full current inbox (~200 threads) plus a look at what's already sitting in the existing vendor labels, to sanity-check priorities at scale.

**Limitation:** the Gmail connector I have access to can read your inbox and labels, but it can't create actual Filters (Settings > Filters and Blocked Addresses) — that API isn't exposed to me. So below are ready-to-paste filter recipes: the exact search string for the "Has the words" field, the label to apply, and whether to skip the inbox.

**Naming convention:** labels use a `category-detail` prefix (`hr-`, `helpdesk-`, `secops-`, etc.) so they sort together alphabetically in an IMAP folder list. This applies both to new labels and to a set of suggested renames for your existing ones, below.

## Label map: existing, renamed, and new

**Existing labels — recommend renaming for consistent sort order**

| Current name | Suggested rename | Why |
|---|---|---|
| `alienvault` | `secops-alienvault` | Security vendor feed — groups with your other `secops-` labels |
| `nessus` | `secops-nessus` | Same |
| `recorded-future` | `secops-recorded-future` | Same |
| `ice-aws` | `secops-ice-aws` | Same |
| `hacker1` | `secops-hackerone` | Same, and corrects the truncated vendor name |
| `github` | `secops-github` | Dev/ops repo notifications tied to your team |
| `jira` | `secops-jira` | Ticketing notifications |
| `carta` | `hr-carta` | Tracks employee stock/stock options — groups with `hr-hibob` as a compensation/benefits system |
| `secops-radware` | *(no change)* | Already fits the convention |
| `secops-misc` / `secops-offboarding` / `secops-domains` / `secops-maint` | *(no change)* | Already fit |

**Existing labels — decided**

| Current name | Action | Note |
|---|---|---|
| `info` | **Delete** | Empty, no longer needed. |
| `concerns` | **Rename to `wavelo-concerns`** | |
| `Archives.2020` | Leave untouched | Dated one-off archive, not a live workflow label. |

**Existing labels — still unclear category, not renaming without your input**

| Current name | Note |
|---|---|
| `misc` | Generic catch-all — could rename to `misc-general` for sort order, but not sure it's worth the churn unless you want it grouped near other `misc`-style labels. |

Note: the Gmail connector I have can create labels but can't delete or rename them — that's not exposed via this API. Both of the above need a quick manual step: Settings (gear icon) → **See all settings** → **Labels** → find `info` and click **remove**; find `concerns` and click **rename**, then type `wavelo-concerns`.

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

## What's already working (functionally fine, rename is cosmetic only)

`nessus`, `recorded-future`, `secops-radware`, `github`, `jira`, and `hacker1` are catching real volume — tens of messages each when you look past the inbox at everything they've already sorted. These filters are doing their job; the renames suggested above are purely for sort order, not because anything's broken.

## Priorities, revised after the larger sample

The bigger review changed the priority order from my first pass:

- **Helpdesk approval/resolved traffic and Perkopolis's triple-alias marketing mail are your two biggest noise sources** — bigger than the small sample suggested. These are the highest-value filters to set up first.
- **The AlienVault → LevelBlue rebrand gap is real but low-volume** (only a couple of messages total). Worth fixing for correctness, but it's a "whenever" fix, not urgent.
- A few moderate-volume senders only showed up in the larger review: CrowdStrike TAM notices, Exact Hosting invoices, and Tempo timesheet reminders. Added as their own recipes below.
- Infosec Institute's training/marketing mail is higher-volume (9+ in the sample) than first estimated — comparable to Docebo.

## Filter recipes

**1. Helpdesk — split into actionable vs. FYI (highest priority)**

Approval requests need your sign-off, so keep those visible:
```
from:(helpdesk@tucows.com OR it@tucows.freshservice.com) subject:"Request for Approval"
```
Action: Apply new label `helpdesk-approvals`. Don't skip inbox.

"Resolved" notices are pure FYI:
```
from:helpdesk@tucows.com subject:"Ticket Resolved"
```
Action: Apply new label `helpdesk-resolved`, Skip Inbox.

**2. Newsletters / webinar marketing (second-highest priority — largest pure-noise bucket)**

```
from:(customerservice@perkopolis.com OR update@grafana.com OR customereducation@docebo.com OR events@docebo.com OR contactus@docebo.com OR info@e.atlassian.com OR aws-marketing-email-replies@amazon.com OR noreply@meraki.com OR donotreply@notifications.visaacceptance.com OR experts@comms.levelblue.com)
```
Action: Apply new label `newsletters-marketing`, Skip Inbox.

Infosec Institute's training mail is high-volume enough to call out on its own:
```
from:training@e.infosecinstitute.com
```
Action: Apply new label `newsletters-training`, Skip Inbox.

Worth calling out: Perkopolis and Infosec Institute mail lands **three times each** — once per alias (`@tucows.com`, `@tucowsinc.com`, `@wavelo.com`). A filter can bundle it out of your inbox, but it won't stop the triplication. If you want that gone entirely, unsubscribing via the link in one or two of those emails (per alias) is the only real fix — a filter can't merge duplicate sends across different recipient addresses.

**3. Automated security reports**

```
from:no-reply@tucows.com subject:"Github Repository Monitoring Report"
```
Action: Apply new label `secops-github-monitoring`, Skip Inbox. (Leave "mark as read" off, so the label still shows unread counts for batch review.)

```
from:no-reply@securityiq-notifications.com
```
Action: Apply new label `secops-phishnotify`, Skip Inbox. This "Reported Emails Summary" goes to a 9-person distro and hits your inbox several times a day.

```
from:(TAM-Team-noreply@crowdstrike.com OR do-not-reply@crowdstrike.com)
```
Action: Apply new label `secops-crowdstrike`. Keep in inbox — these are TAM/support notices worth seeing as they come in, just worth a dedicated label.

**4. HR / HiBob notices**

```
from:no-reply@hibob.com
```
Action: Apply new label `hr-hibob`, Skip Inbox. FYI confirmations (time-off approvals, scheduled reports) — nothing actionable once sent.

**5. Auto-generated meeting notes**

```
from:gemini-notes@google.com
```
Action: Apply new label `meetings-notes`, Skip Inbox. One of these per standup/meeting — useful as reference, not something that needs inbox space.

**6. Billing / invoices**

```
from:help@exacthosting.com
```
Action: Apply new label `billing-exacthosting`, Skip Inbox.

**7. Internal tools**

```
from:no-reply@tempo.io
```
Action: Apply new label `tools-tempo`, Skip Inbox. Timesheet reminders — FYI only.

**8. Genuine mailing list — IT-ISAC AI SIG**

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

**2. Decide: fold into an existing label, or create a new one**

For each recurring/new sender you find, ask in order:

1. Does it clearly belong to one of the existing category prefixes below (same vendor family, same functional purpose)? If so, extend that label's filter query to include the new `from:` address rather than creating a new label. (Edit the filter: Settings → Filters and Blocked Addresses → find it → edit → add `OR from:new-address@example.com` to the existing "Has the words" query.)
2. If it doesn't fit an existing bucket, is the volume sustained (roughly 2+ per week, or a recognizable recurring pattern) rather than a one-off? If yes, create a new label with a `category-detail` name matching the taxonomy below, plus a new filter recipe (see format used throughout this doc: search query → label → skip-inbox y/n).
3. If it's low-volume and doesn't fit anywhere, it's fine to leave it unlabeled/in-inbox rather than inventing a label for a single sender — that's what the `misc` label (or manual handling) is for.
4. For anything actionable (needs a reply/decision, like helpdesk approvals or vendor ticket updates), default to **not** skipping the inbox even if it's from a vendor you'd otherwise auto-file — visibility matters more than tidiness for those.

**3. Current prefix taxonomy (keep new labels consistent with these)**

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

**4. After making changes**

- New filters: Settings → Filters and Blocked Addresses → Create a new filter (see "How to add these in Gmail" above).
- New labels: make sure "Show in IMAP" is checked (Settings → Labels) or Thunderbird won't show the folder.
- In Thunderbird: right-click the account → **Subscribe...** → **Refresh** to pick up new/renamed/removed folders. Remove any stale ghost folders left behind by a rename/delete.
- Optionally, jot a one-line note (sender + label + date) somewhere so the next pass has a changelog — this doc doesn't currently track that, but there's nothing stopping you from appending a running "Change log" section here if that'd help.
