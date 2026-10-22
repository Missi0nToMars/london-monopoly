# London Property Club

Live game: https://london-property-club-missi0ntomars.streamlit.app/

An original interface for a classic London Monopoly game for 2–6 human players.
Python rules run on the Streamlit server. Supabase stores shared rooms with
transactional compare-and-swap updates. The browser never receives a database
key, deck order, or another player's authentication credential.

## Play

1. Open the app, enter your name, choose one of six tokens, and create a table.
2. Share the six-character room code or the invitation URL under **Invite & reconnect**.
3. Friends open the same app, select **Join**, and choose unused names and tokens.
4. Each player selects **Ready**; the host starts once 2–6 players are ready.
5. Roll, buy or auction properties, and open **Trade room** for a private trade
   composer with live cash sliders, deed selection and a net-cash summary. Select
   **Counteroffer** on an incoming offer to edit its reversed terms. Sending
   replaces the original atomically; closing the draft leaves it open.
   Click a property in your collection or on the board to open its management
   window with rents, building purchases/sales, mortgages and redemption.
   Updates arrive automatically every 0.75 seconds.
6. Browsers remember their seats in local storage. Keep the private recovery key
   if you want to reconnect from a different browser. Do not share recovery keys.
7. **declare bankrupcy** opens a confirmation to permanently forfeit your seat.
   In the lobby it frees the seat and transfers hosting if necessary. In a game,
   your assets go to your current creditor or back to the bank for auction. This
   is the user-requested voluntary exit feature; ordinary debt bankruptcy still
   requires insolvency. A remaining sole player wins automatically.
8. **Create or join another table** switches views while preserving the old seat;
   it does not forfeit that seat. Reopen its invitation to return.

## Interface and responsiveness

Tokens have larger coloured bases, an active-player ring and a matching name
legend. Persisted movement routes animate every square around corners, across
GO and backwards for card moves, rather than sliding diagonally across the board. The **Piece movement** menu selects Smooth, Gentle steps or Instant for this browser. Reduced-motion browsers default to Gentle steps, which visibly pauses on each adjacent square; they no longer skip the entire route. Smooth explicitly enables gliding between squares without changing operating-system settings. A progress line names the current square during movement.
The activity feed uses icons and categories for rolls, purchases, rent, trades,
auctions, buildings and bankruptcy. Existing saved rooms remain compatible.

Dice results show the roller, both values, the total and a doubles label.
The board, turn controls, balances, property collection and deal list now share
one persistent browser surface. Polls update it in place only when the room
version changes. Unchanged polls do not recreate buttons, forms, history rows
or token elements. The local countdown updates once per displayed second.

Property desks, trade drafts, reviews, counteroffers and leave confirmations
open locally, without a Python rerun or extra database read. Background sync
continues while they are open. Trade drafts retain their cash amounts and deed
selections when another player acts; a refresh-choices button can reload the
available properties without clearing the draft. Closing a draft sends nothing.
Buttons depress immediately and show Saving while a submitted action is pending.
The server still authenticates the player, validates every action and checks
the shared version atomically. Conflicts refresh the table and keep a failed
draft open for review; no speculative money, dice or ownership changes are shown.

Action callbacks commit before the automatic fragment run. A newly acknowledged
commit supplies the immediate response without a second database round trip;
the next poll reads the database normally so opponents' moves are still seen.
Duplicate receipts never predict a new state. HTTP connections are reused per
server thread. Native host settings, admin tools and recovery controls live in
a separate fragment that is not rebuilt by the play timer.

Streamlit still executes a small server fragment for synchronization and actions;
it no longer reconstructs the visible play interface after each ordinary action.
Creating, joining, changing table and starting/finishing a game can still rerun
the outer app. A truly push-driven client would require a separate API/frontend
deployment. No hosting migration or player setting is required for this update.
The 0.75-second poll interval is a target, not a latency guarantee: hosting load,
network distance and database response time still affect saved-move latency.
When updates stop, a reconnecting indicator preserves the last visible board.

## Room rules, clocks and admin mode

The host can edit **Room rules & timers** in the lobby: starting cash, GO salary,
double salary on GO, a Free Parking jackpot funded by bank payments, tax and jail
amounts, auctions for declined purchases, even building/selling, and rent while
the owner is in jail. Saving changes resets every player's Ready status; rules
lock when the game starts. All players can inspect the chosen rules during play.

New rooms enable a decision clock by default: 60 seconds for an ordinary
decision, 180 for debt, 30 for each auction response, and removal after two
consecutive missed decisions. The host can configure or disable these in the
lobby and can grant up to five one-minute extensions per decision during play.
Old saved rooms remain untimed. Manual decisions reset that player's miss count;
trades and unrelated clicks do not reset the current deadline. Missed rolls roll
automatically, purchases are declined, auction bids are passed, mortgage
inheritances retain their mortgage, and building requests are declined. The first
debt timeout grants another full grace period; repeated misses forfeit the seat
using the same asset/creditor and winner handling as voluntary bankruptcy. No
assets are automatically mortgaged or sold to make a decision for an absent player.

Deadlines live in shared state and are enforced on the server. Authenticated
polls advance expired decisions through compare-and-swap commits, so two readers
cannot apply the same timeout twice. If all browsers are closed or the host is
asleep, the next authenticated read processes the expiry and grants a fresh
deadline for the next decision; it does not fast-forward many missed turns.
Opening a personal window does not pause the stored deadline.

Hover a player in the board legend, click their name, or use **Portfolio** above
the board to highlight every property they own. The selector supports touch and
keyboard use; All properties clears the highlight.

