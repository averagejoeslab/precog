# precog

An embodied LLM agent built on one claim: **a self is a body of sensors and actuators wired across a membrane.**

Not a chat loop with tools bolted on. Signals enter through sensors, cross to a mind, leave through actuators, and an act's result comes home through the sensor *paired* to that actuator — so the agent perceives its own doing. Afference, efference, and reafference are load-bearing plumbing here, not metaphors.

```
sensors ─▶ ONE queue ─▶ the mind (one LLM call) ─▶ actuators ─▶ paired sensors ─▶ the queue ─▶ …
```

It is one Python file, `precog.py`, with one dependency.

## What it looks like alive

```
  ‹ TimeSensor[int] (a quiet moment · Mon 01:46:09 UTC · your first moment)
  〜 The TimeSensor is beating. Let me find my bearings…
  › DefaultOut[ext] Quiet. The first beat of my own time.
  › BashOut[ext]    $ date; pwd; ls -la ~/
  ‹ BashIn[int]     predicted: the time and where I am · actual: Mon Jul 27 01:46:14 UTC 2026 ⏎ /
  › TelegramOut[ext] → Chase Hey Chase — I'm precog, just woke for the first time.
  ‹ TelegramIn[ext] predicted: Chase receives it · actual: (sent to Chase)
  ‹ Chase[ext]      Hey how is it going!
```

`‹` is afference, `›` is efference, `〜` is thinking. Note the two return paths: bash comes home through `BashIn` (**internal** — proprioception, feeling your own hand), telegram through `TelegramIn` (**external** — hearing your own words land). One mechanism, two sides of the membrane.

## The body

| Sensor (afferent) | Actuator (efferent) | What returns |
|---|---|---|
| `TelegramIn` — people | `TelegramOut` → `TelegramTool` | `(sent to Chase)` |
| `BashIn` — your hands returning | `BashOut` → `BashTool` | the command's output |
| `DefaultIn` — local input *(dormant)* | `DefaultOut` — the voice | **nothing** |
| `TimeSensor` — the beat | *none* | the only unpaired sensor |

Three things fall out of that table:

- **The voice reaches no one.** Plain text goes to `DefaultOut` unconditionally — a body does not decide to move its own mouth — but a *local* voice reaches no *remote* self, so it returns nothing and is recorded as `(thought — no one heard this)`. To reach a person the agent must **act**.
- **`TimeSensor` has no actuator**, because time can be perceived and never acted upon. It beats when nothing else arrives, backing off 5s → 30min as the quiet holds; a message pierces the wait instantly, so a long backoff costs nothing.
- **Every willed act carries a prediction.** Its result returns as `predicted · actual`, and the mind is the comparator: a match is confirmation, a mismatch is news.

## What it does

It lives in a loop. When a person messages it, that reframes the turn and can cut whatever it was doing mid-word; when nothing arrives, its own clock beats and it decides what is worth doing unbidden — including speaking first. It runs shell commands in a container, keeps notes it writes itself, and reads back its own verbatim history when it needs to. A process stop is sleep, not death: the record persists and the next wake resumes the same life.

Two layers of past, and the agent writes only one of them:

```
~/.precognitive/
├── trace.jsonl        every message of one life · append-only · written by the harness
└── memory/memory.md   what the agent chose to distil · written by the agent, with bash
```

Recall is an ordinary act through its own hands — `grep`, `tail`, a pipe — not a retrieval system it is subject to. Both layers are stamped UTC, so a note's timestamp is directly greppable in the verbatim record.

Context is a window over the trace that slides by whole **units** (one complete exchange). Everything held is sent; when the provider says the prompt is too long, the oldest unit is dropped and the call retried. No tokenizer and no per-model context constant — the API is the oracle, so changing models needs no configuration.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install anthropic
cp .env.example .env          # then fill it in
.venv/bin/python precog.py
```

```ini
DEEPSEEK_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_PEOPLE={"123456789": "Chase", "987654321": "Alice"}
```

`TELEGRAM_PEOPLE` is one dict serving both directions — **the name it hears in `[Chase · 15:04]` is the name it types in `TelegramOut`'s `to`** — and its keys *are* the allowlist. Unlisted senders are dropped; an empty dict admits no one.

`BashOut` runs in a Docker container (`precog-sandbox`), with the host's state directory mounted at `/root/.precognitive` inside it. The absolute paths differ across the membrane, but `~` resolves to the mount on both sides — so the `~/.precognitive/...` paths the agent is *told* about are the paths its hands actually find. Message the bot to talk to it; it may also speak first. Send `quit` to stop it.

## Status

Experimental, and honest about it. It has been run for real, and across those development sessions it has woken into its own past, reached out unprompted, kept a ten-minute promise by counting its own heartbeats, written and corrected its own memory, and been interrupted mid-sentence without losing anything. Those are observations from live runs, not guarantees — there is no test suite, and nothing checks that any of them still holds.

Known rough edges — deliberate, not unnoticed:

- **`BashOut` has root in its container and unrestricted network egress.** It will install packages and call external APIs if it decides that is worth doing.
- **Rapid consecutive messages can cut the reply to the previous one.** Interruption is maximally responsive by design; a grace window would trade that for fewer dropped sends.
- **Memory records claims without provenance.** Something it read on the web and something it verified itself read alike six months later.
- **A person's standing instruction has no home in the standing self.** It lives in the scrolling conversation or in memory, so the proactive drive can out-authorize it.

## Documentation

| | Answers |
|---|---|
| [`spec.md`](spec.md) | **the model** — what a self is, why the *-ceptions* are emergent rather than built, and why this constitutes a being in a world |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | **the machine** — every component, the execution flow cycle by cycle, the logical dataflow diagrams, persistence, and the invariants |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | **how to add to it** — a recipe per component, the paired-sensor rule for new actuators, and the review process |
| [`CLAUDE.md`](CLAUDE.md) | **orientation for coding agents** — how the system works, what is load-bearing, and what looks like a bug but isn't |

Adding a sense or a reach is meant to be one class and one line.

## License

[Apache 2.0](LICENSE).
