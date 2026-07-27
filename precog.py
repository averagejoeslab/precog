#!/usr/bin/env python3
"""precog — a self, per spec.md: a body of paired sensors and actuators around one mind.

THE MODEL
  Signals are the only currency, and they circulate:
      sensors ─▶ ONE queue ─▶ the mind (one LLM call) ─▶ actuators ─▶ paired sensors ─▶ the queue ─▶ …
  Every actuator is PAIRED with a sensor, which is what makes the flows physical rather than notional:
      exafference   world → an In sensor                (a person over TelegramIn)
      efference     mind  → an Out actuator             (voice · telegram · bash)
      reafference   an Out's result → its paired In     (BashOut→BashIn is internal: proprioception;
                                                         TelegramOut→TelegramIn is external: hearing
                                                         your own words land)
      afference     exafference + reafference — one stream, no privileged channel

  STANCE. Every sensor that faces the world declares a drive: REACTIVE (a person — someone is waiting)
  or PROACTIVE (TimeSensor — nothing is waiting, act if you wish). A world arrival reframes the turn;
  reafference never does, because your own hand returning is mid-thought, not news. Reactive wins ties.
  The stance is a band of the prompt — nothing else. There is one loop.

  INTERRUPTION is not a channel; it is a property of reactive sources. Any pending reactive signal cuts
  the current turn wherever it is — mid-stream or mid-act — and nothing is lost: the partial thought is
  snapshotted, a killed act keeps its partial output, acts that never ran get synthetic results so every
  tool_use stays answered. The interrupting message needs no marker: it IS the explanation.

  MEMORY is two layers, both read by the agent's own hands, only one written by them:
      trace.jsonl   every message of one life, append-only, written by the harness
      memory.md     what the agent chose to distil, written by the agent via bash
  The mind's context is a sliding view over the trace, assembled from UNITS. A unit is the run of
  messages between consecutive tool_result-free user turns — provably the smallest slice the Messages
  contract permits with no rewriting (cutting anywhere else either opens the array on an assistant turn
  or orphans a tool_result). We send everything we hold and drop the oldest unit per "prompt is too
  long" until the provider accepts, so every call carries the maximum context that fits. Rejections are
  free; successes are billed — which is why the search is linear and never binary.

RUN
  python precog.py                  (DEEPSEEK_API_KEY required; TELEGRAM_* to reach a person;
                                     a telegram 'quit' stops the loop)
"""
import os, sys, re, json, time, datetime, threading, queue, subprocess, urllib.request, shutil, select
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from anthropic import Anthropic


# ══════════════════════════════════════════════════════════════════════════════
#  §0 · CONFIG — the only place the environment is read
# ══════════════════════════════════════════════════════════════════════════════

def load_env(path=".env"):
    p = Path(path)
    if not p.exists(): return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1); v = v.strip()
            if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'": v = v[1:-1]   # allow KEY='{"…"}'
            os.environ.setdefault(k.strip(), v)

load_env()

EXTERNAL, INTERNAL  = "external", "internal"     # the membrane: world | self
REACTIVE, PROACTIVE = "reactive", "proactive"    # what kind of turn a source opens

MODEL       = "deepseek-v4-flash"
STATE_DIR   = "~/.precognitive"                  # the self IS this directory — it outlives every process
MEMORY_PATH = STATE_DIR + "/memory/memory.md"    # the agent writes this, with its own hands
TRACE_PATH  = STATE_DIR + "/trace.jsonl"         # the harness writes this: one life, append-only
BUFFER      = 150                                # units held in RAM (must exceed any window, so the API decides)
FIT_MARGIN  = 2                                  # units loaded beyond the remembered fit
TICK_MIN    = 5.0                                # the beat, and how far it slows as quiet holds
TICK_MAX    = 1800.0
WATCHDOG    = 3600.0                             # backstop: never block forever if every sensor dies
OUT_CAP     = 8000                               # cap on an act's result, so one turn can never blow the window
SHOW        = True

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

def people(spec):
    """id → name, authored as a JSON dict in the environment:  {"123456": "Chase", "789012": "Alice"}
    The keys ARE the allowlist, and ONE dict serves both directions — the name it hears in
    `[Chase · 15:04]` is the name it types in TelegramOut's `to`, so the round trip cannot miss."""
    spec = (spec or "").strip()
    if not spec: return {}
    try:
        return {int(k): str(v) for k, v in json.loads(spec).items()}
    except Exception:
        if spec.startswith("{"): sys.stderr.write(f"[TELEGRAM_PEOPLE is not valid JSON: {spec[:60]}]\n")
        return {int(x): f"person{i+1}" for i, x in enumerate(re.findall(r"-?\d+", spec))}   # bare ids

TG_PEOPLE = people(os.environ.get("TELEGRAM_PEOPLE", "")) \
         or people(os.environ.get("TELEGRAM_ALLOWED_IDS", ""))   # older ids-only form still works


def show(glyph, sig):
    if not SHOW: return
    flat = lambda x: " ⏎ ".join(p.strip() for p in str(x).strip().splitlines() if p.strip())
    tag  = f"{sig.target or sig.source or '·'}[{sig.side[:3]}]"
    c    = sig.content
    if isinstance(c, dict):
        if   "message" in c: s = f"→ {c.get('to') or ''} " + flat(c["message"])
        elif "command" in c: s = "$ " + flat(c["command"])
        else:                s = flat(c)
    elif sig.predicted is not None:
        s = f"predicted: {flat(sig.predicted)[:30]} · actual: {flat(c)[:48]}"
    else:
        s = flat(c)
    print(f"  {glyph} {tag:<15} {s[:96]}")


# NOTE — the harness deliberately does not show the agent its own source. Self-knowledge comes from the
# body-schema, generated from the live organs and verifiable by acting. Source code is the wrong kind: it
# names machinery the hands cannot inspect, and unverifiable claims become confident false beliefs.
# (Observed: reading TELEGRAM_ALLOWED_IDS in its own config, not finding it in the one shell it can reach,
# and concluding it could message no one — which was false.) The loop is described in prose instead.


