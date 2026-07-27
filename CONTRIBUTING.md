# Contributing

Read [`spec.md`](spec.md) for the model and [`ARCHITECTURE.md`](ARCHITECTURE.md) for the machine. This document is only about *how to add to it*.

**Before anything else:** a change that contradicts the spec is a change to the spec. That is allowed — the spec has been wrong before — but say so explicitly in the PR and change `spec.md` in the same commit. Silent drift between the model and the code is the one thing this project cannot absorb.

---

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install anthropic     # the only dependency
cp .env.example .env                                          # then fill it in
.venv/bin/python precog.py
```

`~/.precognitive/` is **durable state — a life, not a cache.** Do not wipe it to "reset"; that destroys the agent's memory and its entire past.

To develop against a clean slate, construct the `Agent` with `trace_path` pointed at a scratch file, or `trace_path=None` for a fully ephemeral run. **Do not try to reassign `STATE_DIR`** — `MEMORY_PATH` and `TRACE_PATH` are built from it at import, so they go on pointing at the real life while only the container mount moves.

Running it live starts a real agent that will message a real person and run real commands.

---

## What there is to contribute to

The file is in two halves, split at the `—— THIS AGENT ——` banner, and which half you are in determines what you may write.

| Part | You are adding | Half |
|---|---|---|
| **A sensor** | a new way the world reaches in | this agent |
| **An actuator + its tool + its paired sensor** | a new way to act, and where its result comes home | this agent |
| **A provider** | a different reasoning engine, or a different wire format | framework |
| **A drive** | a new stance the mind can take | this agent |
| **The identity** | how the self is worded to itself | this agent |
| **The framework** | ports, the stream, the loop, the window | framework — highest bar |

**The framework half never names an organ. This agent half never contains mechanism.** If you write `if actuator.name == "TelegramOut"` in the framework, stop: the design is telling you the distinction belongs somewhere else.

Most contributions should be an organ. A sensor is **one class and one line in `build()`**; an actuator pair is three small classes and three lines. If yours needs framework changes to add a sense or a reach, open an issue first — that usually means the model is missing something.

---

## Every sensor declares one of three things

This is the rule that keeps stance and interruption coherent, so get it right before you write anything.

| The sensor faces | `drive` | What its arrivals do |
|---|---|---|
| the world, and someone is waiting on you | `REACTIVE` | opens a reactive turn · **may interrupt** the turn in progress |
| the world, but nothing is waiting | `PROACTIVE` | opens a proactive turn in the gaps · can never interrupt |
| nothing — it is a return path for an actuator | **unset** (the bypass) | only ever stamps results; reframes nothing, interrupts nothing |

A sensor may be *both* — `TelegramIn` hears people (`REACTIVE`) and is also `TelegramOut`'s return path.

**The bypass is a property of the signal, not the sensor.** `Sensor.reafferent()` stamps `origin="self"` and leaves `drive` unset on the signal it makes, and the two gates downstream both key on `origin`:

```python
def stance(self, scene):            # only origin == "world" can reframe a turn
def put(self, sig):                 # only origin == "world" and drive == REACTIVE can interrupt
```

So reafference flows home through *any* pair sensor without touching the drive — including through a `REACTIVE` one. Your own hand returning is the middle of a thought, not news, and it can never seize a moment it is already serving. You do not have to arrange this; you only have to not fight it.

Leaving `drive` unset on a pure return path buys one more thing: `Sensor.signal()` asserts `drive is not None`, so a return path *physically cannot* manufacture a world arrival.

---

## Recipe: add a sensor

```python
class WebhookIn(Sensor):
    drive = REACTIVE                    # REACTIVE · PROACTIVE · omit for a pure return path
    def __init__(self, port=None):
        super().__init__("WebhookIn", EXTERNAL, "HTTP webhooks from your services")
        self.port = port
    def status(self):                   # live state — generated into the body-schema
        return f"LISTENING on :{self.port}" if self.port else "not configured"
    def start(self, stream):            # world-facing sensors spawn their own feed
        threading.Thread(target=self._serve, args=(stream,), daemon=True).start()
    def _serve(self, stream):
        ...
        stream.put(self.signal(payload, source="webhook"))     # `source` becomes the [tag · time]
