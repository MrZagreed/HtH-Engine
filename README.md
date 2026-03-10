# Highway to Hell Engine (Pre-release)

[Русская версия](README_ru.md)

Real-time Spotify -> Discord Rich Presence with synchronized lyrics.

## Zero-knowledge quick start
1. Download/unpack this project anywhere.
2. Run `run.py` (double-click) or use terminal:
   - `py -3.12 run.py`
3. On first run, choose language first (`English` default, or `Russian`), then choose mode.
4. Follow the setup wizard prompts.
5. Done. The app auto-installs everything and starts.

## What is fully automatic
- Python compatibility detection (prefers Python 3.12)
- venv creation/recreation when needed
- dependency installation from `requirements.txt`
- re-exec inside venv
- first-run setup wizard in EN/RU

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
- pseudographic progress bar in Rich Presence

## Network drop diagnostics
- Tracks `online/degraded/offline` states
- Logs outage duration, failure count, and last error
- API mode applies adaptive backoff under unstable connection
- Local mode continues tracking with reduced loop pressure

## Authorship and license
- Official author: `Mr.Zagreed`
- Runtime attribution notice is automatically enforced in code
- Tamper-evident authorship fingerprint is logged at startup
- Redistribution must include `LICENSE`

## Author story
This project started in May 2025, when I was 19 and studying in my third year of college.
After finishing my internship practice, I felt genuinely inspired to build something of my own.

The first month produced a rough and unstable prototype. It worked, but barely.
Instead of dropping it, I kept refining it step by step, turning a simple experiment into a serious long-term build.

By the time of writing this story, I am 20 and finishing my fourth year.
Today, Highway to Hell Engine represents that full journey: from a chaotic first idea to a polished release I am proud of.
I hope it becomes useful to someone else out there.

— Mr.Zagreed

## Troubleshooting
1. Fully restart Discord
2. Restart app
3. Check latest `logs/debug_*.log`

## Current pre-release version
`0.9.0-pre`
