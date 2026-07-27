# CLAUDE.md

Guidance for coding agents working in this repository. Read this whole file before changing `precog.py`.

## What this is

`precog.py` is a single-file embodied LLM agent. **It is not a chat loop with tools attached, and reading it as one will cause you to make wrong changes.** The premise, stated in [`spec.md`](spec.md): *a self is a body of sensors and actuators wired across a membrane.* Signals enter through sensors, cross to a mind, leave through actuators, and an act's result comes home *through the sensor paired to that actuator*. Afference, efference, and reafference are the actual control flow, not vocabulary layered on top.

Read in this order: [`spec.md`](spec.md) (the model) → [`ARCHITECTURE.md`](ARCHITECTURE.md) (the machine, with diagrams) → `precog.py` → [`CONTRIBUTING.md`](CONTRIBUTING.md) (the recipes and the review process).

```
precog.py       the whole agent, in two halves
spec.md         the canonical model — the code is an implementation of it
ARCHITECTURE.md components, dataflow diagrams, execution flow, persistence, invariants
CONTRIBUTING.md how to add a sensor, an actuator pair, a provider, a drive; how PRs are reviewed
README.md       what it is, what it does, quickstart
.env.example    configuration
```

Sections inside `precog.py` are numbered and dependencies only point upward:

```
§0 CONFIG      §1 SIGNAL      §2 AFFERENCE   §3 PORTS
§4 DRIVE       §5 PROVIDER    §6 IDENTITY    §7 BODY      §8 AGENT
—— THIS AGENT ——  organs · the self-model · build()
```

**The framework half (§0–§8) never names an organ. The THIS AGENT half never contains mechanism.** This is the single most important structural rule. If you are about to write `if actuator.name == "TelegramOut"` in the framework, the correct change is somewhere else.

---

## How the system works

Enough to change it safely. `ARCHITECTURE.md` has the diagrams; this is the mechanism.

### One currency, and three gates on one field

Everything that moves is a `Signal` (`precog.py:122`). Ten fields, but two of them do the routing work — `origin` (`world` | `self`) and `ref` — and they gate different things. `origin` is read at six sites:

| `origin` decides | How | Where |
|---|---|---|
| can it reframe the turn? | drives filter through `opens()` — `origin == "world"` | `:136`, via `stance()` `:538` |
| can it interrupt? | `Afference.put` counts only `origin == "world" and drive == REACTIVE` | `:156` |
| …and un-counts on drain | the same predicate, decrementing | `:167` |
| is it a beat to coalesce? | `origin == "world" and drive == PROACTIVE` | `:176` |
| is it reafference? | `reafference()` — `origin == "self"` | `:137` |
| can it say "quit"? | only a world signal stops the loop | `:550` |

**`ref`, not `origin`, decides how a signal renders.** `_render` (`precog.py:302`) branches on `s.ref is not None` → `tool_result`, else a text block; it never reads `origin` at all. The two correlate in practice — world signals carry no `ref` — but if you add a code path that sets one without the other, rendering follows `ref`.

`Sensor.reafferent()` (`precog.py:199`) stamps `origin="self"` and leaves `drive` unset, so **reafference bypasses stance and interruption automatically — even through a `REACTIVE` sensor** like `TelegramIn`. The bypass is a property of the signal, not of the sensor. Nothing needs to arrange it; do not add machinery that re-implements it.

`opens()` and `reafference()` (`precog.py:136`) are one-line queries over that field, and the *-ceptions* in `spec.md` §7 are the same kind of query. **Never reify one as a class or a stored flag.**

### The cycle, in exact order

`Agent.step()` (`precog.py:548`) is the whole life. One pass:

```
1  scene = body.perceive()                                            :441
     drain the queue; if empty, BLOCK on get(timeout=WATCHDOG), then drain
     coalesce beats — interoception is level-triggered, one beat per source   :173
     sensor.perceived(scene) for every organ  ← the clock rearms here
2  quit check: a WORLD signal whose content is "quit"/"exit"           :550
3  system = identity.render(body.describe(), {when, window}) + stance(scene)
     body.describe() REGENERATES organs, statuses, pairings, reach every cycle
     the stance band goes LAST — the volatile text nearest the model
4  notes, self.notes = self.notes, []      ← anything owed, delivered in THIS user turn
5  acts, cut, win, fit = provider.respond(...)                         :276
     render the scene into ONE user turn; open a new unit, or extend the current one
     while "prompt is too long": win += 1, retry   ← drop the OLDEST unit
     record the assistant turn IF the model produced anything          :351
6  journal the new turns under their unit id — or discard an empty beat :566
7  cut ?  enact(voice only) + abort(ref-bearing acts) + owe CUT_NOTE
   else:  enact(all acts, interrupting); if still interrupting → owe CUT_NOTE
8  _trim() — bound RAM, but never into the live view                    :584
```

