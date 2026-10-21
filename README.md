# London Property Club

An original interface for a classic London Monopoly game for 2–6 human players.
Python rules run on the Streamlit server. Supabase stores shared rooms with
transactional compare-and-swap updates. The browser never receives a database
key, deck order, or another player's authentication credential.

## Play

1. Open the app, enter your name, choose one of six tokens, and create a table.
2. Share the six-character room code or the invitation URL under **Invite & reconnect**.
3. Friends open the same app, select **Join**, and choose unused names and tokens.
4. Each player selects **Ready**; the host starts once 2–6 players are ready.
5. Roll, buy or auction properties, trade through **Deals**, and manage buildings
   and mortgages in **Your portfolio**. Updates arrive automatically every 1.5 seconds.
6. Browsers remember their seats in local storage. Keep the private recovery key
   if you want to reconnect from a different browser. Do not share recovery keys.

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

All 40 London spaces, 28 deeds, rents, 8 colour groups, building prices,
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
auctions, and the last-player-standing win condition. Free Parking has no reward.
Rent collection is automatic rather than requiring a human to request payment.

Reference: [Hasbro Classic UK instructions](https://instructions.hasbro.com/en-gb/instruction/monopoly-game).
Visuals are original; no Hasbro mascot, logo, supplied board scan, or card artwork
is distributed. This is an unofficial fan project, not a licensed Hasbro product.

## Tests

```powershell
python -m pytest test_game.py -q --cov=engine --cov=store
```

The suite covers all 40 spaces, all 32 cards, all 28 property purchases, rents,
auctions, jail, building constraints, supply shortages, mortgages, trades,
bankruptcy, secure recovery, six-player lobbies, eight competing writes and
duplicate commit receipts, plus three six-player games played through to a
winner using legal actions. Test participants are not exposed as AI opponents.

## Files

- `app.py`: Streamlit screens, lobby, actions, portfolio, trades, live polling.
- `ui.py`: original HTML/CSS/JS board, animation, browser recovery bridge.
- `engine.py`: server-authoritative rules and invariant checks.
- `data.py`: London board, rents, building prices, card effects.
- `store.py`: Supabase and local SQLite backends, membership and action service.
- `schema.sql`: Supabase tables, protected functions and grants.
- `test_game.py`: automated tests and six-player simulations.

## Operational limits

- Players need to respond to auctions and shortage decisions. A disconnected
  player can reconnect, but there is no host kick, forced timeout, or AI substitute.
- Refresh synchronization is polling (1.5 seconds), not a websocket subscription.
- Each room retains its most recent 300 history entries. Completed rooms remain
  in Supabase until the owner removes them; no automatic data retention job exists.
- Sessions use private bearer recovery keys, not email/password accounts.
- Public deployments need host monitoring and rate limiting for abuse at scale.
- Passing tests does not certify every interpretation of every historical rules
  printing. Browser and Supabase integration checks must be reported separately.
