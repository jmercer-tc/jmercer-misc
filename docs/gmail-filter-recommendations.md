# Gmail Inbox Cleanup: Filter Recommendations

Prepared for Jim Mercer. Based on an initial sample of ~100 recent inbox threads, then a follow-up pass covering the full current inbox (~200 threads) plus a look at what's already sitting in the existing vendor labels, to sanity-check priorities at scale.

**Limitation:** the Gmail connector I have access to can read your inbox and labels, but it can't create actual Filters (Settings > Filters and Blocked Addresses) — that API isn't exposed to me. So below are ready-to-paste filter recipes: the exact search string for the "Has the words" field, the label to apply, and whether to skip the inbox.

**Naming convention:** new labels use a `category-detail` prefix (`hr-`, `helpdesk-`, `secops-`, etc.) so they sort together alphabetically in an IMAP folder list. Existing labels (`alienvault`, `nessus`, `recorded-future`, `radware`, `ice-aws`, `carta`, `hacker1`, `confluence-digest`) are left as-is — only new labels follow the prefix scheme.

## What's already working (leave alone)

`nessus`, `recorded-future`, `radware`, and `github`/`jira`/`hacker1` are catching real volume — tens of messages each when you look past the inbox at everything they've already sorted. These filters are doing their job; no changes needed.

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
Action: Apply existing label `alienvault`. Keep `cybersupport@levelblue.com` ticket-update messages visible in the inbox (may need a response) — only the marketing mail from `experts@comms.levelblue.com` is safe to skip inbox.

## Notes for IMAP client use

Since you read mail through an IMAP client rather than Gmail's web UI day-to-day:

- Gmail exposes each label as an IMAP folder, but a label isn't an exclusive folder — a message keeps living in "All Mail" regardless of which labels it has. Nothing described above deletes or hides anything; it's all still searchable in All Mail as a fallback.
- "Skip Inbox" removes the `INBOX` label rather than moving the message anywhere, so the message will disappear from your IMAP "INBOX" folder but remain fully visible under the label's own folder and in All Mail.
- New labels have a "Show in IMAP" checkbox under Gmail Settings > Labels. Check that it's enabled for each new label above, or it won't appear as a folder in your client even though the filter is working correctly.

## How to add these in Gmail

Settings (gear icon) → **See all settings** → **Filters and Blocked Addresses** → **Create a new filter**. Paste the query into the search field, click "Create filter," then check "Apply the label" (creating a new one if needed) and "Skip the Inbox" where noted above.