Acts run concurrently in an 8-thread pool (`Body.enact`, `precog.py:450`) and results are put back **in submission order**, so `tool_result` blocks mirror the order of the `tool_use` blocks that caused them.

Because a result re-enters the same queue a sensor feeds, **an act chains straight into the next cycle** — the queue is non-empty, so there is no wait. Only silence reaches the beat. The agent free-runs while it is doing something, and time appears when it stops.

### The three roles are the membrane

```
system     = the standing self   → identity + generated body-schema + one stance band
user       = AFFERENCE           → exafference (text) + reafference (tool_result) + harness notes
assistant  = EFFERENCE           → (reasoning) + (thought — no one heard this) + tool_use*
```

`user` is everything the model receives; `assistant` is everything it produced. That correspondence is *why* rule 2 exists. Every harness sentence in the file lives in `_render` (`precog.py:302`); `_record` (`precog.py:351`) contains none.

### Units and the window

```python
def opens_unit(turn):     # precog.py:140
    return turn["role"] == "user" and not any(b.get("type") == "tool_result" for b in turn["content"])
```

A **unit** is the run of messages from one `tool_result`-free user turn to just before the next — a moment when nothing was pending. It is provably the smallest slice the Messages API permits **with no rewriting**: cut anywhere else and you either open the array on an assistant turn or orphan a `tool_result`. So `flatten(units, win)` (`precog.py:382`) is a verbatim suffix of the record.

Everything held is sent; each `prompt is too long` drops the oldest unit and retries. The search is **linear, never binary** — a rejection is free, a success is billed. The current unit is never evictable; if it alone will not fit, `respond` raises, and `OUT_CAP` exists to keep that unreachable.

One consequence worth knowing: an interrupt produces a mixed scene (synthetic results **+** the interrupting message), which contains `tool_result` blocks, so it *extends* the current unit rather than opening one. The interrupted episode and the message that interrupted it are therefore evicted together — correct, since neither makes sense alone.

### Persistence, wake, interruption

```
~/.precognitive/
├── trace.jsonl        one life, append-only, one line per message, tagged with its unit
└── memory/memory.md   what the agent chose to distil — the agent writes this, with bash
```

The agent **reads either layer and writes only `memory.md`**. Both are UTC (`precog.py:601`) because they were not once: memory was stamped inside a UTC container while the harness journalled local time, and across a date rollover the cross-layer join silently found nothing.

Wake (`_wake`, `precog.py:498`) reads the tail backwards — O(tail), never O(life) — regroups by recorded unit id, discards a leading partial unit, `heal`s any dangling `tool_use`, positions the window from the remembered fit, and tells every organ when the life was last active.

Interruption is a pending reactive arrival and nothing else. The counter rises in `put`, and the same `interrupting` callable is handed to the stream loop (`precog.py:327`) and to any long-running tool (`precog.py:815`). Neither knows what a keyboard is. On a cut the partial thought is kept, a killed command keeps its partial output, acts that never ran get synthetic results, and `CUT_NOTE` is **owed** — delivered in the next *user* turn, never written into the assistant turn.

### What changes cycle over cycle

| | Changes when | Bound |
|---|---|---|
| `units` | a world arrival opens one; reafference extends the newest | `BUFFER=150`, trimmed only outside the view |
| `unit_no` | a new unit opens — a continuing episode keeps its id | — |
| `win` | the provider rejects the prompt | `< len(units)` |
| `fit` | every `respond` returns it | persisted on the `wake` row |
| `notes` | a turn was cut | drained into the next user turn |
| `_pending` | a reactive signal is enqueued | back to 0 when drained |
| `TimeSensor.beats` | each beat; reset by `arouse()` on a reactive arrival | interval capped at `TICK_MAX` (1800s) |