```

Then one line in `build()`:

```python
body = Body(sensors=[tg_in, default_in, bash_in, TimeSensor(), WebhookIn(port=8080)], tools=registry)
```

Its stance affinity, its entry in the self-model, its liveness line, and whether it can interrupt all follow from what you declared — **no prompt edits**, because the self-model is generated from the live body every cycle.

Two optional hooks:

- `perceived(scene)` — react to what arrived. This is how `TimeSensor` resets its backoff when a person speaks.
- `resume(at)` — at wake you are told when the life was last active (`None` if newborn), so your organ never asserts something false about the past. This hook exists because `TimeSensor` once announced "your first moment" after a nine-hour sleep and the agent doubted its own memory for four hours.

---

## Recipe: add an actuator, its tool, and its paired sensor

**A new way to act is not complete until its result has somewhere to come home.** This is the pairing, and it is what makes reafference physical rather than notional — the whole reason the *-ceptions* are emergent instead of built. Three classes, in this order:

```python
# 1 — the return path. Where this actuator's results re-enter as perception.
class EmailIn(Sensor):
    # drive unset: nothing in the world pushes here. A pure return path — it only stamps results.
    def __init__(self):
        super().__init__("EmailIn", EXTERNAL,
                         "the return from a sent email — the delivery, or why it failed")

# 2 — the capability. Stateless over immutable config.
class EmailTool(Tool):
    description = "Send an email to a person by name. Result returns as predicted vs actual."
    schema = {"type": "object", "properties": {
        "to":     {"type": "string", "description": "who to send it to, by name"},
        "body":   {"type": "string"},
        "expect": {"type": "string", "description": "what you predict the reply or effect will be"}},
        "required": ["to", "body"]}
    def __init__(self, addr, people):
        self.addr, self.people = addr, dict(people)          # immutable — set once, never mutated
        self.by_name = {v.lower(): k for k, v in self.people.items()}
    def status(self):                                        # liveness, into the body-schema
        return f"READY — you can reach: {', '.join(self.people.values())}" if self.addr else "not configured"
    def run(self, inp, should_stop=None):
        who = (inp.get("to") or "").strip().lower()
        if who not in self.by_name:
            return f"(no recipient — name one of: {', '.join(self.people.values())})"
        ...
        return f"(sent to {self.people[self.by_name[who]]})"

# 3 — the port on the membrane. It HAS-A tool; it is not one.
class EmailOut(Actuator):
    def __init__(self, addr, people, pair):
        super().__init__("EmailOut", EXTERNAL, pair, tool=EmailTool(addr, people))
```

Three lines in `build()` — and **the sensor must go into `Body(sensors=…)`**, not only into the actuator:

```python
email_in = EmailIn()
registry = ToolRegistry([DefaultOut(pair=default_in),
                         TelegramOut(TG_TOKEN, TG_PEOPLE, pair=tg_in),
                         BashOut(pair=bash_in),
                         EmailOut(EMAIL_ADDR, EMAIL_PEOPLE, pair=email_in)])
