# SmartShift — what to say at the demo

## 1. Why a website
One URL works on the venue laptop and on hosts' phones with nothing to install; part-time hosts won't install an app for a few shifts a month. Privacy lives on the server (the host's browser never receives other hosts' data), and pasting from Excel is a browser-native gesture. A desktop app would serve only the manager; a mobile app adds store/install friction for no gain.

## 2. How the scheduling algorithm works
Groups are processed in date/start order. For each group, candidates are hosts whose declared availability (regular or on-call) covers the whole group and who would not exceed **2 simultaneous groups**. Each candidate gets a score (lower wins):

- **Fairness** `20 × (assigned hours + this group) / capacity hours`
- **Four-hour rule** `−3` for each same-day group already on this host starting < 4 h away; `−1.5` for each not-yet-assigned same-day group < 4 h away that this host could also take (look-ahead: this is what makes the brief's 10:00/12:30 example go to the host who can do both); `+2` for each same-day group > 4 h away.
- **On call** `+5` when the only cover is an on-call day (last resort); becomes `−5` in last-minute mode (new group added after the schedule exists), so on-call hosts are chosen first.

Ties: fewer groups, then lower id. Every assignment stores its reason, shown in the Schedule tab. Groups with no candidate are stored as **unassigned** with the reason ("No one is available…" or "Everyone available already hosts 2 groups"). Manual assignments are locked and count toward load when regenerating. Complexity O(groups × hosts × groups-per-day), instant for hundreds of groups.

## 3. Privacy
The signed-in user is a server-side session. Every `/me/...` query filters by that user id; editing or deleting another host's row by URL returns 403, as does opening `/manager` as a host. The manager sees everything. Demo: as Bence, open `/me/availability/1/delete` or `/manager` → 403 page.

## 4. Fairness
**Load = scheduled hours ÷ available hours** (an on-call day counts as 8 h). A host available 50 h/week and one available 12 h/week end up with similar *load*, not similar *counts*, which is exactly what the brief asks. The Hours tab shows groups, scheduled hours, available hours and load per host; the generate message reports the load spread (max − min). Counting assignments would punish part-timers; counting hours without capacity would punish full-timers.

## 5. Extensions
- `/api/bookings` already accepts bookings from an external website and assigns on the spot.
- Notifications: hook the assignment write path (one function) to e-mail/push.
- Rolling 4-week fairness window, per-host target hours, travel time between groups.
- Swap the greedy scheduler for an ILP/CP-SAT optimiser behind the same `schedule()` signature.
- Real authentication (OIDC), calendar export (.ics), host-to-host swap requests.

## Limitations
Greedy, not globally optimal; one-week horizon; capacity ignores whether availability actually fits group times; no real auth; one manager; no overnight groups.