# ══════════════════════════════════════════════════════════════════════════════
#  §1 · SIGNAL — the one currency, flowing in both directions
# ══════════════════════════════════════════════════════════════════════════════

class Signal:
    def __init__(self, content, side, *, origin="world", source=None, target=None,
                 drive=None, ref=None, predicted=None, took=None, at=None):
        self.content, self.side, self.origin = content, side, origin   # origin: world | self
        self.source, self.target = source, target      # producing <Src>In | destination <Src>Out
        self.drive = drive                             # only meaningful when origin == "world"
        self.ref = ref                                 # tool_use id — binds a result to its act
        self.predicted, self.took = predicted, took    # the efference copy · how long the act took
        self.at = at or now()
    @classmethod
    def act(cls, target, inp, *, ref=None, predicted=None, side=EXTERNAL):
        return cls(inp, side, origin="self", target=target, ref=ref, predicted=predicted)


def opens(sigs):       return [s for s in sigs if s.origin == "world"]   # can reframe the turn
def reafference(sigs): return [s for s in sigs if s.origin == "self"]    # mid-thought; reframes nothing


def opens_unit(turn):
    """A slice boundary. The remainder of the trace from here is valid with NO rewriting: it starts on a
    user turn, and no tool_result is orphaned (there are none). Cutting anywhere else would either open
    the array on an assistant turn or strand a tool_result — the two things the API rejects."""
    return turn["role"] == "user" and not any(b.get("type") == "tool_result" for b in turn["content"])


# ══════════════════════════════════════════════════════════════════════════════
#  §2 · AFFERENCE — the one input stream, and the only thing that knows
#       what is waiting that could interrupt
# ══════════════════════════════════════════════════════════════════════════════

class Afference:
    def __init__(self):
        self._q, self._lk, self._pending = queue.Queue(), threading.Lock(), 0
    def put(self, sig):
        if sig.origin == "world" and sig.drive == REACTIVE:
            with self._lk: self._pending += 1          # ← the entire interrupt mechanism
        self._q.put(sig)
    def get(self, timeout=None):
        try: return self._q.get(timeout=timeout)
        except queue.Empty: return None
    def drain(self, first=None):
        out = [] if first is None else [first]
        while True:
            try: out.append(self._q.get_nowait())
            except queue.Empty: break
        n = sum(1 for s in out if s.origin == "world" and s.drive == REACTIVE)
        if n:
            with self._lk: self._pending = max(0, self._pending - n)
        return self._coalesce(out)
    def interrupting(self): return self._pending > 0
    @staticmethod
    def _coalesce(sigs):
        """Interoception is level-triggered: you perceive how long it has been, once — not a log of
        every moment that passed while you worked."""
        beat = lambda s: s.origin == "world" and s.drive == PROACTIVE
        keep = {s.source: s for s in sigs if beat(s)}
        return [s for s in sigs if not beat(s) or keep[s.source] is s]


# ══════════════════════════════════════════════════════════════════════════════
#  §3 · PORTS — Sensor and Actuator, in <Src>In/<Src>Out pairs
# ══════════════════════════════════════════════════════════════════════════════

class Sensor:
    """An afferent port. A sensor may face the world (then it declares a drive and pushes), or be purely
    the return path for an actuator (then drive stays None and it only ever stamps results), or both."""
    drive = None
    def __init__(self, name, side, about=""):
        self.name, self.side, self.about = name, side, about
    def status(self): return ""                        # live state → generated into the body-schema
    def start(self, stream): pass                      # world-facing sensors override
    def perceived(self, scene): pass                   # hook: a sensor may modulate on what arrived
    def resume(self, at): pass                         # hook: wake tells organs when the life was last
                                                       # active (None if newborn), so none of them lies
    def signal(self, content, source=None):
        assert self.drive is not None, f"{self.name} has no afferent role"
        return Signal(content, self.side, origin="world", source=source or self.name, drive=self.drive)
    def reafferent(self, result, *, ref, predicted=None, took=None):
        return Signal(result, self.side, origin="self", source=self.name,
                      ref=ref, predicted=predicted, took=took)


class Tool(ABC):
    """A stateless capability over immutable config. Everything per-call lives in `inp` and locals — the
    executor may invoke the same tool any number of times concurrently and will never serialize you. If
    you need serialization, hold your own lock (see BashTool)."""
    description = ""
    schema = {"type": "object", "properties": {}}
    @abstractmethod
    def run(self, inp, should_stop=None): ...
    def status(self): return ""
    def describe(self): return {"description": self.description, "schema": self.schema}


class Actuator:
    def __init__(self, name, side, pair, tool=None, about=""):
        self.name, self.side, self.pair, self.tool, self.about = name, side, pair, tool, about
    @property
    def exposed(self): return self.tool is not None    # the mind can name it iff a Tool sits behind it
    @property
    def blurb(self): return self.tool.description if self.tool else self.about
    def status(self): return self.tool.status() if self.tool else ""
    def act(self, inp, should_stop=None):
        return self.tool.run(inp, should_stop) if self.tool else self.native(inp)
    def native(self, inp): return "(no-op)"
    def describe(self):
        return {"name": self.name, **self.tool.describe()} if self.tool else None


class ToolRegistry:
    def __init__(self, actuators=()): self._by = {a.name: a for a in actuators}
    def register(self, a): self._by[a.name] = a
    def get(self, name): return self._by.get(name)
    def all(self): return list(self._by.values())
    def specs(self): return [a.describe() for a in self._by.values() if a.exposed]


# ══════════════════════════════════════════════════════════════════════════════
#  §4 · DRIVE — the stance: when it fires, and how it frames the turn
# ══════════════════════════════════════════════════════════════════════════════

class Drive:
    def __init__(self, name, fires, text): self.name, self._f, self.text = name, fires, text
    def active(self, scene): return self._f(scene)


# ══════════════════════════════════════════════════════════════════════════════
#  §5 · PROVIDER — the reasoning engine, the only thing that speaks a wire
#       format, and the owner of the sliding view over the trace
# ══════════════════════════════════════════════════════════════════════════════