body = Body(sensors=[tg_in, default_in, bash_in, email_in, TimeSensor()], tools=registry)
```

Reafference will route correctly either way, because `Body._reaff` reaches the pair through the actuator. But an unregistered sensor never gets `start()`, `perceived()`, or `resume()`, and — worse — it will be **missing from the body-schema**, so the agent will not know it has the organ. That is the one mistake in this recipe that produces a working agent with a false self-model.

### Choosing the pair's side — this is the design decision

The returning result takes **the pair sensor's side**, not the actuator's. That choice is what the return *feels* like:

| act side → pair side | Emerges as | Shipped example |
|---|---|---|
| external → **internal** | proprioception — you acted on the world and felt it inside | `BashOut` → `BashIn` |
| external → **external** | external self-perception — you hear your own words land out there | `TelegramOut` → `TelegramIn` |
| internal → internal | introspection | — |
| internal → external | an internal act made outwardly observable | — |

Nothing in the framework distinguishes these. They are all one call to `pair.reafferent(...)`; only the side differs, and the *-ception* is a view you can compute afterwards. Pick the side that is true, not the one that is convenient.

### Rules for tools

- **Always include `expect`.** The prediction is what turns a result into something judgeable instead of merely received. Its value is copied onto the act signal and comes back as `predicted · actual`.
- **Stateless over immutable config.** Everything per-call lives in `inp` and locals. The executor runs up to 8 acts at once (`max_workers=8`) and will never serialize you; if you need serialization, hold your own lock (`BashTool` does, around container bring-up).
- **Cap what you return** (see `OUT_CAP` — 8000 *characters*, compared with `len()` on the decoded string). One unbounded result can blow the whole window and leave the current unit unable to fit — the only unrecoverable state in the system.
- **Name the recipient** if your actuator reaches a person, and on failure say who *is* reachable, so the mind can correct itself rather than concluding it can reach nobody.
- **Poll `should_stop()`** if you can run for a while, and return whatever you produced before dying. A killed act still owes an answer.

---

## Recipe: add a provider

One method, and it owns **everything** wire-shaped: rendering a scene into turns, recording the assistant turn, streaming, the overflow loop, and how thinking is handled.

```python
def respond(self, system, units, win, scene, specs, should_stop, notes=()) -> (acts, cut, win, fit)
```

Subclass `Provider` (or subclass `AnthropicProvider` and override less). Whatever you do:

- **`tool_use` must be the last block of an assistant turn**, by construction rather than discipline.
- **No harness prose in an assistant turn** — it records what the model produced, nothing else. Everything the harness has to say goes in the next `user` turn.
- **Every `tool_use` gets answered** in the immediately following message.
- **Thinking policy must be measured, not assumed.** The shipped provider flattens thinking into `(reasoning) …` text because DeepSeek *accepts* thinking blocks passed back but does not feed them to the model. Probe yours: put a token that only a returned thinking block could carry, then ask for it back. Native pass-through would look cleaner, pass every structural check, and silently destroy continuity of reasoning.

The rest of the invariants are in [`ARCHITECTURE.md`](ARCHITECTURE.md#invariants).

---

## Recipe: add a drive

A drive is a name, a predicate over the scene, and a band of prompt. They are ordered, **the first match wins**, and if none fires the stance is unchanged because the mind is mid-exchange.

```python
drives = [
    Drive("summoned", lambda sc: any(s.source == "Chase" for s in opens(sc)),
          "Chase is speaking — the person who maintains you. Attend to this before anything else."),
    Drive(REACTIVE,  lambda sc: any(s.drive == REACTIVE  for s in opens(sc)), "…"),
    Drive(PROACTIVE, lambda sc: any(s.drive == PROACTIVE for s in opens(sc)) and not reafference(sc), "…"),
]
```

Order is the whole design: `summoned` must precede the generic reactive drive or it can never fire.

- **Predicate over `opens(scene)`, not `scene`.** Filtering to `origin == "world"` is what keeps your own hand returning from reframing the turn.
- **Keep the wording short.** It is the last band of the prompt and it competes with everything above it.
- **A drive that fires every turn is not a stance** — it is part of the identity, so put it there instead.
- **Do not build a drive that mechanically compares `predicted` against `content`.** By `spec.md` §8 the mind is the comparator; an external divergence metric moves judgment out of the only thing qualified to make it.

---

## Recipe: change the identity

Authored prose may state the *model*. **Anything naming a live part must be a slot filled from the body** — organ lists, pairings, liveness, the reaching organ, paths, dates, window state. A hand-written organ list is a lie waiting for someone to add an organ.

And never tell it something it cannot check. An earlier version showed the agent its own source; it read a config variable, could not find it in the one shell it can reach, and concluded it could message nobody — which was false. Self-knowledge comes from the body-schema, which it can verify by acting.

If you change anything the agent reads about itself, paste the rendered section in the PR. `build()` requires `DEEPSEEK_API_KEY` to be set even though nothing here calls the API, so pass a dummy:

```bash
DEEPSEEK_API_KEY=- .venv/bin/python -c "import precog as P; a=P.build(); \
print(a.identity.render(a.body.describe(), {'when': P.now().date(), 'window': a.window()}))"
```

---

## Testing your change

There is no test suite in the repository. Verify against the real thing, in this order:

1. **Mock at the wire boundary, not in the middle.** Subclass the shipped provider and override only `_call` to return scripted content blocks. Everything else — body, agent, units, interrupts, journal — then runs for real, so a pass means the shipping code did the thing. Needs no API key, no Telegram, no Docker.
2. **Run the history through a validity check** whenever you touch turns: opens on `user`, `tool_use` last in its assistant turn, every id answered in the next message, no harness prose in an assistant turn.
3. **Then run it live** and read `~/.precognitive/trace.jsonl`. Several invariants exist because a change passed every structural check and still broke in conversation.
4. **Probe the provider** rather than trusting the docs. Two invariants came from probes that contradicted a plausible reading of documentation that is silent on both.

---

## Pull requests

### Before you open one

- **Open an issue first** for anything in the framework half, anything that changes the wire format, and anything that needs a new field on `Signal`. Organ PRs need no issue.
- One organ, or one framework change, per PR. Two organs is two PRs.
- Rebase on `main`; keep the history readable. Commit subjects state the *why* where it is not obvious — `fix: bash can't find docker (kernel PATH), not a Docker outage` beats `fix: docker`.

