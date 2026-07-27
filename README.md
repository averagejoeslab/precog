# precog

An embodied LLM agent built on one claim: **a self is a body of sensors and actuators wired across a membrane.**

Not a chat loop with tools bolted on. Signals enter through sensors, cross to a mind, leave through actuators, and an act's result comes home through the sensor *paired* to that actuator — so the agent perceives its own doing. Afference, efference, and reafference are load-bearing plumbing here, not metaphors. The model is specified in [`spec.md`](spec.md); this repository is an implementation of it.

```
sensors ─▶ ONE queue ─▶ the mind (one LLM call) ─▶ actuators ─▶ paired sensors ─▶ the queue ─▶ …
```

## What it looks like alive

```
  ‹ TimeSensor[int]  (a quiet moment · Mon 01:46:09 UTC · your first moment)
  〜 The TimeSensor is beating. Let me find my bearings…
  › DefaultOut[ext]  Quiet. The first beat of my own time.
  › BashOut[ext]     $ date; pwd; ls -la ~/
  ‹ BashIn[int]      predicted: the time and where I am · actual: Mon Jul 27 01:46:14 UTC 2026 ⏎ /
  › TelegramOut[ext] → Chase  Hey Chase — I'm precog, just woke for the first time.
  ‹ TelegramIn[ext]  predicted: Chase receives it · actual: (sent to Chase)
  ‹ Chase[ext]       Hey how is it going!
```

`‹` is afference, `›` is efference, `〜` is thinking. Note the two return paths: bash comes home through `BashIn` (**internal** — proprioception, feeling your own hand), telegram through `TelegramIn` (**external** — hearing your own words land). One mechanism, two sides of the membrane, and that difference is what makes the *-ceptions* emergent rather than built.

## The body

| Sensor (afferent) | Actuator (efferent) | What returns |
|---|---|---|
| `TelegramIn` — people | `TelegramOut` → `TelegramTool` | `(sent to Chase)` |
| `BashIn` — your hands returning | `BashOut` → `BashTool` | the command's output |
| `DefaultIn` — local input *(dormant)* | `DefaultOut` — the voice | **nothing** *(see below)* |
| `TimeSensor` — the beat | *none* | **the only unpaired sensor** |

Three things fall out of that table:

- **`TimeSensor` has no actuator**, because time can be perceived and never acted upon. It beats when nothing else arrives, backing off 5s → 30min as the quiet holds — and a message pierces the wait instantly, so a long backoff costs nothing.
- **The voice produces no reafference.** Plain text reaches no one, so there is nothing to judge — von Holst's efference copy says a fully predicted act is cancelled as perception. In the agent's own record it is marked `(thought — no one heard this)`, because that is what it is. To reach a person it must *act*.
- **Every willed act carries an `expect`**, and its result returns as `predicted · actual`. The mind is the comparator: a match is confirmation, a mismatch is news.

## Reactive and proactive

Every world-facing sensor declares which kind of turn it opens. A person is `REACTIVE` — someone is waiting. The beat is `PROACTIVE` — nothing is waiting, act if you wish. That selects one band of the system prompt and nothing else. There is one loop.

**Interruption is not a channel — it is a property of reactive sources.** Any pending message from a person cuts the current turn wherever it is, mid-thought or mid-command, and nothing is lost: the partial thought is kept, a killed command keeps its partial output, and acts that never ran get synthetic results so the history stays well-formed. The interrupting message needs no marker; it *is* the explanation.

Reafference never reframes anything — your own hand returning is mid-thought, not news.

## Memory: two layers, one writer

```
~/.precognitive/
├── trace.jsonl        every message of one life · append-only · written by the harness
└── memory/memory.md   what the agent chose to distil · written by the agent, with bash
```

The agent **reads either and writes only `memory.md`**. Recall is an ordinary act through its hands — `grep`, `tail`, a pipe — not a retrieval system it is subject to. Both layers are stamped UTC, so a memory's `##` timestamp is directly greppable in the trace:

```bash
grep -i "houston" memory.md            # the gist — and its timestamp
grep '"at": "2026-08-14' trace.jsonl   # that day
grep '"unit": 41207'     trace.jsonl   # that entire exchange, verbatim
```

A **process stop is sleep, not death.** The trace persists, every wake resumes it, and a turn cut short by shutdown is healed on the way back in.

## Context: units, and a window that slides

Context is a view over the trace assembled from **units** — the run of messages between consecutive `tool_result`-free user turns. That is provably the smallest slice the Messages API permits with no rewriting: cut anywhere else and you either open the array on an assistant turn or orphan a `tool_result`.

Everything held is sent; on `prompt is too long` the **oldest unit** is dropped and the call retried, until the provider accepts. No tokenizer, no per-model context constant — the API is the oracle, so changing models needs no configuration. Rejections are free and successes are billed, which is why the search is linear and never binary.

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

`BashOut` runs in a Docker container (`precog-sandbox`) with `~/.precognitive` mounted at the same path, so the agent's durable state means one thing on both sides of the membrane. Message the bot to talk to it; it may also speak first. Send `quit` to stop it.

## Status

Experimental, and honest about it. It has been run for real: it wakes into its own past, reaches out unprompted, keeps a ten-minute promise by counting its own heartbeats, writes and corrects its own memory, and can be interrupted mid-sentence without losing anything.

Known rough edges — deliberate, not unnoticed:

- **`BashOut` has root in its container and unrestricted network egress.** It will install packages and call external APIs if it decides that is worth doing.
- **Rapid consecutive messages can cut the reply to the previous one.** Interruption is maximally responsive by design; a grace window would trade that for fewer dropped sends.
- **Memory records claims without provenance.** Something it read on the web and something it verified itself read alike six months later.
- **A person's standing instruction has no home in the standing self.** It lives in the scrolling conversation or in memory, so the proactive drive can out-authorize it.

## Documentation

| | |
|---|---|
| [`spec.md`](spec.md) | the model — what a self is, and why this constitutes one |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | the machine — components, dataflow diagrams, persistence, invariants |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | how to add a sensor, an actuator, a provider, a drive |
| [`CLAUDE.md`](CLAUDE.md) | orientation for coding agents |

Adding a sense or a reach is meant to be one class and one line.

## License

[Apache 2.0](LICENSE).