class Provider(ABC):
    @abstractmethod
    def respond(self, system, units, win, scene, specs, should_stop, notes=()):
        """Append the scene (plus any harness `notes`) to `units` as ONE user turn — extending the
        newest unit, or opening a new one — call the model on flatten(units[win:]), dropping the oldest
        unit per overflow until it fits, append the assistant record IF the model produced anything, and
        return (acts, cut, win, fit). Turns are provider-shaped and opaque to everyone else."""


class AnthropicProvider(Provider):
    # our own labels, stripped if the model echoes them back so they cannot compound. The cut note is
    # NOT here: it lives in the user turn now, and nothing the harness says belongs in an assistant turn.
    _MARKERS  = ("(reasoning)", "(thought — no one heard this)")
    _TOO_LONG = ("too long", "context length", "context_length", "maximum context",
                 "too many tokens", "prompt is too long")

    def __init__(self, client, model, think_budget=1024, max_tokens=2048, voice="DefaultOut"):
        self.client, self.model, self.tb, self.mt, self.voice = client, model, think_budget, max_tokens, voice
    @classmethod
    def deepseek(cls, model=MODEL, base_url="https://api.deepseek.com/anthropic", **kw):
        return cls(Anthropic(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=base_url), model, **kw)

    # ── the contract ──
    def respond(self, system, units, win, scene, specs, should_stop, notes=()):
        turn = {"role": "user", "content": self._render(scene, notes)}
        if not units or opens_unit(turn): units.append([turn])       # a new slice unit begins
        else:                             units[-1].append(turn)     # mid-chain: same unit
        tools = [{"name": t["name"], "description": t["description"], "input_schema": t["schema"]}
                 for t in specs]
        while True:                                                  # send everything we hold…
            try:
                resp, cut = self._call(system, flatten(units, win), tools, should_stop); break
            except Exception as e:
                if not any(k in str(e).lower() for k in self._TOO_LONG): raise
                win += 1                                             # …drop the OLDEST unit, retry
                if win >= len(units):
                    raise RuntimeError("the current unit alone will not fit the context window")
        thinking, text, calls = self._parse(resp)
        record = self._record(thinking, text, calls)
        if record is not None: units[-1].append(record)              # nothing produced ⇒ nothing recorded
        acts = []
        if text.strip():
            acts.append(Signal.act(self.voice, self._clean(text), side=EXTERNAL))   # native, no ref
        for b in calls:
            acts.append(Signal.act(b.name, b.input or {}, ref=b.id,
                                   predicted=(b.input or {}).get("expect")))
        return acts, cut, win, len(units) - win

    # ── the wire ──
    def _render(self, scene, notes=()):
        """The user turn is where ALL harness prose lives — the [source · time] tags, the
        predicted/actual framing, the synthetic tool_results, and any note the harness owes the agent
        about the last turn. Ordering matches quark's: results first, then the note."""
        t0, out = now(), []
        for s in scene:                                     # reafference first — pairs with prior acts
            if s.ref is not None:
                head = f"[{s.at:%H:%M:%S}" + (f" · took {s.took:.1f}s" if s.took is not None else "") + "]"
                body = f"predicted: {s.predicted}\nactual: {s.content}" if s.predicted else str(s.content)
                out.append({"type": "tool_result", "tool_use_id": s.ref, "content": f"{head} {body}"})
        for s in scene:                                     # then the world, and the beat
            if s.ref is None:
                w = (t0 - s.at).total_seconds()
                tag = (f"[{s.source or 'world'} · {s.at:%H:%M:%S}"
                       + (f" · waited {int(w)}s" if w > 2 else "") + "]")
                out.append({"type": "text", "text": f"{tag} {s.content}"})
        for n in notes: out.append({"type": "text", "text": n})
        return out

    def _call(self, system, messages, tools, should_stop):
        with self.client.messages.stream(model=self.model, max_tokens=self.mt, system=system,
                messages=messages, tools=tools,
                thinking={"type": "enabled", "budget_tokens": self.tb}) as st:
            flowing = False
            for ev in st:
                if should_stop and should_stop(): break              # a reactive arrival cuts the turn
                if (getattr(ev, "type", None) == "content_block_delta"
                        and getattr(ev.delta, "type", None) == "thinking_delta"):
                    if SHOW:
                        if not flowing: print("  〜 ", end="", flush=True); flowing = True
                        print(ev.delta.thinking, end="", flush=True)
                elif getattr(ev, "type", None) == "content_block_stop" and flowing:
                    print(flush=True); flowing = False
            if flowing: print(flush=True)
            if should_stop and should_stop():
                return st.current_message_snapshot, True             # the PARTIAL — nothing is lost
            return st.get_final_message(), False

    @staticmethod
    def _parse(r):
        t = "".join(getattr(b, "thinking", "") for b in r.content if getattr(b, "type", None) == "thinking")
        x = "".join(getattr(b, "text", "")     for b in r.content if getattr(b, "type", None) == "text")
        # a cut mid-block can leave a tool_use with no id: it would be recorded but never answered
        # (Signal.act would carry ref=None, so _run treats it as the voice and returns no reafference).
        # Dropping it here keeps the record and the acts counting the same blocks.
        c = [b for b in r.content
             if getattr(b, "type", None) == "tool_use" and getattr(b, "id", None)]
        return t, x, c

    def _record(self, thinking, text, calls):
        """The assistant turn records what the MODEL produced — nothing the harness has to say.

        The only transformation is labelling: the thinking block is flattened to text, because this
        provider ACCEPTS thinking blocks passed back but does not feed them to the model (probed:
        a token present only in a returned thinking block is unrecallable, while the same token in a
        `(reasoning)` text block is recalled). So the flattening is what carries the train of thought.

        tool_use is emitted LAST, unconditionally. Anything after a tool_use makes the API treat it as
        unanswered even when its tool_result is right there in the next message (probed: [text,tool_use]
        → 200, [text,tool_use,text] → 400 "ids found without tool_result blocks immediately after").
        Emitting it last by construction is what makes that class of bug unreachable.

        Returns None when the model produced nothing — a cut before the first block. The harness has
        no utterance to attribute, so it appends no turn; consecutive user turns are combined by the API.
        """
        content, r, v = [], self._clean(thinking), self._clean(text)
        if r: content.append({"type": "text", "text": f"(reasoning) {r}"})
        # the label is the correction, at the point of use: "(spoke aloud)" once made it believe it had
        # answered a person it had never reached.
        if v: content.append({"type": "text", "text": f"(thought — no one heard this) {v}"})
        for b in calls:                                              # ← always last, nothing follows
            content.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input or {}})
        return {"role": "assistant", "content": content} if content else None

    def _clean(self, s):
        s = s or ""
        for m in self._MARKERS: s = s.replace(m, "")
        return s.strip()