---

## Rules that are not style preferences

Each exists because violating it produced a real failure. Treat them as load-bearing.

1. **`tool_use` must be the last block of an assistant turn.** Anything after it makes the API treat the call as unanswered *even when the `tool_result` is present in the next message* (probed: `[text,tool_use]` → 200, `[text,tool_use,text]` → 400). Enforced by construction in `_record`; do not reintroduce a code path that can append after it.
2. **Harness text never enters an assistant turn.** That turn records what the model produced. Source tags, `predicted · actual`, synthetic results, cut notes — all belong to the `user` turn. If the model produced nothing, append **no turn**; consecutive user turns are combined by the API.
3. **Every `tool_use` gets answered** — real result, interrupt synthetic, or wake heal. This is what keeps the unit boundary reliable, which is what keeps the sliding window valid.
4. **The trace only grows.** Sliding moves an index. The view must be a verbatim suffix of the record — never rebuild it, never fabricate a turn to make it fit.
5. **Never drop a turn that perceived exafference** — anything with `origin == "world"` other than a bare beat. The record is the only copy; the signal was already taken off the queue. Be precise here: a `TimeSensor` beat *is* `origin == "world"` (verified — it is `side == "internal"`, interoception rather than the world reaching in), and the empty-beat discard drops exactly that and nothing else. State the rule on the beat, not on `origin` alone, or the discard reads as a violation. See Traps.
6. **Only reactive world signals interrupt.** Not the clock, not reafference.
7. **Anything naming a live part is generated, never authored** — organs, pairings, liveness, paths, dates. A hand-written organ list in the prompt goes stale the moment someone adds an organ.
8. **Never give the agent information it cannot verify.** An earlier version showed it its own source; it read a config variable, failed to find it in the one shell it can reach, and concluded it could message nobody — which was false. Self-knowledge comes from the generated body-schema, which it can check by acting.

---

## Where changes go

| You want to | Change | Half |
|---|---|---|
| add a way the world reaches in | a `Sensor` subclass + one line in `build()` | this agent |
| add a way to act | a `Tool`, an `Actuator` fronting it, **and its paired return `Sensor`** | this agent |
| use a different model or API | a `Provider` subclass | framework |
| add a stance | a `Drive` in `build()` | this agent |
| reword how it understands itself | `_SELF_MODEL` (prose only — live facts are slots) | this agent |
| change ports, the stream, the loop, the window | framework — highest bar, discuss first | framework |

Adding an organ should be **one class and one line** (an actuator pair: three small classes, three lines). If your change needs framework edits to add a sense, that is a signal the model is missing something — raise it rather than working around it.

**A new actuator without a paired sensor is an incomplete change, not a smaller one.** The pairing is what makes reafference physical, and the pair's *side* is the design decision — external→internal is proprioception, external→external is hearing yourself land. `CONTRIBUTING.md` has the full recipe and that table. Register the new sensor on `Body(sensors=…)` too, not only on the actuator: reafference routes either way, but an unregistered sensor is missing from the body-schema, which gives the agent a false self-model.

---

## Working in this repository

```bash
.venv/bin/python precog.py                                                        # live

# inspection. build() reaches os.environ["DEEPSEEK_API_KEY"] and raises KeyError without it,
# so pass a dummy — nothing here calls the API. It reads the trace but writes nothing.
DEEPSEEK_API_KEY=- .venv/bin/python -c "import precog as P; print(P.build().body.describe())"
DEEPSEEK_API_KEY=- .venv/bin/python -c "import precog as P; a=P.build(); \
  print(a.identity.render(a.body.describe(), {'when': P.now().date(), 'window': a.window()}))"
```

**Verification, in order of what it proves:**

1. **Mock at the wire boundary only.** Subclass the shipped provider and override just `_call` to return scripted content blocks. Everything else — body, stream, units, interrupts, journal — runs for real, so a pass means the shipping code behaved. Needs no API key, no Telegram, no Docker.
2. **Check the history** whenever you touch turns: opens on `user`, `tool_use` last, every id answered next, no harness prose in an assistant turn.
3. **Then run it live** and read `~/.precognitive/trace.jsonl`. Several invariants exist because a change passed every structural check and still broke in conversation.
4. **Probe the provider instead of trusting the docs.** Two invariants came from probes that contradicted a plausible reading of documentation that is silent on both.

