# CLAUDE.md

Guidance for coding agents working in this repository.

## What this is

`precog.py` is a single-file embodied LLM agent. It is not a chat loop with tools attached, and reading it as one will cause you to make wrong changes. The premise, stated in [`spec.md`](spec.md): **a self is a body of sensors and actuators wired across a membrane.** Signals enter through sensors, cross to a mind, leave through actuators, and an act's result comes home *through the sensor paired to that actuator*. Afference, efference, and reafference are the actual control flow, not vocabulary layered on top.

Read in this order: `spec.md` (the model) → [`ARCHITECTURE.md`](ARCHITECTURE.md) (the machine, with diagrams) → `precog.py`. [`CONTRIBUTING.md`](CONTRIBUTING.md) has the recipes.

## Orientation

```
precog.py       the whole agent, in two halves
spec.md         the canonical model — code is an implementation of it
ARCHITECTURE.md components, dataflow, persistence, invariants
CONTRIBUTING.md how to add a sensor, actuator, provider, drive
.env.example    configuration
```

Inside `precog.py`, sections are numbered and dependencies only point upward:

```
§0 CONFIG      §1 SIGNAL      §2 AFFERENCE   §3 PORTS
§4 DRIVE       §5 PROVIDER    §6 IDENTITY    §7 BODY      §8 AGENT
—— THIS AGENT ——  organs · the self-model · build()
```

**The framework half (§0–§8) never names an organ. The THIS AGENT half never contains mechanism.** This is the single most important structural rule. If you are about to write `if actuator.name == "TelegramOut"` in the framework, the correct change is somewhere else.

## Rules that are not style preferences

Each of these exists because violating it produced a real failure. Treat them as load-bearing.

1. **`tool_use` must be the last block of an assistant turn.** Any block after it makes the API treat the call as unanswered *even when the `tool_result` is present in the next message*. This is enforced by construction in `_record`; do not reintroduce a code path that can append after it.
2. **Harness text never enters an assistant turn.** That turn records what the model produced. Source tags, `predicted · actual`, synthetic results, cut notes — all belong to the `user` turn. If the model produced nothing, append **no turn**; consecutive user turns are combined by the API.
3. **Every `tool_use` gets answered** — real result, interrupt synthetic, or wake heal. This is what keeps the unit boundary reliable, which is what keeps the sliding window valid.
4. **The trace only grows.** Sliding moves an index. The view must be a verbatim suffix of the record — never rebuild it, never fabricate a turn to make it fit.
5. **Never drop a turn that perceived the world.** The record is the only copy; the signal was already taken off the queue.
6. **Only reactive world signals interrupt.** Not the clock, not reafference.
7. **Anything naming a live part is generated, never authored** — organs, pairings, liveness, paths, dates. A hand-written organ list in the prompt goes stale the moment someone adds an organ.
8. **Never give the agent information it cannot verify.** An earlier version showed it its own source; it read a config variable, failed to find it in the one shell it can reach, and concluded it could message nobody — which was false. Self-knowledge comes from the generated body-schema, which it can check by acting.

## Where changes go

| You want to | Change | Half |
|---|---|---|
| add a way the world reaches in | a `Sensor` subclass + one line in `build()` | this agent |
| add a way to act | a `Tool` + an `Actuator` fronting it + its return `Sensor` | this agent |
| use a different model or API | a `Provider` subclass | framework |
| add a stance | a `Drive` in `build()` | this agent |
| reword how it understands itself | `_SELF_MODEL` (prose only — live facts are slots) | this agent |
| change ports, the stream, the loop, the window | framework — highest bar, discuss first | framework |

Adding an organ should be **one class and one line**. If your change needs framework edits to add a sense, that is a signal the model is missing something — raise it rather than working around it.

## Verifying a change

There is no test suite. What works:

- **Mock at the wire boundary only.** Subclass the shipped provider and override just `_call` to return scripted content blocks. Everything else — body, stream, units, interrupts, journal — runs for real, so a pass means the shipping code behaved. Needs no API key, no Telegram, no Docker.
- **Check the history** whenever you touch turns: opens on `user`, `tool_use` last, every id answered next, no harness prose in an assistant turn.
- **Then run it live** and read `~/.precognitive/trace.jsonl`. Several invariants exist because a change passed every structural check and still broke in conversation.
- **Probe the provider instead of trusting the docs.** Two invariants came from probes that contradicted a plausible reading of the documentation, which is silent on both.

Running it live starts a real agent that will message a real person and run commands. `~/.precognitive/` is durable state — a life, not a cache. Do not wipe it to "reset" without saying so; that destroys the agent's memory and its entire past.

## Traps

- **Do not "fix" the voice producing no reafference.** `DefaultOut` returns nothing on purpose: plain text reaches no one, so a fully-predicted act is cancelled as perception (`spec.md` §8). It looks like an omission and is not.
- **Do not "fix" `TimeSensor` having no pair.** Time is perceived and never acted upon. It is the one asymmetry in the body, and it is deliberate.
- **Do not add alternation padding.** Consecutive user turns are combined by the API. Inventing an assistant turn to balance a dangling user turn puts words in the model's mouth, which violates rule 2.
- **Do not convert the sliding window to token counting.** The lazy `prompt is too long` trigger is why no tokenizer or per-model constant is needed. The search is linear on purpose: a rejection is free, a success is billed, so a binary search pays for inference it discards.
- **Do not pass thinking blocks through without measuring.** The provider flattens thinking into `(reasoning) …` text because this API accepts thinking blocks back but does not feed them to the model. Native pass-through would look cleaner, pass every structural check, and silently destroy continuity of reasoning.
- **Watch what you paste.** The agent geolocated its own host and wrote the answer to memory. Redact `TELEGRAM_PEOPLE` ids and anything a shell result may have picked up.

## Style

Single file, dense, aligned end-of-line comments that say *why* rather than *what* — particularly where a line encodes something learned the hard way. Match the surrounding density rather than reformatting to your own preference. Do not split the file into modules; the single-file shape is a choice, and the two-half discipline is what keeps it navigable.
