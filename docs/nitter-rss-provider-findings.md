# X RSS provider findings and recovery notes

## Purpose

This document records the production investigation into Courier's X/Twitter RSS ingestion outage and the safeguards added to prevent misleading success signals or lost Discord deliveries.

It intentionally contains no Discord webhook URLs, XCancel reader identifiers, account credentials, or other secrets.

## Courier data flow

Courier uses public Nitter-compatible services to turn a public X account timeline into RSS:

```text
configured X handle
  -> Nitter-compatible provider RSS endpoint
  -> Courier parses only real /status/<tweet-id> entries
  -> Courier compares IDs with persistent watermark state
  -> Courier sends new items to configured Discord destinations
  -> Courier advances watermark only after complete delivery
```

Current configured provider order:

```text
nitter.net -> xcancel.com -> nitter.privacyredirect.com
```

## What changed

Previously, Courier had delivered real X items; persisted X snowflake watermarks date the last known delivered items to August 20–21, 2026 UTC.

During the outage investigation, the following live behavior was observed from Courier's actual Podman network namespace:

| Provider / request profile | Result | Usable tweet RSS? |
| --- | --- | --- |
| `nitter.net/<handle>/rss` with a browser-like request | `200 OK`, empty body | No |
| `nitter.net/<handle>/rss` with an RSS-reader request | `403`, body says `nitter RSS feed is disabled` | No |
| `xcancel.com/<handle>/rss` with a browser-like request | Redirect, then `400` from `rss.xcancel.com` | No |
| `xcancel.com/<handle>/rss` with RSS-reader identity (`Feedly/1.0`) | `200 OK`, valid RSS containing an XCancel whitelist interstitial | No |
| `nitter.privacyredirect.com/<handle>/rss` | connection timeout | No |

The XCancel response is structurally valid RSS but has one non-tweet entry and no `/status/<tweet-id>` links. HTTP success or a nonzero RSS entry count alone is therefore not evidence of an available timeline.

The investigation does not establish a single upstream cause for the public Nitter failures. They may reflect instance operator policy, upstream X changes, rate limits, availability, or network-specific restrictions. The current operational fact is that none of the configured providers returns usable tweet entries from Courier's environment.

## Code safeguards added

### Provider fallback inclusion

The runtime provider list now includes all configured fields:

```text
primary + fallback + other_options
```

Previously, the explicit `fallback` field (including XCancel) was accepted in configuration but omitted when `Engine` constructed the active Nitter source.

### XCancel-compatible request profile

Courier retains its established browser-like request profile for generic Nitter instances. It additionally retries XCancel with an RSS-reader user agent because XCancel explicitly distinguishes RSS-reader traffic from normal browser/curl requests.

### Usable-feed validation

The source implementation now treats the following as provider failures and continues to the next configured option:

- empty response body;
- HTTP failures;
- non-RSS HTML or malformed feeds;
- zero parsed entries;
- feeds with no extractable tweet `/status/<tweet-id>` links;
- network failures and timeouts.

This specifically prevents the XCancel whitelist page from being logged as a successful timeline fetch.

### Delivery watermark durability

Courier now advances a source watermark only through the latest item that every configured destination accepted.

- If a Discord destination fails, processing stops at that item.
- If a configured destination is unknown, processing stops at that item.
- Later items are not skipped.
- On the next poll, Courier retries from the last fully delivered item.

This prevents a transient Discord failure from permanently dropping an X post.

## Current state after rebuild

The current build is healthy as a process and polls configured sources. It correctly logs provider failures, including XCancel's `no-status-links` whitelist interstitial result. It cannot presently send X items because no configured provider returns actual tweet status links.

No source watermark should advance solely because a provider returns the current invalid responses.

## Recovery options

1. **XCancel whitelist approval**
   - A whitelist request was sent with the reader identifier requested by XCancel.
   - This is the lowest-effort path if approval produces a timeline with real tweet status links.

2. **Official X API source adapter**
   - Build a Courier source using authorized X API access, retaining Courier's existing dedupe and Discord delivery logic.
   - This is the durable operational option, but a plan with sufficient API quota is likely required for continuous monitoring.

3. **Private Nitter deployment**
   - Technically possible using Nitter plus Redis/Valkey and a private deployment.
   - This does not eliminate X-side session/access constraints and creates ongoing operational and policy risk.
   - A reverse proxy in front of public Nitter does not solve the upstream RSS access issue.

## Verification standard

Do not declare provider recovery based only on HTTP status, XML validity, byte count, or RSS entry count. A provider is usable only when Courier observes at least one legitimate item with a URL containing:

```text
/status/<tweet-id>
```

After recovery, verify all of the following:

1. Courier logs show a usable feed and real status links.
2. New items are newer than the saved watermark.
3. Logs show `Sending` followed by `Sent` for the destination(s).
4. Discord receives the item.
5. The source watermark advances only after delivery completes.

## Safe operational commands

Run from the repository root:

```bash
uv run python -m pytest tests/ -q
make rebuild
podman ps --filter name='^courier$'
podman logs --tail 120 courier
```

When sharing logs, redact Discord webhook URLs and other credentials.
