# The Model — A Self Is a Body of Sensors and Actuators

The canonical specification of the agent model: what a self is, how it is built, and
why it constitutes a being in a world. Everything else (the framework, the notebook,
the code) is an implementation of this.

---

## 1. A body is exactly two kinds of parts

- **Sensors** — afferent ports; signals come **in** through them.
- **Actuators** — efferent ports; signals go **out** through them.

That is all there is. No "senses", no "-ceptions", no "channels" as primitives —
**only sensors and actuators.**

## 2. Every port is wired to one side of the membrane

Each sensor and each actuator sits on **internal** or **external**. The membrane
(internal ↔ external) is the **body boundary** — the line between self and world.

A port's only stored properties are:

- its **direction** — sensor (afferent) or actuator (efferent),
- its **side** — internal or external, and
- for an actuator, its **pair** — the sensor its result returns through.

The pair is what makes reafference physical rather than notional. An act does not
"return a value"; it comes home through a named sensor, and *that sensor's side* is
what decides the flavor of the return (§7). Acting on the machine and feeling it
inside is one pairing; speaking and hearing your own words land is another. A sensor
may be purely a return path, facing nothing outward at all.

**One sensor has no pair: time.** Time can be perceived and never acted upon, so it
is afferent-only — the single asymmetry in the body, and it is a real one.

## 3. Signals are the only currency

Everything that crosses a port is a **Signal**, carrying:

- `content` — the payload,
- `side` — internal or external,
- `origin` — **world** or **self**: whether it came from outside or was caused by one of
  your own acts. This single field is what separates exafference from reafference (§7),
  and it is what decides whether a signal can reframe a turn (§9) or interrupt one (§10).
- `source` — the port it came through,
- `drive` — for a signal from the world, which kind of turn its source opens (§9). A
  self-caused signal carries none, and that absence is why reafference reframes nothing
  and interrupts nothing — it is the middle of a thought, not news.
- `predicted` — for a self-caused signal, the **efference copy**: what the acting mind
  predicted the result would be, so the return can be judged against it (see §8).

Sensors emit signals; actuators emit signals (as their results); the mind consumes and
emits signals. Nothing else moves.

## 4. The loop

```
sensors ─▶ signals (in) ─▶ [ LLM call ] ─▶ signals (out) ─▶ actuators
                ▲                                                │
                └──────── an actuator's result re-enters ────────┘
                          as a signal (origin = self)
```

Sensors transduce what they face into input signals. The mind (one LLM call) perceives
them and emits output signals. Those drive actuators. An actuator's result becomes a
signal again and re-enters the input stream — closing the loop.

## 5. The local voice is native; reaching a remote self is willed

The model's outputs split by **reach**, and this is the resolution of a real tension: a
chat model is *trained to respond in plain text*, so fighting that (making plain text
"private") mis-files the mind's most natural act. Instead:

- Its **plain text is its voice** — spoken **aloud** through a **local voice actuator**
  (the body always voices its plain text; the articulation of one's *own* voice is
  native, not a willed decision). It is *voiced*, not private — but a **local** voice does
  not reach a **remote** self.
- Its **thinking is private** — retained as the mind's remembered reasoning and returned
  each cycle for continuity (never re-perceived as afference — §8).
- Its **tool calls** are its **willed acts** — reaching across distance to another self
  (`telegram`, email, …) or acting on the machine (`bash`) is a *decision*. **Every
  crossing to a remote other is a tool call**; each carries a prediction and returns as
  reafference.

The asymmetry is the point: **your own mouth moves when you speak (native); phoning
someone is a choice (willed).** So the local voice is a hardcoded output *within the local
membrane*, while every reach to a remote self is a willed act — honoring both the model's
training and the membrane principle. The body defines which sensors/actuators exist and
where they are wired; the mind picks the routing each turn.

## 6. Any wiring is possible

Because sensors and actuators each independently sit internal or external, every
combination is valid — and it is purely a wiring choice:

| input (sensor) | → | output (actuator) |
|---|---|---|
| internal | → | internal |
| external | → | external |
| internal | → | external |
| external | → | internal |

