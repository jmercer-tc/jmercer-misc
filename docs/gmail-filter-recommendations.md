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
| `carta` | `hr-stocks` | Renamed a second time, from `hr-carta` — Jim's call to frame it as the equity/stock-plan bucket rather than a single-vendor label, since Siebert mail (stock-plan-related) is being folded in below. |

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

*(The two `[Gmail]/Trash/...` entries in your label list aren't separate labels — they're just Gmail's mirror of trashed messages that happen to carry the `alienvault`/`secops-radware` label. Update: these have since cleared on their own — they no longer appear in the label list at all, consistent with Trash being emptied or those messages no longer qualifying for the overlap.)*

**New labels proposed in this doc**

| Label | Skip inbox? | Purpose |
|---|---|---|
| `helpdesk-approvals` | No | Approval requests needing your sign-off |
| `helpdesk-resolved` | Yes | FYI-only ticket-resolved notices |
| `newsletters-marketing` | Yes | Perkopolis, Grafana, Docebo, Atlassian survey, AWS marketing, Visa/Cybersource, LevelBlue marketing |
| `newsletters-training` | Yes | Infosec Institute training/poll mail |
| `secops-github-monitoring` | Yes | Daily GitHub repo monitoring report |
| `secops-phishnotify` | Yes | PhishNotify "Reported Emails Summary" |
| `secops-crowdstrike` | No | CrowdStrike TAM/support notices |
| `hr-hibob` | Yes | HiBob time-off/report notices |
| `meetings-notes` | Yes | Auto-generated Gemini meeting notes |
| `misc-invoices` | Yes | Billing/invoice mail generally, starting with Exact Hosting — a catchall rather than a per-vendor label, so future invoice senders can be folded in here too |
| `hr-tempo` | Yes | Tempo timesheet reminders |
| `lists-it-isac` | Optional | Genuine opt-in IT-ISAC AI SIG mailing list |
| `confluence-digest` | Yes | Weekly Confluence content digest |
| `secops-netops` | Yes | Meraki network device notifications (moved out of `newsletters-marketing` — networking gear, not marketing) |
| `incidentio-alerts` | Yes | incident.io platform notifications — its own dedicated label since Jim expects this system to grow in importance |
| `meetings-invites` | Yes | Google Calendar invitations, updates, and cancellations from any organizer — the single biggest volume source found across the whole review |

## Update: "already working" labels turned out to be Thunderbird-dependent, not real Gmail filters

The note below originally said `nessus`, `recorded-future`, `secops-radware`, `github`, `jira`, and `hacker1` were "already working" — catching real volume with no filter needed. That was true only because Thunderbird had its own local message filters moving mail into those label-folders over IMAP, which (for Gmail) both applies the label and removes `INBOX` in one step. There was never an underlying Gmail Filter doing this server-side.

When those Thunderbird filters were removed, all four active ones stopped sorting simultaneously — Jira, GitHub, HackerOne, and Recorded Future mail all started piling back into the inbox unlabeled. See the new section 1 below for real Gmail-side recipes to replace them. (Nessus, ICE-AWS, and Radware weren't sending anything in the days right after the Thunderbird filters were removed, so it wasn't confirmed at the time whether they were also affected.)

**Update from the second pass:** confirmed — Nessus is affected too. Sampled the most recent Nessus scan-report mail directly and every message carries only `["UNREAD","INBOX"]`; the `secops-nessus` label is never applied despite the label existing. Same root cause, same fix. Added as a fifth recipe in section 1 below.

## Priorities, revised after the larger sample

The bigger review changed the priority order from my first pass:

- **Helpdesk approval/resolved traffic and Perkopolis's triple-alias marketing mail are your two biggest noise sources** — bigger than the small sample suggested. These are the highest-value filters to set up first.
- **The AlienVault → LevelBlue rebrand gap is real but low-volume** (only a couple of messages total). Worth fixing for correctness, but it's a "whenever" fix, not urgent.
- A few moderate-volume senders only showed up in the larger review: CrowdStrike TAM notices, Exact Hosting invoices, and Tempo timesheet reminders. Added as their own recipes below (Exact Hosting now folded into a general `misc-invoices` catchall rather than its own vendor-specific label).
- Infosec Institute's training/marketing mail is higher-volume (9+ in the sample) than first estimated — comparable to Docebo.

## Filter recipes

**1. Replace Thunderbird-only sorting with real Gmail filters (urgent — currently flooding the inbox)**

✅ Four confirmed live and working correctly — re-checked by sampling recent mail from each sender and verifying the label is applied with `INBOX` absent:

- ✅ `secops-jira` (from:jira@wiki-tucows.atlassian.net) — skipping inbox as intended.
- ✅ `secops-github` (from:notifications@github.com) — skipping inbox as intended.
- ✅ `secops-hacker1` (from:no-reply@hackerone.com) — skipping inbox as intended.
- ✅ `secops-recorded-future` (from:alert@recordedfuture.com) — skipping inbox as intended.

❌ **`secops-nessus` is not** — this is the biggest single gap found in the second-pass review. The label exists and was renamed, but there's no real Gmail filter behind it; it was riding on the same now-removed Thunderbird rule as the other four. Every sampled Nessus scan-report message in the inbox carries only `UNREAD`/`INBOX`, no label at all. This looked like high volume in the sample (Gmail's own estimate capped out at "201" for `from:nessus@tucows.com in:inbox`, so treat that as "a lot," not literal). Recipe:

```
from:nessus@tucows.com
```
Action: Apply label `secops-nessus`, Skip Inbox — matching the treatment of the other four in this section.

For reference, these were the original recipes for the other four:

```
from:jira@wiki-tucows.atlassian.net
```
Action: Apply label `secops-jira` (new label — starting fresh rather than reusing/renaming the old `jira` label). Skip Inbox. Keep it as one label covering everything from Jira, including "Pending approval" mail — this is a separate system from the helpdesk approvals workflow below and doesn't need the same actionable/FYI split.

```
from:notifications@github.com
```
Action: Apply label `secops-github`, Skip Inbox.

```
from:no-reply@hackerone.com
```
Action: Apply label `secops-hacker1`, Skip Inbox. Highest current volume of the four.

```
from:alert@recordedfuture.com
```
Action: Apply label `secops-recorded-future`, Skip Inbox.

**2. Helpdesk — split into actionable vs. FYI**

✅ `helpdesk-approvals` is set up and working correctly (label applied, inbox visibility preserved as intended).

✅ `helpdesk-resolved` is set up and working correctly.

**3. Newsletters / webinar marketing (largest pure-noise bucket)**

✅ `newsletters-marketing` is set up and working correctly — confirmed across ~20 sampled messages (Perkopolis, Grafana, Docebo, Atlassian, AWS marketing, Visa/Cybersource, LevelBlue), all correctly labeled with inbox skipped. Recipe for reference:

```
from:(customerservice@perkopolis.com OR update@grafana.com OR customereducation@docebo.com OR events@docebo.com OR contactus@docebo.com OR info@e.atlassian.com OR aws-marketing-email-replies@amazon.com OR donotreply@notifications.visaacceptance.com OR experts@comms.levelblue.com)
```
Note: Meraki has been pulled out of this filter — see `secops-netops` below. It's networking gear, not really "marketing," and it makes more sense grouped with other network/security device feeds.

✅ `newsletters-training` (Infosec Institute) is set up and working correctly.

Worth calling out: Perkopolis and Infosec Institute mail lands **three times each** — once per alias (`@tucows.com`, `@tucowsinc.com`, `@wavelo.com`). A filter can bundle it out of your inbox, but it won't stop the triplication. If you want that gone entirely, unsubscribing via the link in one or two of those emails (per alias) is the only real fix — a filter can't merge duplicate sends across different recipient addresses.

**4. Automated security reports**

✅ `secops-github-monitoring` and ✅ `secops-phishnotify` are both set up and working correctly.

✅ `secops-crowdstrike` is set up and working correctly — confirmed across 15 sampled messages, all labeled with inbox skipped. Note: this overrides the original recipe below, which had recommended keeping these in the inbox — Jim's call was to route them straight to the label folder instead, so skip inbox is the confirmed/intended behavior going forward. Recipe (updated):

