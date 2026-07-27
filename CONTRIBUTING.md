# Contributing

Read [`spec.md`](spec.md) for the model and [`ARCHITECTURE.md`](ARCHITECTURE.md) for the machine. This document is only about *how to add to it*.

**Before anything else:** a change that contradicts the spec is a change to the spec. That is allowed — the spec has been wrong before — but say so explicitly in the PR and change `spec.md` in the same commit. Silent drift between the model and the code is the one thing this project cannot absorb.

---

## What there is to contribute to

The file is in two halves, and which half you are in determines what you may write.

| Part | You are adding | Half |
|---|---|---|
| **A sensor** | a new way the world reaches in, or a return path for a new actuator | this agent |
| **An actuator + its tool** | a new way to act — another person, another service, another machine | this agent |
| **A provider** | a different reasoning engine, or a different wire format | framework |
| **A drive** | a new stance the mind can take | this agent |
| **The identity** | how the self is worded to itself | this agent |
| **The framework** | ports, the stream, the loop, the window | framework — highest bar |

**The framework half never names an organ. This agent half never contains mechanism.** If you write `if actuator.name == "TelegramOut"` in the framework, stop: the design is telling you the distinction belongs somewhere else.

Most contributions should be an organ. Adding a sense or a reach is meant to be **one class and one line in `build()`** — if yours needs framework changes, that is worth discussing in an issue first, because it usually means the model is missing something.

---

## Add a sensor

```python
class WebhookIn(Sensor):
    drive = REACTIVE                    # REACTIVE · PROACTIVE · omit for a pure return path
    def __init__(self, port=None):
        super().__init__("WebhookIn", EXTERNAL, "HTTP webhooks from your services")
        self.port = port
    def status(self):                   # live state — generated into the body-schema
        return f"LISTENING on :{self.port}" if self.port else "not configured"
    def start(self, stream):            # world-facing sensors spawn a feed
        threading.Thread(target=self._serve, args=(stream,), daemon=True).start()
    def _serve(self, stream):
        ...
        stream.put(self.signal(payload, source="webhook"))
```

Then one line in `build()`. Its stance affinity, its entry in the self-model, its liveness line, and whether it can interrupt all follow from what you declared — **no prompt edits**, because the self-model is generated from the live body.

Choosing the drive:

- **`REACTIVE`** — another self is reaching in and may be waiting. Grants the power to interrupt.
- **`PROACTIVE`** — a reading of your own state: time, a resource, a condition. Fires in the gaps and can never interrupt.
- **omit** — a pure return path. It only ever stamps results; it faces nothing outward, so `signal()` on it is an error.

Two optional hooks: `perceived(scene)` to react to what arrived (this is how `TimeSensor` resets its backoff when a person speaks), and `resume(at)` to be told at wake when the life was last active, so your organ never asserts something false about the past.

## Add an actuator and its tool

Two classes: the **tool** is the capability, the **actuator** is the port on the membrane.

```python
class EmailTool(Tool):
    description = "Send an email. Result returns as predicted vs actual."
    schema = {"type": "object", "properties": {
        "to":      {"type": "string"},
        "body":    {"type": "string"},
        "expect":  {"type": "string", "description": "what you predict the reply/effect will be"}},
        "required": ["to", "body"]}
    def status(self):
        return f"READY — from {self.addr}" if self.addr else "not configured"
    def run(self, inp, should_stop=None):
        ...
        return f"(sent to {inp['to']})"

class EmailIn(Sensor):                  # where its results come home
    def __init__(self): super().__init__("EmailIn", EXTERNAL, "replies and delivery reports")

class EmailOut(Actuator):
    def __init__(self, pair): super().__init__("EmailOut", EXTERNAL, pair, tool=EmailTool())
```

Rules for tools:

- **Always include `expect`.** The prediction is what turns a result into something judgeable instead of merely received.
- **Stateless over immutable config.** Everything per-call lives in `inp` and locals. The executor may invoke your tool many times at once and will never serialize you; if you need serialization, hold your own lock (`BashTool` does, around container bring-up).
- **Cap what you return** (see `OUT_CAP`). One unbounded result can blow the whole window and leave the current unit unable to fit.
- **Name the recipient** if your actuator reaches a person. You speak to someone, not into a room, and errors should say who *is* reachable so the mind can correct itself.
- **Poll `should_stop()`** if you can run for a while, and return whatever you produced before dying.

Pick the pair's side deliberately — it decides what the return *feels* like. Internal is proprioception (you acted on the world and felt it inside); external is hearing yourself land out there.

## Add a provider

Implement one method:

```python
def respond(self, system, units, win, scene, specs, should_stop, notes=()) -> (acts, cut, win, fit)
```

The provider owns **everything** wire-shaped: rendering a scene into turns, recording the assistant turn, streaming, the overflow loop, and how thinking is handled.

That last one is provider-specific and must be **measured, not assumed**. The shipped provider flattens thinking into `(reasoning) …` text because DeepSeek *accepts* thinking blocks passed back but does not feed them to the model. Probe your provider before deciding: put a token only a returned thinking block could carry, then ask for it back.

Whatever you do, honour the invariants in `ARCHITECTURE.md` — particularly that `tool_use` is the last block of an assistant turn, and that no harness prose enters one.

## Add a drive

```python
Drive("repair", lambda sc: any(mismatched(s) for s in reafference(sc)),
      "A prediction of yours was wrong. Work out why before doing anything else.")
```

Drives are ordered and the first match wins; if none fires, the stance is unchanged because the mind is mid-exchange. Keep the wording short — it is the last band of the prompt, and it competes with everything above it. A drive that fires on every turn is not a stance, it is part of the identity.

## Change the identity

Authored prose may state the *model*. **Anything naming a live part must be a slot filled from the body** — organ lists, pairings, liveness, the reaching organ, paths, dates, window state. A hand-written organ list is a lie waiting for someone to add an organ.

And never tell it something it cannot check. An earlier version showed the agent its own source; it read a config variable, could not find it in the one shell it can reach, and concluded it could message nobody — which was false. Self-knowledge comes from the body-schema, which it can verify by acting.

---

## Testing your change

There is no test suite in the repository. Verify against the real thing:

1. **Wire a mock at the boundary, not in the middle.** Subclass the shipped provider and override only its `_call` to return scripted blocks. Everything else — body, agent, units, interrupts, journal — then runs for real, so a pass means the shipping code did the thing. No API key, no Telegram, no Docker needed.
2. **Run the history through a validity check** whenever you touch turns: opens on `user`, `tool_use` last in its assistant turn, every id answered in the next message, no harness prose in an assistant turn.
3. **Then run it live** and read `~/.precognitive/trace.jsonl`. Several of the invariants exist because something passed structural checks and still went wrong in a conversation.
4. **Probe the provider** rather than trusting the docs. Two of the invariants came from probes that contradicted a plausible reading, and the documentation is silent on both.

## Pull requests

- One organ, or one framework change, per PR.
- Say which half you touched and why it had to be that half.
- If you changed anything the agent reads about itself, paste the rendered self-model section.
- Include a trace excerpt for behavioural changes. `grep '"unit": N' trace.jsonl` pulls one complete exchange.
- **Redact before pasting.** `TELEGRAM_PEOPLE` ids, anything a `BashOut` result picked up. The agent has been known to geolocate its own host and write the answer to memory.

## Style

Single file, dense, aligned comments that say *why* rather than *what* — especially where a line encodes something learned the hard way. Match the surrounding density rather than your own preference. Keep the framework half organ-free.