`~/.precognitive/` is **durable state — a life, not a cache.** Do not wipe it to "reset" without saying so; that destroys the agent's memory and its entire past.

For a clean slate, pass `trace_path=<tmp>` or `trace_path=None` to `Agent`. **Reassigning `STATE_DIR` at runtime does not work and is worse than doing nothing:** `MEMORY_PATH` and `TRACE_PATH` are concatenated from it at import (`precog.py:66-68`), so they keep pointing at the real life, while `BashTool._up` *does* read `STATE_DIR` at call time — you would get a container mounted somewhere new and an agent still writing its real trace and memory.

Running it live starts a real agent that will message a real person and run commands. **Watch what you paste** into a PR, an issue, or a conversation: redact `TELEGRAM_PEOPLE` ids, hostnames, IPs, and anything a `BashOut` result picked up. The agent has geolocated its own host and written the answer to memory. Never paste an API key or bot token.

---

## Traps

Things that look like bugs and are not. Do not "fix" these.

- **The voice produces no reafference.** `DefaultOut` *does* have a pair (`DefaultIn`), but it is native, so its acts carry `ref=None` and `Body._run` returns `None` before the result is ever used (`precog.py:462`). Plain text reaches no one, so a fully-predicted act is cancelled as perception (`spec.md` §8). `DefaultOut.native()` returning `"(voiced)"` is dead by construction — design, not oversight.
- **`TimeSensor` has no pair.** Time is perceived and never acted upon. It is the one asymmetry in the body, and it is deliberate.
- **An empty beat is discarded.** `step()` pops the unit when the model produced no acts on a pure beat (`precog.py:570`), guarded by four conditions so it can never reach anything older or anything that perceived a person. Without it a quiet night deposits dozens of empty units into the trace and the window. Accepted consequence: a beat where the model only *thought* loses that thinking.
- **Do not add alternation padding.** Consecutive user turns are combined by the API. Inventing an assistant turn to balance a dangling user turn puts words in the model's mouth, which violates rule 2.
- **Do not convert the sliding window to token counting.** The lazy `prompt is too long` trigger is why no tokenizer or per-model constant is needed. The search is linear on purpose: a rejection is free, a success is billed, so a binary search pays for inference it discards.
- **Do not pass thinking blocks through without measuring.** The provider flattens thinking into `(reasoning) …` text because this API accepts thinking blocks back but does not feed them to the model. Native pass-through would look cleaner, pass every structural check, and silently destroy continuity of reasoning.
- **`_parse` dropping an id-less `tool_use` is load-bearing** (`precog.py:347`). A cut mid-block can produce one; it would be recorded but never answerable, because `Signal.act` would carry `ref=None` and `_run` would treat it as the voice.
- **`show()` garbling multi-line output is a terminal artifact**, not a harness bug — byte-level truncation under the char-by-char thinking stream. `flat()` already collapses newlines to `⏎`.

## Known seams

Real, minor, currently accepted. Leave them unless asked, and do not document them as features.

- **The persisted `fit` is measured early.** `_open` writes the `wake` row lazily on the first journal, so `fit` is whatever the *first* cycle of the session fit; `_wake` reads only `wake` rows (`precog.py:504`) and ignores the `fit` carried on every `slide` row. A session that slid from 5 units to 2 persists 5, and the next wake re-pays those slides. Costless — rejections are free.
- **The watchdog path can build an empty user turn.** If every sensor thread dies, `get(timeout=WATCHDOG)` returns `None`, `drain` yields `[]`, and `_render` returns `[]`. Unreachable while `TimeSensor` lives (`TICK_MAX` 1800s < `WATCHDOG` 3600s).
- **`voice="DefaultOut"` is a constructor default in the framework half** (`precog.py:269`) — an injection point rather than a branch on identity, but it is an organ name above the line.

---

## Style

Single file, dense, aligned end-of-line comments that say *why* rather than *what* — particularly where a line encodes something learned the hard way. Match the surrounding density rather than reformatting to your own preference. Do not split the file into modules; the single-file shape is a choice, and the two-half discipline is what keeps it navigable.

Line references above point at `precog.py` as committed; re-grep rather than trusting them once the file moves.