```
from:(TAM-Team-noreply@crowdstrike.com OR do-not-reply@crowdstrike.com)
```
Action: Apply new label `secops-crowdstrike`, Skip Inbox.

**4a. Meraki network device notifications — own label, moved out of newsletters-marketing**

Jim's call: Meraki mail (both known sending addresses — the original `noreply@meraki.com` already caught by `newsletters-marketing`, plus the second address `support-noreply@meraki.com` found unlabeled in the second-pass review) should live under a dedicated `secops-netops` label rather than under the marketing catchall.

```
from:(noreply@meraki.com OR support-noreply@meraki.com)
```
Action: create new label `secops-netops`, Skip Inbox. Remove `noreply@meraki.com` from the `newsletters-marketing` filter's query if it's still there live (see the updated recipe in section 3 above).

**5. HR / HiBob notices**

✅ `hr-hibob` is set up and working correctly — confirmed across 15 sampled messages, all labeled with inbox skipped as intended. (A few offboarding-notice messages also carry `secops-offboarding` at the same time — that overlap looks intentional/harmless, not a problem.) Recipe for reference:

```
from:no-reply@hibob.com
```
Action: Apply new label `hr-hibob`, Skip Inbox. FYI confirmations (time-off approvals, scheduled reports) — nothing actionable once sent.

**5a. HR / Stocks — Carta (renamed) + Siebert (new fold-in)**

`hr-stocks` (renamed from `hr-carta`, see label map above) already has a working filter for Carta mail. Folding Siebert's stock-plan mail in as a second sender on the same label rather than giving it its own, since it's the same functional bucket:

```
from:(carta.com OR no-reply@siebert.com)
```
Action: add `OR from:no-reply@siebert.com` to the existing `hr-stocks` filter's query. Skip Inbox, matching Carta's existing behavior. (The exact Carta sending address wasn't independently re-verified this pass — swap in whatever address the current live filter actually uses if it differs from `carta.com`.)

**6. Auto-generated meeting notes**

✅ `meetings-notes` is set up and working correctly — confirmed across 15 sampled messages, all labeled with inbox skipped as intended. Recipe for reference:

```
from:gemini-notes@google.com
```
Action: Apply new label `meetings-notes`, Skip Inbox. One of these per standup/meeting — useful as reference, not something that needs inbox space.

**6a. Calendar invites, updates, and cancellations — biggest single volume source in the whole inbox**

Every Google Calendar invitation, update, and cancellation email — from any organizer, internal or external — currently lands straight in the inbox with no filter touching it at all. This isn't from one sender like everything else in this doc; it's dozens of different colleagues and vendors (Michael Sahai's recurring 1:1s, CrowdStrike/Teleport/Radware demos, Town Halls, incident.io incident-response invites, All-Hands, etc.), all sharing the same Gmail subject conventions: `Invitation:`, `Updated invitation:`, `Updated invitation with note:`, `Canceled event:`, `Canceled event with note:` (and the `Cancelled` UK spelling variant Google also uses). Confirmed via a subject-based search that this pattern alone accounts for the largest chunk of inbox volume found in this whole review — Gmail's estimate capped at "201."

```
subject:("Invitation:" OR "Updated invitation:" OR "Canceled event:" OR "Cancelled event:")
```
Action: apply new label `meetings-invites`, Skip Inbox. Since Gmail's search treats the quoted phrases as word-matches rather than exact substrings, this query also catches the "with note" and recurring-series variants (confirmed against live results) without needing extra clauses. Per Jim's stated preference this pass: pull these out of the inbox entirely and rely on Google Calendar itself (not the inbox) for tracking upcoming meetings and RSVPs — the label is there to keep the raw notification emails searchable/reference-able, not for active monitoring.

**7. Billing / invoices**

Made this a general catchall label rather than a per-vendor one, since billing/invoice mail tends to come from a handful of small vendors rather than one:

```
from:help@exacthosting.com
```
Action: Apply new label `misc-invoices`, Skip Inbox. When another billing/invoice sender shows up later, add it to this same filter's query (`OR from:new-vendor@example.com`) rather than creating a new label.

**8. Timesheets**

```
from:no-reply@tempo.io
```
Action: Apply new label `hr-tempo` (moved from the originally-suggested `tools-tempo` — timesheets fit better under the `hr-` prefix alongside HiBob/Carta), Skip Inbox. Timesheet reminders — FYI only.

**9. Genuine mailing list — IT-ISAC AI SIG**

Not spam, a real opt-in working group. Label for easy reference but leave it in the inbox since meeting notes/slide decks tend to be time-sensitive:
```
from:it-isac.org
```
Action: Apply new label `lists-it-isac`. Skip inbox optional — your call.

## Second pass: new unfiltered senders found in the last ~200 inbox threads

You asked for a review of what's still piling up unfiltered. Went through the full current inbox (~200 threads, 4 pages of 50) and cross-checked every repeat sender against the existing label/filter set. Six real gaps, in priority order by volume/impact. (Nessus is covered above in section 1, since it's the same Thunderbird-dependency root cause as Jira/GitHub/HackerOne/Recorded Future — this list is everything else.)

**10. Helpdesk ticket-lifecycle notices — existing filter is too narrow**

`helpdesk-resolved` is working, but it only matches the "Ticket Resolved" subject line. Three sibling notification types from the same sender are unlabeled and sitting in the inbox: "Ticket Closed - ...", "Ticket Received - ...", and "Ticket Approved/Rejected - [#SR-...] ...". This isn't a broken filter, just a scope gap — the sender sends several distinct lifecycle notices and only one was ever covered.

**Decided:** everything skips the inbox, split across two labels so the separate message counts stay visible for monitoring:

```
from:helpdesk@tucows.com (subject:"Ticket Closed" OR subject:"Ticket Resolved")
```
Action: keep in the existing `helpdesk-resolved` filter (just widen its query to add `OR subject:"Ticket Closed"`), Skip Inbox — no change to this label's existing behavior.

```
from:helpdesk@tucows.com (subject:"Ticket Received" OR subject:"Ticket Approved" OR subject:"Ticket Rejected")
```
Action: new filter, applying the existing `helpdesk-approvals` label, **Skip Inbox** (this is a separate filter from the actionable approval-request one already using that label — that one stays visible since it needs your sign-off; this one is just an FYI lifecycle notice reusing the same label for grouping).

**11. `domains-sreteam@tucows.com` — SRE incident status broadcasts**

Recurring "[ops] [SRE Status]" messages (investigating/monitoring/resolved) for domains-team incidents. Confirmed via `from:domains-sreteam@tucows.com in:inbox` — about 13 in the current inbox, all unlabeled. `secops-domains` already exists and already fits the naming convention, so this folds in there rather than becoming a new label.

**Decided:** same approach as the helpdesk items above — skip inbox entirely, monitor via the label's message count instead of inbox visibility:

```
from:domains-sreteam@tucows.com
```
Action: apply existing `secops-domains` label, Skip Inbox — including "investigating"/"monitoring" messages, not just "resolved."

**12. Confluence digest — finally implementing the label proposed earlier in this doc**

`confluence-digest` has been sitting in the "New labels proposed" table since the first pass without ever getting a recipe. Confirmed it's still needed: `from:confluence@wiki-tucows.atlassian.net` turns up the recurring "Jim Mercer, your team is working on these pages" (weekly) and "Daily digest: updates from..." messages, unlabeled. Important: the same address also sends per-comment/@mention notifications (e.g. "[Confluence] Operations > ...") that should stay visible — so the recipe targets the digest subject lines specifically rather than the whole sender.

```
from:confluence@wiki-tucows.atlassian.net (subject:"your team is working on these pages" OR subject:"Daily digest")
```
Action: apply new label `confluence-digest`, Skip Inbox. Leaves comment/mention notifications from the same address untouched in the inbox.

**13. incident.io — dedicated label (new system, expected to grow)**

Recurring "Workflow failed to run: When an Wavelo incident is created or changed: Send a webhook" error notices from `no-reply@incident.io`, seen repeatedly between 2026-06-17 and 2026-06-24. This still reads like a genuinely broken integration worth fixing at the source (rebuilding the webhook connection in incident.io's workflow settings) — a filter doesn't fix that. But per Jim's call, incident.io is a new system that's going to become more important, so rather than folding its mail into the generic `secops-misc` catchall, it gets its own dedicated label now — room to grow into as more notification types show up (on-call alerts, postmortem summaries, etc.), not just this one error:

```
from:no-reply@incident.io
```
Action: create new label `incidentio-alerts`, Skip Inbox. Deliberately scoped to the whole sender rather than just the "Workflow failed to run" subject, so future incident.io notification types land here automatically too.

**14. Fellow.app — fold into existing `meetings-notes`**

Weekly digest emails and individual "shared meeting notes" messages from `no-reply@fellow.app`, unlabeled. Same functional category as the Gemini notes already covered by `meetings-notes`, so this is a one-line extension rather than a new label:

```
from:(gemini-notes@google.com OR no-reply@fellow.app)
```
Action: update the existing `meetings-notes` filter to add `OR from:no-reply@fellow.app`, Skip Inbox.

**Resolved, no filter needed:**

- ✅ `info.blazemeter@perforce.com` — Jim unsubscribed directly, so this is closed out rather than needing a filter.

(`no-reply@siebert.com` and both Meraki addresses were also found here — folded into `hr-stocks` and the new `secops-netops` respectively; see sections 5a and 4a above.)

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
4. For anything genuinely actionable — needs *your* reply or decision, like an approval request specifically waiting on you — default to **not** skipping the inbox even if it's from a vendor you'd otherwise auto-file. But Jim's stated preference (as of the second-pass review) is to keep the inbox itself as empty as possible otherwise: FYI-style lifecycle notices, status broadcasts, and ticket updates should skip inbox and get their own label even if they're not purely closed/resolved — he tracks new activity via the label/folder's unread or message count rather than inbox visibility. When in doubt between "keep visible" and "skip inbox," lean toward skip-inbox-with-a-dedicated-label unless the message is a direct ask of Jim himself.

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
| `secops-` | Security vendor feeds, tickets, monitoring reports (AlienVault/LevelBlue, Nessus, Recorded Future, ICE-AWS, HackerOne, GitHub, Jira, PhishNotify, CrowdStrike, misc/offboarding/domains/maint, `-netops` for Meraki network devices) |
| `hr-` | HR/compensation/timesheet/equity systems (HiBob, Tempo, `hr-stocks` for Carta + Siebert) |
| `helpdesk-` | Internal IT helpdesk ticket traffic, split by actionable (`-approvals`) vs. FYI (`-resolved`) |
| `newsletters-` | Marketing/webinar/training mail with no action needed (`-marketing`, `-training`) |
| `meetings-` | Meeting-related mail — auto-generated artifacts (`-notes`: Gemini/Fellow) and calendar invitations/updates/cancellations (`-invites`) |
| `misc-` | Catchall categories that don't warrant their own prefix (e.g. `misc-invoices` for billing/invoice mail across vendors) |
| `lists-` | Genuine opt-in mailing lists/working groups (IT-ISAC) |
| `wavelo-` | Internal Wavelo-specific labels (e.g. `wavelo-concerns`) |
| `confluence-` | Confluence digest-style notifications |
| `incidentio-` | incident.io platform notifications — its own prefix since Jim expects this system to grow beyond the one alert type currently filtered |

When in doubt, prefer reusing a prefix over inventing a new one — the whole point of the convention is that IMAP folders in Thunderbird sort together by category, and a proliferation of one-off prefixes defeats that.

**5. After making changes**

- New filters: Settings → Filters and Blocked Addresses → Create a new filter (see "How to add these in Gmail" above).
- New labels: make sure "Show in IMAP" is checked (Settings → Labels) or Thunderbird won't show the folder.
- In Thunderbird: right-click the account → **Subscribe...** → **Refresh** to pick up new/renamed/removed folders. Remove any stale ghost folders left behind by a rename/delete.
- Optionally, jot a one-line note (sender + label + date) somewhere so the next pass has a changelog — this doc doesn't currently track that, but there's nothing stopping you from appending a running "Change log" section here if that'd help.