### What the PR body must contain

- **Which half you touched, and why it had to be that half.**
- **Whether the spec still holds.** If your change contradicts `spec.md`, say so and amend the spec in the same PR.
- **For an organ:** its side, its drive (or that it is a bypass), and its pair — plus what the pairing makes the return *feel* like.
- **The rendered self-model section**, if the agent's view of itself changed.
- **A trace excerpt** for anything behavioural. `grep '"unit": N' ~/.precognitive/trace.jsonl` pulls one complete exchange.
- **How you verified it**, naming which of the four levels above you reached.

**Redact before pasting.** `TELEGRAM_PEOPLE` ids, hostnames, IPs, anything a `BashOut` result picked up. The agent has been known to geolocate its own host and write the answer to memory. Never paste an API key or bot token; if one appears in a trace excerpt you are pasting, rotate it.

### How it gets reviewed

Expect three passes, roughly in this order — a PR usually comes back on the first two before anyone discusses the third:

1. **Structural.** Which half did you touch? Does the framework name an organ? Does the organ contain mechanism? Is it one class and one line, or did it need framework edits? A PR that needed framework edits to add a sense gets converted into a design discussion rather than merged, because that is a signal the model is missing something.
2. **Invariants.** The eight in [`ARCHITECTURE.md`](ARCHITECTURE.md#invariants), checked against the diff — especially block ordering in any assistant turn, whether every `tool_use` can still be answered on every path (including the interrupt and wake paths), whether anything naming a live part got authored instead of generated, and whether the agent is now told something it cannot verify.
3. **Behaviour.** Your trace excerpt, read as a conversation rather than as a structure. Does the agent's own record still say something true about what happened? This is the pass that catches the changes that are correct and still wrong — a label that makes it believe it reached someone it did not, a drive that fires so often it becomes the identity, a result that returns on the wrong side of the membrane.

What gets sent back, most common first: harness prose that ended up in an assistant turn; a live fact hand-written into the prompt; a new actuator with no paired sensor, or with a pair that was never registered on the body; a tool with mutable per-call state; an unbounded result; a framework branch on an organ name.

---

## Style

Single file, dense, aligned end-of-line comments that say *why* rather than *what* — especially where a line encodes something learned the hard way. Match the surrounding density rather than reformatting to your own preference. Do not split the file into modules; the single-file shape is a choice, and the two-half discipline is what keeps it navigable.