**Admin commands** is an optional, intentionally unfair mode. Only the room's
authenticated host can unlock it, using the fixed shared code **676767**, and
only that host can issue powers. This is a game unlock switch, not a secret
security credential; the public source contains the code. Admin-mode banners and
enabled/disabled notices are not shown publicly; every actual power is still
logged. Powers create/set cash, transfer
one deed or a whole colour set, grant a set with free hotels, move a piece without
landing effects, jail/release players, rig the host's next dice, skip a turn,
bankrupt an opponent, or declare a winner. Most require no pending decision;
cash powers can resolve debt. Hotel supply and ownership invariants still hold.
Unlocking in the lobby resets Ready status. Disabling clears queued rigged dice.

## Run locally

Python 3.12 recommended. From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
$env:MONOPOLY_LOCAL = "1"
.\.venv\Scripts\python -m streamlit run app.py
```

Local mode uses `local-games.db`. This mode supports separate browser sessions
connected to the same server, but is intended for local tests. Online deployment
must use Supabase so restarting or redeploying Streamlit does not lose rooms.

## Supabase setup

1. Create a Supabase project in your own account. Use a free plan if available.
2. Run **schema.sql** in its SQL Editor.
3. In Streamlit Community Cloud → your app → Settings → Secrets, enter:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "YOUR_SERVER_ONLY_SB_SECRET_KEY"
PUBLIC_APP_URL = "https://YOUR_APP.streamlit.app"
```

Do not commit actual secrets. Supabase's secret key is server-only and
must never be placed in frontend JavaScript or a public repository. Tables have
RLS enabled, no anonymous or authenticated grants, and no public policies. Only
the server role can execute the three database functions. The commit function
locks the room row, checks its version, and records an action receipt in the
same transaction. Stale simultaneous actions are rejected and the next refresh
shows the latest state. The SQLite backend implements the same contract.

Modern `sb_secret_` keys use the `apikey` header only; legacy JWT service-role
keys also remain supported through `SUPABASE_SERVICE_ROLE_KEY` for existing setups.

Player recovery keys contain 256 bits of random entropy; only SHA-256 hashes
are stored in the database. Room codes are invitations, not player credentials.
The server authenticates membership for every read and mutation, then validates
actions in Python. All dice and deck shuffles use server-side randomness.

## Deploy on Streamlit Community Cloud

1. Upload these source files to a GitHub repository.
2. In Streamlit Community Cloud choose **Create app → Deploy from GitHub**.
3. Select your repository, branch `main`, main file `app.py`, and Python 3.12.
4. Set the Supabase secrets above, then deploy.
5. Set `PUBLIC_APP_URL` to the actual deployed address so invitation links are complete.
6. Test from two different browser profiles, refresh each, and confirm the same
   room, balances, dice, and active turn remain synchronized.

The app displays a setup message and disables game creation if neither Supabase
nor explicitly enabled local mode is configured. It does not silently use
ephemeral cloud storage for an online game.

## Rules and edition

At the default classic settings, all 40 London spaces, 28 deeds, rents, 8 colour groups, building prices,
railways, utilities, and fixed £200 Income Tax / £100 Super Tax match the supplied
board. There are two shuffled 16-card decks; card text is independently
paraphrased using the familiar modern Classic UK card effects. Historical UK
printings have different cards; a board photograph alone does not identify its
included deck. The older US percentage income-tax option is not used.

The engine implements doubles and three-doubles jail, three jail attempts,
Get Out of Jail Free cards, bank purchases and auctions (including the declining
player), colour-set rents, fresh dice for the Chance utility instruction,
even building and selling, 32 houses / 12 hotels, building-shortage auctions,
mortgages and redemption, mortgage-transfer interest, trades with immediate
redemption choices, cash-raising for debts, bankruptcy transfers and bank
auctions, and the last-player-standing win condition. Free Parking has no reward by default.
Rent collection is automatic rather than requiring a human to request payment.

Reference: [Hasbro Classic UK instructions](https://instructions.hasbro.com/en-gb/instruction/monopoly-game).
Visuals are original; no Hasbro mascot, logo, supplied board scan, or card artwork
is distributed. This is an unofficial fan project, not a licensed Hasbro product.

## Tests

```powershell
python -m pytest test_game.py test_room_features.py -q --cov=engine --cov=store
```

The suite covers all 40 spaces, all 32 cards, all 28 property purchases, rents,
auctions, jail, building constraints, supply shortages, mortgages, trades,
bankruptcy, secure recovery, six-player lobbies, eight competing writes and
duplicate commit receipts, plus three six-player games played through to a
winner using legal actions. Test participants are not exposed as AI opponents.

## Files

- `app.py`: Streamlit entry forms, authenticated action callbacks, live polling and host tools.
- `ui.py`: persistent HTML/CSS/JS play surface, local desks, animation and recovery bridge.
- `engine.py`: server-authoritative rules and invariant checks.
- `data.py`: London board, rents, building prices, card effects.
- `store.py`: Supabase and local SQLite backends, membership and action service.
- `schema.sql`: Supabase tables, protected functions and grants.
- `test_game.py`: automated tests and six-player simulations.
- `test_room_features.py`: rules, clocks, timeout races and admin permissions.

## Operational limits

- Configured decision clocks handle inactive players. Without clocks, players
  must respond or reconnect. There is no AI substitute or ordinary host kick.
- Refresh synchronization is polling (0.75 seconds), not a websocket subscription.
- Each room retains its most recent 300 history entries. Completed rooms remain
  in Supabase until the owner removes them; no automatic data retention job exists.
- Sessions use private bearer recovery keys, not email/password accounts.
- Public deployments need host monitoring and rate limiting for abuse at scale.
- Passing tests does not certify every interpretation of every historical rules
  printing. Browser and Supabase integration checks must be reported separately.




