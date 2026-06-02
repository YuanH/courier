# X → Discord Bridge (Many-to-Many)

**Status:** Draft spec  
**Date:** 2026-06-02

---

## 1. Problem

You want to subscribe to multiple X (Twitter) accounts and automatically push their tweets to various Discord channels. Not one-to-one, not one source to many — **many sources, many destinations**, with routing control.

---

## 2. Architecture

```
                         ┌──────────────────────┐
  @FabrizioRomano ──────►│                      │
  @David_Ornstein ──────►│   Bridge Script      │──► Discord #futbol
  @TheAthleticFC  ──────►│   (poll + route)     │──► Discord #transfers
  @some_other     ──────►│                      │──► Discord some-channel
                         └──────────────────────┘
                              │
                              ▼
                      config.yaml (routing table)
```

**Core idea:** One daemon process polls all watched X accounts (via Nitter RSS), then routes each new tweet to every Discord channel listed for that source in the routing config.

---

## 3. Options

| Option | Runtime | Effort | Strength | Weakness |
|--------|---------|--------|----------|----------|
| **A. Custom Python script** | Python 3 | Medium | Full control, easy routing config, Mac mini native | Need to write it |
| **B. Custom Node script** | Node.js | Medium | Same as Python, already have Node on the mini | Need to write it |
| **C. MonitoRSS bot** | External SaaS | Low | Already a bot, multi-source multi-channel supported | Invite to server, depends on third-party, $? |
| **D. Forked twitter-rss-discord-webhook** | Node.js | Low-Medium | Quick start, add routing layer on top | Modifying someone else's code |

**Recommendation: A (Custom Python) or B (Custom Node).** Given this is a generic many-to-many tool, a purpose-built script is cleaner than hacking existing one-to-one tools. Pick whichever language you prefer maintaining.

---

## 4. Configuration Design

The config file (YAML for readability) defines the routing table:

```yaml
# config.yaml

# Global settings
settings:
  poll_interval_minutes: 5
  dedup_persistence: "state.json"
  nitter_fallback: "xcancel.com"   # if primary nitter.net fails

# Nitter instance preference (RSS is required)
nitter_instances:
  primary: "https://nitter.net"
  fallback: "https://xcancel.com"
  other_options:
    - "https://nitter.privacyredirect.com"

# Sources: X accounts to watch
sources:
  - handle: "FabrizioRomano"
    display_name: "Fabrizio Romano"
    active: true

  - handle: "David_Ornstein"
    display_name: "David Ornstein"
    active: true

  - handle: "TheAthleticFC"
    display_name: "The Athletic Football"
    active: true

  - handle: "DeadlineDayLive"
    display_name: "Deadline Day"
    active: false           # inactive until summer window

# Destinations: Discord channels as webhook URLs
destinations:
  - id: "futbol"
    webhook_url: "https://discord.com/api/webhooks/..."
    display_name: "#futbol"

  - id: "transfers"
    webhook_url: "https://discord.com/api/webhooks/..."
    display_name: "#transfers"

  - id: "general"
    webhook_url: "https://discord.com/api/webhooks/..."
    display_name: "#general"

# Routing: which sources go to which destinations
routes:
  - source: "FabrizioRomano"
    destinations: ["futbol", "transfers"]

  - source: "David_Ornstein"
    destinations: ["futbol", "transfers"]

  - source: "TheAthleticFC"
    destinations: ["futbol"]
```

**Key design decisions:**
- Sources and destinations are declared separately, then wired together via `routes`
- Each source can fan out to N channels
- Each channel can receive from M sources
- `active: false` lets you turn off sources without deleting them
- YAML over JSON — comments, cleaner

---

## 5. Script Behaviour (Python Pseudocode)

```python
while True:
    for source in active_sources:
        rss_url = f"{nitter}/{source.handle}/rss"
        feed = parse_rss(rss_url)
        new_tweets = deduplicate(feed, state[source.handle])

        for tweet in new_tweets:
            destinations = routes[source.handle]
            for dest in destinations:
                webhook_url = dest.webhook_url
                payload = fmt_discord_embed(source, tweet)
                post_webhook(webhook_url, payload)

        state[source.handle] = last_seen_id(feed)
        sleep(seconds_between_feeds)

    save_state()
    sleep(poll_interval_minutes * 60)
```