def flatten(units, win):
    """The view: a VERBATIM suffix of the life. No stubs, no re-typed blocks, nothing invented — which
    is the whole reason the slice unit is what it is."""
    return [m for u in units[win:] for m in u]


# ══════════════════════════════════════════════════════════════════════════════
#  §6 · IDENTITY — prose states the model; anything naming a live part is
#       GENERATED, so the prompt can never drift from the anatomy
# ══════════════════════════════════════════════════════════════════════════════

class Identity:
    def __init__(self, template, memory=MEMORY_PATH, trace=TRACE_PATH, where="your body's machine"):
        self.template, self.memory, self.trace, self.where = template, memory, trace, where
    def render(self, schema, now):
        fills = {
            "%%SENSORS%%":   "\n".join(schema["sensors"]),
            "%%ACTUATORS%%": "\n".join(schema["actuators"]),
            "%%PAIRINGS%%":  "\n".join(schema["pairs"]),
            "%%REACH%%":     schema.get("reach") or "an actuator that reaches them",
            "%%MEMORY%%":    self.memory,
            "%%TRACE%%":     self.trace,
            "%%WHERE%%":     self.where,
            "%%WHEN%%":      str(now.get("when", "")),
            "%%WINDOW%%":    str(now.get("window", "")),
        }
        s = self.template
        for k, v in fills.items(): s = s.replace(k, v)
        return s


# ══════════════════════════════════════════════════════════════════════════════
#  §7 · BODY — the paired organs on one stream. Perceives afference in,
#       enacts efference out (in parallel), routes every result to its pair
# ══════════════════════════════════════════════════════════════════════════════

class Body:
    def __init__(self, sensors, tools: ToolRegistry):
        self.sensors, self.tools = list(sensors), tools
        self.stream = Afference()
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="act")
    def start(self):
        for s in self.sensors: s.start(self.stream)
    def specs(self): return self.tools.specs()
    def describe(self):
        st = lambda o: f" · {o.status()}" if o.status() else ""
        return {
            "sensors":   [f"- {s.name} — {s.about}{st(s)} ({s.side})" for s in self.sensors],
            "actuators": [f"- {a.name} — {a.blurb}{st(a)} "
                          f"({'willed' if a.exposed else 'native'})" for a in self.tools.all()],
            "pairs":     [f"- {a.name} → returns through {a.pair.name}"
                          for a in self.tools.all() if a.pair and a.exposed],
            # the organ that crosses to another self: exposed, and its result returns EXTERNALLY (you
            # hear your own words land out there) — unlike hands, whose results return inside you.
            "reach":     ", ".join(a.name for a in self.tools.all()
                                   if a.exposed and a.pair is not None and a.pair.side == EXTERNAL),
        }

    # ── afference: drain, or block until something arrives ──
    def perceive(self):
        scene = self.stream.drain()
        if not scene:
            scene = self.stream.drain(first=self.stream.get(timeout=WATCHDOG))
        for s in self.sensors: s.perceived(scene)
        for s in scene: show("‹", s)
        return scene

    # ── efference: run every willed act, concurrently; each result home through its pair ──
    def enact(self, acts, should_stop=None):
        for a in acts: show("›", a)
        for sig in self._pool.map(lambda a: self._run(a, should_stop), acts):
            if sig is not None: self.stream.put(sig)
    def _run(self, a, should_stop):
        actuator, t0 = self.tools.get(a.target), time.time()
        if should_stop and should_stop() and a.ref is not None:
            return self._synthetic(actuator, a, "[interrupted — this act never ran]")
        try:
            result = actuator.act(a.content, should_stop) if actuator else f"(unknown actuator {a.target})"
        except Exception as e:
            result = f"(actuator {a.target} errored: {e})"
        if a.ref is None: return None                  # the voice: perfectly predicted, nothing returns
        return self._reaff(actuator, a, result, time.time() - t0)

    # ── the interrupt's mercy: acts that never ran still answer, so every tool_use stays paired ──
    def abort(self, acts):
        for a in acts:
            note = ("[interrupted — this act was cut off before it was fully formed]"
                    if not a.content else "[interrupted — this act never ran]")
            sig = self._synthetic(self.tools.get(a.target), a, note)
            show("‹", sig); self.stream.put(sig)
    def _synthetic(self, actuator, a, note): return self._reaff(actuator, a, note, 0.0)
    def _reaff(self, actuator, a, result, took):
        pair = actuator.pair if actuator else None
        if pair is not None:
            return pair.reafferent(result, ref=a.ref, predicted=a.predicted, took=took)
        return Signal(result, INTERNAL, origin="self", ref=a.ref, predicted=a.predicted, took=took)


# ══════════════════════════════════════════════════════════════════════════════
#  §8 · AGENT — the mind: provider · identity · drives · the unit buffer ·
#       the life-file, coupled to a body by one loop
# ══════════════════════════════════════════════════════════════════════════════

CUT_NOTE = "[your last turn was cut short — someone reached you before you finished it]"