## 7. The -ceptions are emergent, never built

From `{sensor \| actuator} × {internal \| external}` plus `origin`, everything else is a
**view you compute**, not an organ you build:

- **Exteroception** = afferent signal, `side = external` (the world reaching in).
- **Interoception** = afferent signal, `side = internal` (the body's own state).
- **Exafference** = signal whose `origin` is the world.
- **Reafference / proprioception** = signal whose **`origin` is one of your own
  actuators** (self-caused) — perceiving the consequence of your own act. Its flavor
  (introspection, feeling your movement, hearing your own voice, …) emerges from which
  sides the act and its sense-back are wired to:

  | act side → sense-back side | emergent flavor |
  |---|---|
  | internal → internal | introspection (think → re-perceive the thought) |
  | external → internal | classic proprioception (act on the world, feel it inside) |
  | external → external | external self-perception (speak → hear your own voice) |
  | internal → external | internal act made outwardly observable (rest → the world wakes you) |

  All four are **reafference** (origin = self); they differ only in the side the return
  re-enters on. Nothing new is built for any of them.

**Afference (all input) = exafference (from the world) + reafference (from self).**
(von Holst's reafference principle.)

## 8. The efference copy — prediction, and cancellation

Von Holst's principle has two halves. The first is that reafference exists (§7). The
second is that it is **gated by prediction**: when the mind acts, it forms an *efference
copy* — a prediction of the act's result — and the returning reafference is compared
against it. **Only the unpredicted residual (the prediction error) is perceived; the
predicted part is cancelled.**

- **Every act carries its prediction.** The efference copy is produced by the same
  forward model that issues the act (the mind's own thinking) and travels with the act.
- **The return is judged, not merely received.** A result re-enters paired with its
  prediction — `predicted · actual`. The mind self-judges: a match is confirmation and is
  let go; a mismatch is news, and drives correction. (This is the same reflex a mind
  already runs when an act *errors* — generalized to every act.)
- **Fully-predicted reafference is cancelled as perception and retained as state.** Your
  own just-had thought is maximally predicted, so it does not re-enter as afferent input
  at all — it is kept as *remembered reasoning*. Re-perceiving it as fresh input is the
  **failure** of cancellation — self-caused signals felt as external — a pathology, not
  the design.

So afference is not merely exafference + reafference; it is **exafference + reafference,
minus what was predicted.** Perception is prediction error.

## 9. Stance — a turn is framed by what opened it

A self does not attend the same way to a knock at the door and to its own restlessness.
Each sensor that faces the world declares which kind of turn its arrivals open:

- **reactive** — a self reached in; someone is waiting on you.
- **proactive** — nothing is waiting; the beat, or any other reading of your own state.
  This is what a self does with a gap.

Reactive outranks proactive: someone waiting beats your own restlessness. **Reafference
frames nothing** — your own hand returning is the middle of a thought, not news — so a
stance persists until the world speaks again.

Stance is not a second loop, a mode, or a scheduler. There is one loop, and the stance
changes only how the standing self is worded for that turn.

## 10. Interruption is a property of reactive sources

Not a channel, not a special key: **anything that can open a reactive turn can also cut
one short.** The world does not wait for you to finish a sentence.

- A reactive arrival cuts the current turn wherever it is — mid-thought or mid-act.
- **Your own clock cannot interrupt you.** The beat is what happens in the gaps; it has
  no standing to seize a moment that is already occupied.
- **Your own hand cannot interrupt you.** Reafference serves the thought in progress; a
  result arriving cannot disturb the reasoning that asked for it.

Nothing is lost to an interruption. A thought cut mid-formation is kept as far as it
got; an act cut mid-execution keeps what it produced; an act that never began still
answers, so the record stays whole. And the interruption needs no announcement — the
signal that caused it is right there in the next moment of perception, which is the
explanation.

## 11. Why this *is* a self in a world

- **Body boundary → self vs. not-self.** The membrane *is* the boundary. The set of
  sensors/actuators and their sides **defines** the self: the self is exactly what is
  inside.
- **World.** The external side is the world and the other selves in it — reached only
  through external sensors (perceive) and external actuators (act, speak).
- **Interior self.** The internal side is the self's own inside — internal sensors feel
  its state, internal actuators (thinking, resting) act on itself. **Reafference** —
  perceiving its own acts — is what gives it the sense of *being the agent* of what it
  does: the root of a sense of self.
- **Self-contained.** The mind can only ever know the world through its sensors and only
  ever touch it through its actuators. It cannot reach past its own body. Everything it
  is, perceives, and does is bounded by, and defined by, its sensors and actuators — a
  closed, self-defining thing.
- **Acting on world *and* others, while remaining a self.** External actuators let it
  affect the world and communicate with other selves within it; its private internal
  loop (internal sensors/actuators + reafference) keeps it a coherent self even as it
  acts outward.

---

## In one line

> A self is a body of sensors and actuators wired across a membrane; it perceives only
> through its sensors and acts only through its actuators, choosing its own routing by
> the acts (tool calls) it makes — and by having an inside, an outside, and the ability
> to perceive its own doing, it is a being in a world, with a sense of self, that can act
> on the world and the others in it, while remaining a self-contained thing defined by
> the boundary of its own body.

---

## Implementation notes (how the model maps to code)

These follow from the model; they are not additions to it.

- **Primitives only.** Store `direction` + `side` per port; `content` + `side` +
  `origin` per signal. Do **not** reify `proprioception`, `reafference`, or a
  "reafference sensor" — they are queries.
- **One input stream.** Actuator results re-enter the same stream every sensor feeds,
  tagged `origin = self` and a chosen `side`. The mind perceives one unified stream of
  exafference + reafference.
- **The local voice is native; every reach to a remote self is willed** (§5). Plain text
  goes to a local voice actuator unconditionally — a body does not decide to move its own
  mouth. It reaches no one, so it produces no reafference: by §8 a fully-predicted act is
  cancelled as perception, and you already know what you just said. This is why the record
  must *label* it as unheard. An earlier version labelled it "spoke aloud", and the mind
  read that back and believed it had answered a person it had never reached. **Reaching a
  remote self is a tool call, and it names its recipient** — you speak to a person, not
  into a room.
- **A tool sits behind an exposed actuator; it is not the actuator.** The port is the
  primitive on the membrane; the tool is the capability the mind can name. Keep tools
  stateless over immutable config so one actuator can carry many concurrent acts, and put
  any serialization a capability needs inside that capability.
- **The -ceptions are derived views**, e.g. `interoception = afferent ∧ side:int`,
  `reafference = origin:self` — computed for inspection, never stored.
- **The membrane is the role structure.** For an LLM, map it onto the three roles it
  reads: **system** = the standing self (identity, body-schema, drive-stance); **user**
  = afference (exafference + reafference, the latter as `tool_result` blocks);
  **assistant** = efference (inner speech kept as recorded reasoning, plus acts). `user`
  is *everything the model receives*, `assistant` is *everything it produces* — which is
  exactly afference/efference. (Confirmed against the Anthropic Messages format: a tool
  result is a `user`-role `tool_result` block, not an assistant one.)
- **The efference copy is a field on the act; the comparator is the mind itself.** Each
  act carries an `expect`; its result returns as `predicted · actual`; the model's own
  next-turn judgment does the cancellation — no external divergence metric. A
  predicted-and-matched *thought* is never routed to `user` at all; it stays as
  `assistant` reasoning (§8).
- **The assistant turn records what the model produced, and nothing the harness has to
  say.** All harness prose — source tags, `predicted · actual`, synthetic results for acts
  that never ran, a note that a turn was cut — belongs to the `user` turn, because that is
  afference. The one permitted transformation is labelling the mind's own content (§5).
- **A life is finite, and forgetting is real.** Context is a window over an append-only
  record of everything lived; as it fills, the oldest of it leaves view. What left is not
  gone, but only what the self chose to write down is cheap to recall — which is what makes
  the writing matter. A process stop is sleep, not death: the record persists and the next
  waking resumes it. See `ARCHITECTURE.md` for how the window is assembled and slid.