**Deduplication:** Store `{source_handle: last_tweet_id}` in `state.json`. On boot, only process tweets newer than the stored ID.

**Embed format (Discord webhook):**
```json
{
  "username": "Fabrizio Romano",
  "avatar_url": "https://...",
  "embeds": [{
    "description": "🔴 Here we go...",
    "url": "https://fxtwitter.com/FabrizioRomano/status/123456789",
    "color": 0x1DA1F2,
    "footer": {"text": "🐦 X • 5m ago"},
    "image": {"url": "..."}   # if tweet has media
  }]
}
```

---

## 6. Deployment on Mac mini

**Bare-metal (recommended for this scale):**

```bash
# Python (if going that route)
cd ~/clawd
mkdir x-bridge && cd x-bridge
python3 -m venv venv
source venv/bin/activate
pip install pyyaml requests feedparser
# ... create bridge.py and config.yaml ...

# pm2 for persistence
npm install -g pm2
pm2 start bridge.py --interpreter python3 --name "x-bridge"
pm2 save
pm2 startup
```

**Or with Podman (if you want it containerized with the rest of your stack):**

```dockerfile
FROM python:3.12-alpine
RUN pip install pyyaml requests feedparser
WORKDIR /app
COPY bridge.py config.yaml ./
CMD ["python3", "bridge.py"]
```

```bash
podman build -t x-bridge .
podman run -d \
  --name x-bridge \
  -v ./config.yaml:/app/config.yaml \
  -v ./state.json:/app/state.json \
  --restart=always \
  x-bridge
```

---

## 7. Beyond Twitter - Future Sources

The config structure already supports adding non-X sources in the future:

```yaml
sources:
  # Existing Twitter accounts via Nitter RSS
  - handle: "FabrizioRomano"
    type: "nitter"
    active: true

  # RSS feeds directly
  - handle: "BBC Sport"
    type: "rss"
    url: "https://feeds.bbc.co.uk/sport/rss"
    active: true

  # Reddit subreddit
  - handle: "r/soccer"
    type: "reddit"
    subreddit: "soccer"
    active: true

  # YouTube channel
  - handle: "Tifo Football"
    type: "youtube"
    channel_id: "UC..."
    active: false
```

The router still works the same — just different feed parsers per `type`, same routing table.

---

## 8. Config Change Workflow

To **add a source** → add entry to `sources` + add route in `routes` → script picks it up on next poll cycle (config reload every N cycles or on SIGHUP).

To **add a Discord channel** → create webhook in Discord → add `destinations` entry → add routes. No restart needed if the script watches config file for changes.

Alternatively, `HUP` the process or `docker restart` the container to reload config.

---

## 9. Potential Issues & Mitigations

| Issue | Mitigation |
|-------|-----------|
| Nitter instance down | Define fallback instance; script tries `nitter_instances.fallback` before skipping |
| Discord rate limiting | Webhook POST with backoff (409/429 → exponential backoff) |
| Tweet deleted between poll and post | Not worth handling — just the nature of the beast |
| First run floods channels | `state.json` default to "now" timestamp, so only forward tweets |
| Config is YAML and invalid | Validate on startup; die with useful error message |

---

## 10. Decision Checklist

- [ ] **Language:** Python or Node.js
- [ ] **Config format:** YAML (`config.yaml`)
- [ ] **Default poll interval:** 5 minutes
- [ ] **Fallback Nitter:** `xcancel.com`
- [ ] **URL format in embeds:** `fxtwitter.com/<handle>/status/<id>` for rich Discord previews
- [ ] **Per-source avatar:** Auto-fetch from X or manual override in config
- [ ] **Process manager:** pm2 (lighter) or Podman (consistent with stack)
- [ ] **Config reload:** On SIGHUP or periodic file-watch

---

## 11. Quickstart Commands (once config is ready)

```bash
cd ~/clawd && mkdir -p x-bridge
cd x-bridge
python3 -m venv venv
source venv/bin/activate
pip install pyyaml requests feedparser

# Create config.yaml, then run
python3 bridge.py
```

---

*Open for edits. Once the config shape is signed off I can write the actual script.*