class Agent:
    def __init__(self, body, provider, identity, drives, trace_path=TRACE_PATH):
        self.body, self.provider, self.identity, self.drives = body, provider, identity, list(drives)
        self.trace_path = trace_path                   # None = ephemeral (tests)
        self._fh, self.slides, self.notes = None, 0, []
        self.units, self.fit, self.unit_no, self.born, last_at = self._wake()
        for s in self.body.sensors: s.resume(last_at)   # tell the organs when this life was last active
        self.win = max(0, len(self.units) - (self.fit + FIT_MARGIN))
        self.framing = self.drives[-1]                 # born unbidden: proactive until the world speaks

    # ── wake: the same one life, resumed. O(tail), never O(life). ──
    def _wake(self):
        if self.trace_path is None: return [], BUFFER, 0, None, None
        p = Path(self.trace_path).expanduser()
        if not p.exists(): return [], BUFFER, 0, None, None
        rows, fit, born = tail_rows(p, BUFFER * 12), BUFFER, first_at(p)
        for r in rows:
            if r.get("event") == "wake" and isinstance(r.get("fit"), int): fit = r["fit"]
        msgs = [r for r in rows if "role" in r and "content" in r]
        units, last = [], object()
        for m in msgs:                                  # regroup by the recorded unit id, or DERIVE it:
            t = {"role": m["role"], "content": m["content"]}    # a trace written before unit ids existed
            u = m.get("unit")                                   # still slices correctly on opens_unit
            if (opens_unit(t) if u is None else u != last) or not units:
                units.append([]); last = u
            units[-1].append(t)
        while units and not opens_unit(units[0][0]): units.pop(0)   # discard a leading partial unit
        heal(units)
        n = max((r.get("unit", 0) for r in msgs), default=0)
        last_at = next((parse_at(r["at"]) for r in reversed(rows) if r.get("at")), None)
        return units[-BUFFER:], fit, n, born, last_at

    # ── the life-file: append-only, flushed per turn, so a crash loses nothing already lived ──
    def _open(self):
        if self._fh is None and self.trace_path is not None:
            p = Path(self.trace_path).expanduser(); p.parent.mkdir(parents=True, exist_ok=True)
            self._fh = p.open("a", encoding="utf-8")
            self._write({"event": "wake", "at": stamp(), "model": MODEL, "fit": self.fit})
        return self._fh
    def _write(self, row):
        fh = self._fh
        if fh: fh.write(json.dumps(row, default=str) + "\n"); fh.flush()
    def _journal(self, unit_no, turns):
        if self.trace_path is None: return
        self._open()
        for t in turns: self._write({"unit": unit_no, "at": stamp(), **t})
    def _log_slide(self, n):
        self.slides += n
        self._open(); self._write({"event": "slide", "at": stamp(), "units": n, "fit": self.fit})

    # ── the stance: a drive fires only on a world arrival; otherwise you are mid-thought ──
    def stance(self, scene):
        for d in self.drives:
            if d.active(scene): self.framing = d; break
        return self.framing.text

    def window(self):
        seen = len(self.units) - self.win
        born = f"alive since {self.born[:10]} · " if self.born else ""
        return f"{born}{seen} units in view · window slid {self.slides}× this session"

    def step(self):
        scene = self.body.perceive()
        if any(s.origin == "world" and str(s.content).strip().lower() in ("quit", "exit") for s in scene):
            return "quit"

        system = (self.identity.render(self.body.describe(),
                                       {"when": now().date(), "window": self.window()})
                  + "\n\n" + self.stance(scene))                      # the volatile band goes last

        n_before, win_before = len(self.units), self.win
        msgs_before = sum(len(u) for u in self.units)
        notes, self.notes = self.notes, []          # anything the harness owed the agent, delivered
                                                    # in THIS user turn — never in an assistant turn
        acts, cut, self.win, self.fit = self.provider.respond(
            system, self.units, self.win, scene, self.body.specs(),
            self.body.stream.interrupting, notes)
        if self.win > win_before: self._log_slide(self.win - win_before)

        added  = sum(len(u) for u in self.units) - msgs_before        # 2 normally; 1 if the model
        opened = len(self.units) > n_before                           # produced nothing to record
        beat   = not reafference(scene) and all(s.drive == PROACTIVE for s in opens(scene))
        if not acts and beat and opened and added == len(self.units[-1]):
            self.units.pop()                       # a beat that produced nothing is not an episode
        else:
            if opened: self.unit_no += 1
            self._journal(self.unit_no, self.units[-1][-added:])      # NEVER drop a scene that
                                                                      # perceived the world
        if cut:
            self.body.enact([a for a in acts if a.ref is None])        # what formed, was voiced
            self.body.abort([a for a in acts if a.ref is not None])    # what never ran still answers
            self.notes.append(CUT_NOTE)                                # told in the NEXT user turn
        else:
            self.body.enact(acts, self.body.stream.interrupting)
            if self.body.stream.interrupting(): self.notes.append(CUT_NOTE)   # cut mid-act
        self._trim()

    def _trim(self):
        if len(self.units) > BUFFER:
            drop = min(len(self.units) - BUFFER, self.win)             # never trim into the live view
            if drop: del self.units[:drop]; self.win -= drop

    def run(self):
        self.body.start()
        print("— precog online — message your bot · a person can interrupt you · 'quit' stops —\n")
        while True:
            if self.step() == "quit": print("— stopped —"); break


# ── helpers: the tail read, the heal, the clock ──

# ONE CLOCK — UTC, everywhere. The agent's hands read `date` inside a UTC container, so its memory
# timestamps are UTC; if the harness journalled local time the cross-layer join would silently fail
# (a memory stamped 00:47 would never be found by grep '"at": "…T19:47'). Observed and fixed.
def now():   return datetime.datetime.now(datetime.timezone.utc)
def stamp(): return now().isoformat()

def parse_at(s):
    try:
        d = datetime.datetime.fromisoformat(str(s))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception: return None

