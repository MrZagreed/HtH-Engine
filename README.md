# HtH Engine (Release)

[Русская версия](README_ru.md)

Real-time Spotify -> Discord Rich Presence with synchronized lyrics.

Note: `HtH` is a reference to AC/DC's song `Highway to Hell`.

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

This project began in May 2025. I was 19 years old and in my third year of college. After finishing my internship, I felt a strong desire to build something of my own from scratch, not just a class assignment or a short experiment, but a complete tool I could truly finish.

This became my first genuinely serious independent project. Before that, I had built smaller programs and experiments, but this was the first time I committed to the full development path: from the initial idea and first lines of code to a stable and polished result.

At the beginning, everything was simple. The first version was a single monolithic file of roughly 300 lines. There was almost no architecture. It worked mostly because the codebase was still small.

Over time, the project started to evolve. As I continued studying in college, I discovered new development approaches and tools, and I gradually brought those lessons into this project. I rewrote parts of the system, split the code into modules, improved the structure, and worked to make the architecture clearer and more resilient.

Development was not always smooth. There were periods when I had to pause because some tasks were too complex for my experience at the time. But I kept returning to the project with better understanding and stronger skills.

Step by step, that simple monolithic script became a full modular project. The process took almost a year and became an important practice for me. It taught me patience, systems thinking, and how to improve code incrementally.

Today, **March 10, 2026**, as I am finishing my fourth year and now 20 years old, I can finally say I brought this project to a state I am truly satisfied with.

For me, **HtH Engine** is more than just code. It is a journey from a small experiment of a few hundred lines to a complete tool that grew together with my knowledge.

I sincerely hope this application will be useful to someone else.

Mr.Zagreed
March 10, 2026
## Troubleshooting
1. Fully restart Discord
2. Restart app
3. Check latest `logs/debug_*.log`

## Current release version
`1.0.0`




## Safe release
1. Run: `py -3.12 scripts/release_guard.py --create-archive`
2. Follow: `RELEASE_CHECKLIST.md`
3. Publish tag `v1.0.0` and upload `dist/hth-engine-v1.0.0.zip`
