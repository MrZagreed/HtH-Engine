# Highway to Hell Engine (Pre-release)

Real-time Spotify -> Discord Rich Presence with synchronized lyrics.

## Zero-knowledge quick start
1. Download/unpack this project anywhere.
2. Run `run.py` (double-click) or use terminal:
   - `py -3.12 run.py`
3. Choose a mode:
   - `API` (Spotify Premium + Spotify API keys)
   - `LOCAL` (no Premium required, Discord Client ID only)
4. Follow the first-run setup wizard prompts.
5. Done. The app auto-installs everything and starts.

## What is fully automatic
- Python compatibility detection (prefers Python 3.12)
- venv creation/recreation when needed
- dependency installation from `requirements.txt`
- re-exec inside venv
- first-run setup wizard by selected mode

## Project data locations
Created automatically on first run:
- `highway_to_hell_engine_data/config/highway_to_hell_engine_config.json`
- `highway_to_hell_engine_data/cache/lyrics_cache.db`
- `highway_to_hell_engine_data/cache/spotify_oauth_cache.json`

If an old root config existed, it is migrated automatically.

## Modes
### LOCAL mode (no Premium)
- Requires only `Discord Client ID`
- Reads real playback position from Windows Media Session (starts from true mid-track progress)
- Fallback to Spotify window title parsing

### API mode (Premium)
- Requires:
  - `Discord Client ID`
  - `Spotify Client ID`
  - `Spotify Client Secret`

## Where to get keys
### Discord Client ID
1. Open Discord Developer Portal: [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create/select an application
3. Copy `Application ID` (this is your `Discord Client ID`)

### Spotify API keys
1. Open Spotify Developer Dashboard: [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Create an app
3. Copy `Client ID` and `Client Secret`
4. In app settings, add redirect URI:
   - `https://127.0.0.1:8888/callback`

## Mini tutorial: LOCAL mode
1. Start Discord
2. Start Spotify and play any track
3. Run `py -3.12 run.py --mode=local`
4. Enter Discord Client ID in wizard
5. Confirm Discord activity visibility is enabled:
   - Discord Settings -> Activity Privacy -> `Display current activity as a status message`

## Mini tutorial: API mode
1. Start Discord
2. Run `py -3.12 run.py --mode=api`
3. Enter Discord + Spotify keys in wizard
4. Complete Spotify authorization in browser callback flow

## Lyrics sources (priority)
1. LRCLIB (synced/plain)
2. Genius
3. Musixmatch
4. AZLyrics
5. lyrics.ovh

Caching backend: SQLite (`lyrics_cache.db`).

## Rich Presence behavior
- image hover text: `Discord Karaoke RPC by Mr.Zagreed`
- safe `Open in Spotify` button (URL validation)
- throttled RPC update rate to avoid overload

## Troubleshooting
1. Fully restart Discord
2. Restart app
3. Check latest `logs/debug_*.log`

## Current pre-release version
`0.9.0-pre`