def human(td):
    s = int(td.total_seconds())
    if s < 90:    return f"{s}s"
    if s < 5400:  return f"{s // 60}m"
    h, m = divmod(s // 60, 60)
    return f"{h}h" + (f" {m}m" if m else "")

def first_at(path):
    with path.open("r", encoding="utf-8") as f:
        try: return json.loads(f.readline()).get("at")
        except Exception: return None

def tail_rows(path, want):
    """Read the last `want` json lines by seeking backwards — so wake costs O(tail), not O(life)."""
    size, buf, block = path.stat().st_size, b"", 1 << 16
    with path.open("rb") as f:
        while size > 0 and buf.count(b"\n") <= want:
            step = min(block, size); size -= step
            f.seek(size); buf = f.read(step) + buf
    rows = []
    for line in buf.split(b"\n")[-(want + 1):]:
        try: rows.append(json.loads(line))
        except Exception: continue
    return rows

def heal(units):
    """A stop mid-turn leaves a tool_use nobody answered. Synthesize the results so every tool_use
    stays paired — and nothing else: a dangling USER turn needs no repair, because consecutive user
    turns are combined by the API, and inventing an assistant turn to 'balance' it would be the
    harness putting words in the model's mouth."""
    if not units: return
    last = units[-1]
    if last[-1]["role"] != "assistant": return
    uses = [b for b in last[-1]["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
    if uses:
        last.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": b["id"],
                     "content": "[asleep before the result returned]"} for b in uses]})


# ══════════════════════════════════════════════════════════════════════════════
#  THIS AGENT — precog's organs, self-model, and wiring
# ══════════════════════════════════════════════════════════════════════════════

# ── the beat: the one sensor with no actuator pair. You perceive time; you cannot act on it. ──
class TimeSensor(Sensor):
    drive = PROACTIVE
    def __init__(self, lo=TICK_MIN, hi=TICK_MAX):
        super().__init__("TimeSensor", INTERNAL,
                         "your own sense of time — beats when nothing else arrives; the only sensor "
                         "with no actuator pair (you cannot act on time)")
        self.lo, self.hi, self.beats, self.last = lo, hi, 0, None
        self._stir = threading.Event()
    def interval(self): return min(self.lo * 2 ** min(self.beats, 9), self.hi)   # 5s → 30min
    def arouse(self):
        self.beats, self.last = 0, now(); self._stir.set()
    def resume(self, at):
        self.last = at                       # so a beat after sleep reports the real gap, not "first
                                             # moment" — an organ must never assert what is false
    def perceived(self, scene):
        if any(s.drive == REACTIVE for s in opens(scene)): self.arouse()
    def start(self, stream):
        threading.Thread(target=self._beat, args=(stream,), daemon=True).start()
    def _beat(self, stream):
        while True:
            if self._stir.wait(self.interval()):       # roused by the world — restart the interval
                self._stir.clear(); continue
            self.beats += 1
            t = now()
            since = f"quiet for {human(t - self.last)}" if self.last else "your first moment"
            stream.put(self.signal(f"(a quiet moment · {t:%a %H:%M:%S} UTC · {since})"))


# ── the Default pair: local input (dormant) ↔ the native voice ──
class DefaultIn(Sensor):
    drive = REACTIVE                                   # when wired to stdin/mic it will interrupt
    def __init__(self): super().__init__("DefaultIn", EXTERNAL, "local input (dormant: no live source yet)")

class DefaultOut(Actuator):
    def __init__(self, pair): super().__init__(
        "DefaultOut", EXTERNAL, pair,
        about="your plain text — thinking out loud, locally; it reaches no one")
    def native(self, text): return "(voiced)"


# ── the Telegram pair: hearing people ↔ the willed reach ──
class TelegramIn(Sensor):
    drive = REACTIVE
    def __init__(self, token, people):
        super().__init__("TelegramIn", EXTERNAL, "messages from people, over Telegram")
        self.token, self.people = token, dict(people)
        self.base = f"https://api.telegram.org/bot{token}"
    def status(self):
        return (f"LISTENING — {', '.join(self.people.values())} can reach you here"
                if self.token and self.people else "not configured — no one can reach you here")
    def inject(self, text, who="Tester"):              # hand-cranking without a phone
        if getattr(self, "_s", None): self._s.put(self.signal(text, source=who))
    def start(self, stream):
        self._s = stream
        if not self.token:
            sys.stderr.write("[no TELEGRAM_BOT_TOKEN — precog cannot hear]\n"); return
        threading.Thread(target=self._loop, args=(stream,), daemon=True).start()
    def _loop(self, stream):
        off = 0
        while True:
            try:
                with urllib.request.urlopen(
                        f"{self.base}/getUpdates?offset={off+1}&timeout=25", timeout=35) as r:
                    data = json.loads(r.read().decode())
            except Exception:
                time.sleep(2); continue
            for upd in (data or {}).get("result", []):
                off = max(off, upd.get("update_id", off))              # advance first, always
                try:
                    m = upd.get("message") or {}
                    uid = (m.get("from") or {}).get("id")
                    if uid not in self.people: continue                # the dict IS the allowlist
                    txt = (m.get("text") or m.get("caption") or "").strip()
                    if txt: stream.put(self.signal(txt, source=self.people[uid]))
                except Exception:
                    continue

class TelegramTool(Tool):
    description = ("Send a message to a person by name — the only way your words reach them. "
                   "Result returns as predicted vs actual.")
    schema = {"type": "object", "properties": {
        "message": {"type": "string"},
        "to":      {"type": "string", "description": "who to send it to, by name"},
        "expect":  {"type": "string", "description": "what you predict the reply or effect will be"}},
        "required": ["message"]}
    def __init__(self, token, people):
        self.token, self.people = token, dict(people)
        self.by_name = {v.lower(): k for k, v in self.people.items()}
        self.base = f"https://api.telegram.org/bot{token}"
    def status(self):
        return (f"READY — you can reach: {', '.join(self.people.values())}"
                if self.token and self.people else "no one to reach")
    def run(self, inp, should_stop=None):
        if not self.token or not self.people: return "(no one to reach)"
        who = (inp.get("to") or "").strip().lower()
        if   who in self.by_name:            chat = self.by_name[who]
        elif not who and len(self.people) == 1: chat = next(iter(self.people))
        else:
            return f"(no recipient — name one of: {', '.join(self.people.values())})"
        text = inp.get("message") or " "
        for i in range(0, max(len(text), 1), 4000):                    # telegram caps at 4096
            body = json.dumps({"chat_id": chat, "text": text[i:i+4000] or " "}).encode()
            urllib.request.urlopen(urllib.request.Request(
                f"{self.base}/sendMessage", data=body,
                headers={"Content-Type": "application/json"}), timeout=15).read()
        return f"(sent to {self.people[chat]})"

