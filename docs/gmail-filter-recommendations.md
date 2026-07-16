# Gmail Inbox Cleanup: Filter Recommendations

Prepared for Jim Mercer — based on your current labels and a sample of ~100 recent inbox threads (all from the last 4 days, which itself is a sign of how fast the inbox fills up).

**One important limitation:** the Gmail connector I have access to can read your inbox and labels, but it can't create actual Filters (Settings > Filters and Blocked Addresses) — that API isn't exposed to me. So below are ready-to-paste filter recipes: the exact search string for the "Has the words" field, plus the action to select, for each one you want to set up.

## What's already working

You've already got a solid set of vendor-specific labels handling security feeds: `alienvault`, `nessus`, `recorded-future`, `radware`, `ice-aws`, `carta`, `hacker1`, plus `secops-misc`, `secops-offboarding`, `secops-domains`, `secops-maint`. Good foundation — the gaps below are mostly newer senders that never got folded in.

## One broken filter worth fixing first

AlienVault rebranded to **LevelBlue**, and your `alienvault` filter doesn't seem to match the new domain — messages from `experts@comms.levelblue.com` and `no-reply-cybersupport@levelblue.com` are landing in the inbox unlabeled. Recommend editing that filter (or adding a second one) with:

```
from:(@levelblue.com OR @comms.levelblue.com)
```
Action: Apply label `alienvault`. I'd keep the `cybersupport@levelblue.com` ticket-update messages visible in the inbox rather than skipping it, since those can require a response — just the marketing mail from `experts@comms.levelblue.com` is safe to skip inbox.

## New filters to set up

**1. Automated security reports (currently unlabeled, arrive daily)**

```
from:no-reply@tucows.com subject:"Github Repository Monitoring Report"
```
Action: Apply new label `secops-github-monitoring`, Skip Inbox. (Leave "mark as read" off, so the label still shows unread counts you can review in a batch.)

```
from:no-reply@securityiq-notifications.com
```
Action: Apply new label `secops-phishnotify`, Skip Inbox. These "Reported Emails Summary" notices go to a 9-person distro and hit your inbox several times a day.

**2. HR / HiBob notices**

```
from:no-reply@hibob.com
```
Action: Apply new label `hr`, Skip Inbox. These are FYI confirmations (time-off approvals, scheduled reports) — nothing actionable once sent.

**3. Auto-generated meeting notes**

```
from:gemini-notes@google.com
```
Action: Apply new label `meeting-notes`, Skip Inbox. You're getting one of these per standup/meeting — useful as reference, not something that needs inbox real estate.

**4. Newsletters / webinar marketing (the real mailing-list clutter)**

```
from:(customerservice@perkopolis.com OR update@grafana.com OR customereducation@docebo.com OR events@docebo.com OR contactus@docebo.com OR training@e.infosecinstitute.com OR info@e.atlassian.com OR aws-marketing-email-replies@amazon.com OR noreply@meraki.com OR donotreply@notifications.visaacceptance.com OR experts@comms.levelblue.com)
```
Action: Apply new label `newsletters`, Skip Inbox.

Worth calling out: Perkopolis (employee perks deals) and Infosec Institute's marketing/poll emails are landing **three times each** — once per alias (`@tucows.com`, `@tucowsinc.com`, `@wavelo.com`). A filter can bundle them out of your inbox, but it won't stop the triplication. If you want that gone entirely, unsubscribing via the link in one or two of those emails (per alias) is the only real fix — a filter can't merge duplicate sends across different recipient addresses.

**5. IT helpdesk — split into actionable vs. FYI**

Approval requests need your sign-off, so keep those visible:
```
from:(helpdesk@tucows.com OR it@tucows.freshservice.com) subject:"Request for Approval"
```
Action: Apply new label `approvals-pending`. Don't skip inbox — just makes them easier to find/filter later.

But "resolved" notices are pure FYI:
```
from:helpdesk@tucows.com subject:"Ticket Resolved"
```
Action: Apply new label `helpdesk`, Skip Inbox.

**6. Confluence weekly digest**

```
from:confluence@wiki-tucows.atlassian.net
```
Action: Apply new label `confluence-digest`, Skip Inbox.

**7. IT-ISAC AI SIG mailing list**

This one's a genuine opt-in working group, not spam — I'd label it for easy reference but leave it in the inbox rather than skipping, since meeting notes/slide decks are time-sensitive:
```
from:it-isac.org
```
Action: Apply new label `it-isac`. Skip inbox optional — your call depending on how closely you follow that group.

## Net effect

Setting up filters 1–6 above would pull roughly two-thirds of the ~100 messages I sampled out of your inbox automatically, leaving behind: real human correspondence, calendar invites, approval requests that need your action, and the vendor security alerts your existing filters already catch (once the LevelBlue domain fix is in). Everything filtered out stays fully searchable by label — nothing gets deleted.

## How to add these in Gmail

Settings (gear icon) → **See all settings** → **Filters and Blocked Addresses** → **Create a new filter**. Paste the query into the search field, click "Create filter," then check "Apply the label" (creating a new one if needed) and "Skip the Inbox" where noted above.