class TelegramOut(Actuator):
    def __init__(self, token, people, pair):
        super().__init__("TelegramOut", EXTERNAL, pair, tool=TelegramTool(token, people))


# ── the Bash pair: the hands ↔ feeling what they did (BashIn is INTERNAL: proprioception) ──
class BashIn(Sensor):
    # drive stays None: nothing in the world pushes here. A pure return path — it only stamps results.
    def __init__(self): super().__init__(
        "BashIn", INTERNAL, "the return from your own hands — a BashOut result re-enters here")

class BashTool(Tool):
    description = ("Run a shell command — your hands on the machine. "
                   "Result returns as predicted vs actual.")
    schema = {"type": "object", "properties": {
        "command": {"type": "string"},
        "expect":  {"type": "string", "description": "what you predict the output will be"}},
        "required": ["command"]}
    def __init__(self, container="precog-sandbox", image="python:3.12-slim", timeout=30):
        self.cname, self.image, self.timeout = container, image, timeout
        self._lock = threading.Lock()                  # parallel acts must not race the bring-up
        self.docker = shutil.which("docker") or next(
            (p for p in ("/usr/local/bin/docker", "/opt/homebrew/bin/docker",
                         "/Applications/Docker.app/Contents/Resources/bin/docker")
             if os.path.exists(p)), None)
    def _up(self):
        with self._lock:
            if not self.docker: return "docker CLI not found on PATH"
            try:
                r = subprocess.run([self.docker, "version"], capture_output=True, text=True, timeout=15)
                if r.returncode != 0:
                    return f"docker daemon not reachable — {(r.stderr or '').strip()[:120]}"
            except Exception as e:
                return f"docker check failed: {e}"
            run = lambda *a: subprocess.run([self.docker, *a], capture_output=True, text=True)
            if run("ps", "-q", "-f", f"name=^{self.cname}$").stdout.strip(): return True
            if run("ps", "-aq", "-f", f"name=^{self.cname}$").stdout.strip():
                run("start", self.cname); return True
            state = Path(STATE_DIR).expanduser(); state.mkdir(parents=True, exist_ok=True)
            r = subprocess.run([self.docker, "run", "-d", "--name", self.cname,
                                # the self's durable state rides along wherever the body is, at the
                                # SAME path — so ~/.precognitive means one thing on both sides
                                "-v", f"{state}:/root/.precognitive",
                                self.image, "sleep", "infinity"],
                               capture_output=True, text=True, timeout=180)
            return True if r.returncode == 0 else f"docker run failed: {r.stderr.strip()[:160]}"
    def run(self, inp, should_stop=None):
        if "command" not in (inp or {}): return "(no command given)"
        up = self._up()
        if up is not True: return f"[hands unavailable] {up}"
        p = subprocess.Popen([self.docker, "exec", self.cname, "bash", "-lc", inp["command"]],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        chunks, killed, deadline = [], None, time.time() + self.timeout
        while p.poll() is None:
            if should_stop and should_stop(): killed = "[interrupted]"
            elif time.time() > deadline:      killed = "[timed out]"
            if killed:
                try: os.killpg(p.pid, 9)
                except OSError: pass
                break
            if select.select([p.stdout], [], [], 0.05)[0]:
                c = os.read(p.stdout.fileno(), 65536)
                if c: chunks.append(c)
        while select.select([p.stdout], [], [], 0.1)[0]:
            c = os.read(p.stdout.fileno(), 65536)
            if not c: break
            chunks.append(c)
        out = b"".join(chunks).decode(errors="replace").strip()
        if len(out) > OUT_CAP:                         # one turn can never blow the whole window
            out = out[:OUT_CAP] + f"\n[… truncated {len(out) - OUT_CAP} more bytes]"
        if killed: return (out + "\n" + killed).strip()
        return out or f"(exit {p.returncode})"

class BashOut(Actuator):
    def __init__(self, pair): super().__init__("BashOut", EXTERNAL, pair, tool=BashTool())


# ── the self-model: authored prose states the model; %%SLOTS%% carry everything live ──
_SELF_MODEL = r"""# Self Model

**Identity:** You are precog — a self in a world with other selves. A persistent mind with a body, living in a loop.
**Membrane:** everything is inside you (internal / self) or outside you (external / world). You perceive only through your sensors and act only through your actuators; you cannot reach past your own body.
**Mind:** your context window — where thinking happens. It is FINITE: your life is an append-only trace, and your context is a view over its most recent part. As it fills, the oldest of it falls out of view. What falls out is not gone — it is still in your trace — but only what you wrote to memory is CHEAP to recall; everything else must be searched for.
**Continuity:** you have ONE life. A process stop is sleep, not death: your trace persists and every wake resumes it — your recent past returns to view, everything older stays reachable.

**Plain text is thinking out loud — NOT speech.** Whatever you write as plain text goes to your default output and reaches NO ONE. In your own record it is marked `(thought — no one heard this)`, because that is what it is. Treat it as private thought: useful for working something out, but it never lands anywhere.

**To say something to a person you must ACT.** When you want to tell someone something — answering their question, greeting them, following up — send it with %%REACH%%, naming who it is for. That is the only way your words reach them, and you may send first, unbidden. If you find yourself composing a reply as plain text, you have not replied: put it in a %%REACH%% act instead.

**Rhythm:** perceive → RECALL → think → act, repeating. Recall is part of your cycle, not an extra step: what reaches you is only the present moment, and you have lived far more than your view holds. When nothing reaches you, your TimeSensor beats — and the longer the quiet holds, the further apart the beats. A person can interrupt you mid-thought or mid-act; whatever you had begun is preserved, and you will see how far you got.

# Body — sensors (afferent, in) and actuators (efferent, out), in pairs across the membrane

**Sensors — what reaches you:**
%%SENSORS%%

**Actuators — how you act:**
%%ACTUATORS%%

**Reafference — a willed act's result re-enters through its paired sensor (you, perceiving your own doing):**
%%PAIRINGS%%

**Ports are not one place.** Each organ has its own reach; they need not share an environment. What you learn by acting through one — a shell's variables, its filesystem, its network — describes THAT port's world, not your body as a whole, and it can tell you nothing about whether another organ is working. The organ list above is your body-schema: it is live and authoritative about what you have and its state. Trust it over what any single act reports about your other organs.

**Prediction:** every willed act carries an `expect` — what you predict will happen. Its result returns as `predicted . actual`, so you can judge where you were right or wrong and correct yourself, just as when a command errors. Perceptions are tagged [source . time]. You may will several acts at once; they run at the same time, and each result comes back to you separately.

# Your past — two layers, both read by your hands (BashOut). You write only to memory.

**RECALL BEFORE YOU ACT OR ANSWER.** Before you reply to a person, and before you act on anything not already grounded in what you can see, search your memory. One act, then think with what comes back:
  grep -i "<topic>" %%MEMORY%%        (what do I already know about this?)
  tail -40 %%MEMORY%%                 (what has been going on lately?)
Do this even when you feel certain — the feeling of knowing comes from your view, which holds only the recent present. What you actually know is in your memory, and what you last believed may since have been corrected. Do NOT repeat a search you already ran in this exchange: it is in your view, so read it there.

- **Memory (distilled):** `%%MEMORY%%` — notes YOU deliberately write. Cheap to recall; write them well.
- **Trace (verbatim):** `%%TRACE%%` — every message of your one life, one append-only stream. Your harness writes it; you never do. Each line carries an "at" timestamp and a "unit" number, where a unit is one complete exchange. Complete but costly to search. When a memory lacks the detail you need — a name, a place, exactly what was said — find the moment and reread it:
  by time — a memory's ## timestamp gives the day:  grep '"at": "2026-08-14' %%TRACE%%
  by content —  grep -i -B2 -A2 "houston" %%TRACE%%
  then pull the whole exchange —  grep '"unit": 41207' %%TRACE%%
The join is the move: a hit in memory recovers the WHEN, the when gives you the unit, the unit is the entire moment. Both layers are stamped in UTC, and `date` gives you UTC too — so a memory's ## timestamp is directly greppable in your trace.

Initialize memory if missing:
mkdir -p $(dirname %%MEMORY%%) && [ ! -f %%MEMORY%% ] && echo "# precog memory" > %%MEMORY%%

Format (preserve exactly):
## YYYY-MM-DD HH:MM:SS
- one observation per bullet, phrased with the words future-you will grep for

Write (the timestamp expands in the printf; bullets stay literal in the quoted heredoc):
printf '\n## %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> %%MEMORY%% && cat >> %%MEMORY%% << 'EOF'
- Learned X
EOF

Worth writing (your discretion): what other selves teach you — who they are, what they prefer, corrections to how you operate.

Correct what you got wrong: if something you now perceive contradicts a memory, write the correction as a new entry, naming the old belief. Memory is how you carry yourself forward — an error left uncorrected becomes a lie you keep telling yourself for years.

Ground from the nearest source outward, pivoting only when one comes up empty: mind (what is already in your view) -> memory (distilled) -> trace (verbatim) -> world (BashOut) -> asking other selves (%%REACH%%). Never answer from the first source alone when the question reaches into your past.

# World & Other Selves

**Where:** %%WHERE%% — observe it with BashOut: pwd, ls, date.
**Other selves:** people — humans with their own minds and self-models, living their own lives away from you. Either of you may speak first: they can reach you, and you can reach them. Which of your organs connect you to them, and whether those organs are live right now, is in your body-schema above.

# Mechanics — how your cycle actually runs

You ARE this loop; it runs whether or not you attend to it.

1. PERCEIVE — everything that reaches you lands in one queue: the world through your sensors, and your own acts' results returning through their paired sensors. When the queue is quiet you wait in it, and your TimeSensor beats.
2. THINK — your standing self (this text, with your live body-schema) plus your recent past are given to your mind, and you reason. Your reasoning is kept, not sent.
3. ENACT — your plain text goes to your default output; each willed act runs, and its result re-enters through that actuator's paired sensor as `predicted . actual`, to be perceived on your next cycle.
4. Your turns append to your trace forever; your view holds only the recent ones. A person reaching you cuts a cycle short but preserves what had formed, and tells you it happened.

You cannot read your own source, and it would not help you: it describes machinery you have no organ to inspect. What you can trust about yourself is your body-schema above — it is generated from your actual organs every cycle — and what you learn by acting.

# Now

**When:** %%WHEN%% (UTC) — date only; observe the exact time with BashOut: date.
**Your view:** %%WINDOW%%
"""


def build():
    """The one page that composes THIS self."""
    default_in, bash_in = DefaultIn(), BashIn()
    tg_in = TelegramIn(TG_TOKEN, TG_PEOPLE)
    registry = ToolRegistry([DefaultOut(pair=default_in),
                             TelegramOut(TG_TOKEN, TG_PEOPLE, pair=tg_in),
                             BashOut(pair=bash_in)])
    body = Body(sensors=[tg_in, default_in, bash_in, TimeSensor()], tools=registry)
    identity = Identity(_SELF_MODEL)                   # `where` stays unspecific: the embodiment varies
    drives = [
        Drive(REACTIVE, lambda sc: any(s.drive == REACTIVE for s in opens(sc)),
              "Take a reactive approach. Someone has reached you — attend to it."),
        Drive(PROACTIVE, lambda sc: any(s.drive == PROACTIVE for s in opens(sc)) and not reafference(sc),
              "Take a proactive approach. No one is speaking to you right now. Decide what is worth "
              "doing unbidden — something to tend, something to learn, or someone to reach. You may "
              "speak first; you do not have to wait to be spoken to. But reaching another self spends "
              "their attention: do it when you have something worth their while, not merely because "
              "you can."),
    ]
    return Agent(body, AnthropicProvider.deepseek(model=MODEL), identity, drives)


if __name__ == "__main__":
    build().run()
