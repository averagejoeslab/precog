"""Validate precog.py with a MOCK provider at the wire boundary (override _call only).
Covers: unit slicing (the atomic slice) · lazy slide on overflow · verbatim view (no rewriting) ·
push-sensors + coalescing · reactive interruption mid-stream and mid-act · reafference shielding ·
stance stickiness · parallel same-tool by name · tail-load + heal · empty-beat drop · never-drop-a-
world-scene · dynamic identity. No real API, telegram, or docker."""
import sys, os, json, time, tempfile, threading
from abc import ABC
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import precog as P

fails = []
def ok(n, c):
    print(("PASS " if c else "FAIL ") + n)
    if not c: fails.append(n)

# ── a scripted mock: entries are block-lists, ("CUT", blocks), or Exceptions to raise ──
class _B:
    def __init__(self, **k): self.__dict__.update(k)
class _R:
    def __init__(self, blocks): self.content = blocks
class Mock(P.AnthropicProvider):
    def __init__(self):
        self.client = self.model = None; self.tb = self.mt = 0; self.voice = "DefaultOut"
        self.script, self.systems, self.views = [], [], []
    def _call(self, system, messages, tools, should_stop):
        self.systems.append(system); self.views.append(messages)
        e = self.script.pop(0)
        if isinstance(e, Exception): raise e
        if isinstance(e, tuple) and e[0] == "CUT": return _R(e[1]), True
        return _R(e), False

PEOPLE = {111: "Bob", 222: "Alice"}
def mk(trace_path=None, people=PEOPLE):
    d_in, b_in = P.DefaultIn(), P.BashIn()
    tg_in = P.TelegramIn("tok", people)
    d_out = P.DefaultOut(pair=d_in)
    tg_out = P.TelegramOut("tok", people, pair=tg_in)
    b_out = P.BashOut(pair=b_in)
    clock = P.TimeSensor(0.02, 0.05)
    reg = P.ToolRegistry([d_out, tg_out, b_out])
    body = P.Body(sensors=[tg_in, d_in, b_in, clock], tools=reg)
    ident = P.Identity(P._SELF_MODEL)
    drives = [
        P.Drive(P.REACTIVE, lambda sc: any(s.drive == P.REACTIVE for s in P.opens(sc)), "REACTIVE-FRAME"),
        P.Drive(P.PROACTIVE, lambda sc: any(s.drive == P.PROACTIVE for s in P.opens(sc))
                                        and not P.reafference(sc), "PROACTIVE-FRAME"),
    ]
    ag = P.Agent(body, Mock(), ident, drives, trace_path=trace_path)
    tg_in._s = body.stream                                    # wire inject without start()
    return ag, body, tg_in, d_out, tg_out, b_out, clock

ag, body, tg_in, d_out, tg_out, b_out, clock = mk()
_voiced, _sent = [], []
d_out.native = lambda t: (_voiced.append(t), "(voiced)")[1]
tg_out.tool.run = lambda inp, ss=None: (_sent.append((inp.get("to"), inp["message"])),
                                        f"(sent to {inp.get('to')})")[1]
b_out.tool.run = lambda inp, ss=None: "OK-RESULT"
prov = ag.provider
NOW = {"when": "2026-07-26", "window": "x"}

def wf(msgs):
    """Valid Anthropic messages — asserting the ACTUAL contract, not stricter:
       · opens on a user turn
       · tool_use is the LAST block of its assistant turn  (anything after it → 400, probed)
       · every tool_use has a non-empty id, answered in the very next message
       · consecutive same-role turns are ALLOWED (documented: they are combined)
       · no harness-authored assistant turn (the assistant turn records the model only)"""
    if not msgs: return True
    if msgs[0]["role"] != "user": return "opens on assistant"
    HARNESS = ("a quiet beat", "sleep took me mid-turn", "a sleep boundary",
               "cut off — something reached you")
    for i, m in enumerate(msgs):
        if m["role"] != "assistant": continue
        types = [b.get("type") for b in m["content"]]
        if "tool_use" in types and types[-1] != "tool_use":
            return f"block after tool_use @{i}: {types}"
        uses = [b.get("id") for b in m["content"] if b.get("type") == "tool_use"]
        if any(not u for u in uses): return f"tool_use with empty id @{i}"
        if uses:
            nxt = msgs[i + 1]["content"] if i + 1 < len(msgs) else []
            res = [b.get("tool_use_id") for b in nxt if b.get("type") == "tool_result"]
            if set(uses) != set(res): return f"unpaired@{i}"
        for b in m["content"]:
            if b.get("type") == "text" and any(h in b["text"] for h in HARNESS):
                return f"harness text in assistant turn @{i}"
    return True

# ═══ 1 · the kit ═══
ok("Tool/Provider are ABCs; Signal/Actuator/Sensor concrete",
   issubclass(P.Tool, ABC) and issubclass(P.Provider, ABC)
   and not getattr(P.Signal, "__abstractmethods__", None)
   and not getattr(P.Actuator, "__abstractmethods__", None))
ok("no ESC subsystem survives",
   not any(hasattr(P.Agent, a) for a in ("_listen", "interrupt"))
   and not any(hasattr(P, n) for n in ("ESC_SAYING", "ESC_DOING")))
ok("sensor drive tags: reactive sources, one proactive, pure return path is None",
   tg_in.drive == P.REACTIVE and P.DefaultIn().drive == P.REACTIVE
   and clock.drive == P.PROACTIVE and P.BashIn().drive is None)
def _try_signal():
    try: P.BashIn().signal("x"); return False
    except AssertionError: return True
ok("a pure return path cannot open a unit (signal() asserts)", _try_signal())
ok("every exposed actuator is paired", all(a.pair is not None for a in body.tools.all() if a.exposed))
ok("BashIn internal (proprioception) · TelegramIn external (hearing yourself)",
   b_out.pair.side == P.INTERNAL and tg_out.pair.side == P.EXTERNAL)
ok("reach organ derived structurally (exposed + pair is external)",
   body.describe()["reach"] == "TelegramOut")

# ═══ 2 · the atomic slice unit ═══
u_open = {"role": "user", "content": [{"type": "text", "text": "[Bob] hi"}]}
u_mid  = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "u1", "content": "r"}]}
ok("opens_unit: tool_result-free user turn only",
   P.opens_unit(u_open) and not P.opens_unit(u_mid)
   and not P.opens_unit({"role": "assistant", "content": []}))
_units = [[u_open, {"role": "assistant", "content": [{"type": "tool_use", "id": "u1", "name": "BashOut", "input": {}}]},
           u_mid, {"role": "assistant", "content": [{"type": "text", "text": "(reasoning) done"}]}],
          [{"role": "user", "content": [{"type": "text", "text": "[TimeSensor] beat"}]},
           {"role": "assistant", "content": [{"type": "text", "text": "(reasoning) quiet"}]}]]
ok("flatten(win=0) is a VERBATIM suffix and well-formed", P.flatten(_units, 0) == _units[0] + _units[1]
   and wf(P.flatten(_units, 0)) is True)
ok("flatten(win=1) drops the whole oldest unit — still verbatim, still well-formed",
   P.flatten(_units, 1) == _units[1] and wf(P.flatten(_units, 1)) is True)
ok("no rewriting anywhere: every message in the view is identity-equal to the trace",
   all(any(m is t for u in _units for t in u) for m in P.flatten(_units, 1)))

# ═══ 3 · the flow: beat → proactive → acts → reafference chains, stance sticky ═══
prov.script = [[_B(type="thinking", thinking="T1"), _B(type="text", text="thinking out loud"),
                _B(type="tool_use", id="u1", name="BashOut", input={"command": "date", "expect": "a date"})]]
body.stream.put(clock.signal("(a quiet moment · beat)"))
ag.step()
ok("beat → PROACTIVE stance", "PROACTIVE-FRAME" in prov.systems[-1])
ok("plain text voiced through DefaultOut, nothing sent", "thinking out loud" in _voiced[-1] and not _sent)
_q = list(body.stream._q.queue)
ok("BashOut result reafferences through BashIn (internal, predicted·actual)",
   len(_q) == 1 and _q[0].source == "BashIn" and _q[0].side == P.INTERNAL
   and _q[0].origin == "self" and _q[0].ref == "u1" and _q[0].predicted == "a date")
ok("unit opened by the beat", len(ag.units) == 1 and len(ag.units[0]) == 2)

prov.script = [[_B(type="thinking", thinking="T2")]]
ag.step()
ok("reafference extends the SAME unit (no new unit)", len(ag.units) == 1 and len(ag.units[0]) == 4)
ok("reafference does NOT reframe — stance stays proactive (sticky)",
   "PROACTIVE-FRAME" in prov.systems[-1])
u = ag.units[0][2]["content"]
ok("reafference rendered as tool_result predicted·actual, paired",
   u[0]["type"] == "tool_result" and u[0]["tool_use_id"] == "u1"
   and "predicted: a date" in u[0]["content"] and "actual: OK-RESULT" in u[0]["content"])

# ═══ 4 · two people at once → one drain, one reframe, two parallel sends by name ═══
tg_in.inject("hey whats up?", who="Bob"); tg_in.inject("can you help?", who="Alice")
prov.script = [[_B(type="tool_use", id="s1", name="TelegramOut", input={"to": "Bob", "message": "hi Bob", "expect": "r"}),
                _B(type="tool_use", id="s2", name="TelegramOut", input={"to": "Alice", "message": "hi Alice", "expect": "r"})]]
ag.step()
_scene_txt = " ".join(b.get("text", "") for b in ag.units[-1][-2]["content"])
ok("both messages arrive in ONE scene, tagged by name",
   "[Bob" in _scene_txt and "[Alice" in _scene_txt)
ok("one reframe → REACTIVE", "REACTIVE-FRAME" in prov.systems[-1])
ok("same tool called twice in parallel, addressed by name",
   sorted(_sent[-2:]) == [("Alice", "hi Alice"), ("Bob", "hi Bob")])
_q = list(body.stream._q.queue)
ok("two sends → two reafferences through ONE TelegramIn, distinguished by ref",
   sorted(s.ref for s in _q) == ["s1", "s2"] and all(s.source == "TelegramIn" for s in _q))
prov.script = [[_B(type="thinking", thinking="T3")]]
ag.step()
ok("history well-formed after the parallel batch", wf(P.flatten(ag.units, 0)) is True)

# unknown recipient reafferences an honest, teaching error
tg_out.tool = P.TelegramTool("tok", PEOPLE)
ok("unknown name → helpful error naming who is reachable",
   "name one of" in tg_out.tool.run({"to": "Bobby", "message": "x"})
   and "Bob" in tg_out.tool.run({"to": "Bobby", "message": "x"}))

# ═══ 5 · lazy slide: drop the OLDEST unit per overflow, until it fits ═══
n0 = len(ag.units)
tg_in.inject("one more", who="Bob")
prov.script = [RuntimeError("Bad request: prompt is too long"),
               RuntimeError("... maximum context length ..."),
               [_B(type="thinking", thinking="T4"), _B(type="text", text="still here")]]
w0 = ag.win; ag.step()
ok("two overflows → win advanced two UNITS (not messages)", ag.win == w0 + 2)
ok("slide never mutates the trace: unit count only grew", len(ag.units) == n0 + 1)
ok("the sent view was a verbatim suffix and valid", wf(prov.views[-1]) is True
   and prov.views[-1] == P.flatten(ag.units, ag.win)[:len(prov.views[-1])])
ok("`fit` reported = units in view", ag.fit == len(ag.units) - ag.win)
try:
    a2, b2, t2, *_ = mk()
    b2.stream.put(t2.signal("hi", source="Bob"))
    a2.provider.script = [RuntimeError("prompt is too long")]
    a2.step(); guard = False
except RuntimeError as e:
    guard = "current unit alone will not fit" in str(e)
ok("guard: the current unit is never evictable", guard)

# ═══ 6 · interruption = a reactive arrival. mid-stream, then mid-act. ═══
ok("interrupting() is driven by pending REACTIVE only", not body.stream.interrupting())
body.stream.put(clock.signal("(beat)"))
ok("a beat never makes interrupting() true", not body.stream.interrupting())
body.stream.drain()
body.stream.put(tg_in.signal("stop!", source="Bob"))
ok("a person's arrival makes interrupting() true", body.stream.interrupting())

# mid-stream cut: partial voiced, un-run acts answered synthetically, no marker signal injected
prov.script = [("CUT", [_B(type="thinking", thinking="partial"), _B(type="text", text="I was about to"),
                        _B(type="tool_use", id="k1", name="BashOut", input={"command": "sleep 99", "expect": "long"}),
                        _B(type="tool_use", id="k2", name="BashOut", input=None)])]
ag.step()
_q = list(body.stream._q.queue)
ok("mid-stream cut: the partial thought was still voiced", "I was about to" in _voiced[-1])
_rec = ag.units[-1][-1]
ok("mid-stream cut: NO harness text in the assistant turn",
   _rec["role"] == "assistant"
   and not any("cut off" in b.get("text", "") for b in _rec["content"]))
ok("mid-stream cut: tool_use is the LAST block (the crash shape is unreachable)",
   [b["type"] for b in _rec["content"]][-1] == "tool_use")
ok("mid-stream cut: the note is owed to the NEXT user turn, not written here",
   ag.notes == [P.CUT_NOTE])
ok("mid-stream cut: un-run acts get synthetic reafference through BashIn",
   any(s.ref == "k1" and s.source == "BashIn" and "never ran" in str(s.content) for s in _q)
   and any(s.ref == "k2" and "cut off before it was fully formed" in str(s.content) for s in _q))
ok("no synthetic operator signal is injected", not any(s.source == "operator" for s in _q))
prov.script = [[_B(type="thinking", thinking="T5")]]
ag.step()
ok("history still well-formed after a mid-stream cut", wf(P.flatten(ag.units, 0)) is True)
ok("the cut note was delivered in the following USER turn, after the tool_results",
   (lambda c: any(b.get("text") == P.CUT_NOTE for b in c)
              and [b.get("type") for b in c].index("text") > 0)(ag.units[-1][-2]["content"])
   and ag.notes == [])

# mid-act cut: the tool sees should_stop and keeps its partial output
def slow(inp, should_stop=None):
    body.stream.put(tg_in.signal("wait", source="Bob"))            # a person arrives DURING the act
    return "PARTIAL-OUT\n[interrupted]" if should_stop and should_stop() else "FULL"
b_out.tool.run = slow
tg_in.inject("run it", who="Bob")
prov.script = [[_B(type="tool_use", id="m1", name="BashOut", input={"command": "long", "expect": "done"})]]
ag.step()
_q = list(body.stream._q.queue)
ok("mid-act cut: partial output preserved in the reafference",
   any(s.ref == "m1" and "PARTIAL-OUT" in str(s.content) and "[interrupted]" in str(s.content) for s in _q))
b_out.tool.run = lambda inp, ss=None: "OK-RESULT"

# ═══ 7 · coalescing: interoception is level-triggered ═══
body.stream.drain()
for _ in range(4): body.stream.put(clock.signal("(beat n)"))
body.stream.put(tg_in.signal("hello", source="Alice"))
sc = body.stream.drain()
ok("four beats coalesce to one; the person's message is untouched",
   sum(1 for s in sc if s.drive == P.PROACTIVE) == 1 and sum(1 for s in sc if s.drive == P.REACTIVE) == 1)
clock.beats = 5; clock.perceived(sc)
ok("perceived() hook aroused the clock on a reactive arrival", clock.beats == 0)

# ═══ 8 · empty beats dropped; scenes that perceived the world never dropped ═══
ag2, body2, tg2, d2, t2b, b2b, clk2 = mk()
d2.native = lambda t: "(voiced)"
body2.stream.put(clk2.signal("(a quiet beat)"))
ag2.provider.script = [[_B(type="thinking", thinking="nothing to do")]]
ag2.step()
ok("a beat that produced neither voice nor act leaves NO unit", len(ag2.units) == 0)
tg2.inject("hello", who="Bob")
ag2.provider.script = [[_B(type="thinking", thinking="only thinking, no reply")]]
ag2.step()
ok("a scene that perceived a person is KEPT even with no acts (never lose the only record)",
   len(ag2.units) == 1 and "[Bob" in str(ag2.units[0][0]))

# ═══ 9 · one life: journal per message with a unit id, tail-load, heal ═══
tp = os.path.join(tempfile.mkdtemp(prefix="val_life_"), "trace.jsonl")
ag3, body3, tg3, d3, t3, b3, clk3 = mk(trace_path=tp)
d3.native = lambda t: "(voiced)"; t3.tool.run = lambda inp, ss=None: "(sent to Bob)"
tg3.inject("remember me", who="Bob")
ag3.provider.script = [[_B(type="text", text="noted"),
                        _B(type="tool_use", id="j1", name="TelegramOut", input={"to": "Bob", "message": "ok", "expect": "r"})]]
ag3.step()
ag3.provider.script = [[_B(type="thinking", thinking="done")]]
ag3.step()
rows = [json.loads(l) for l in open(tp)]
ok("journal: wake event carries the remembered fit",
   rows[0]["event"] == "wake" and isinstance(rows[0]["fit"], int))
ok("journal: one line per MESSAGE, each tagged with its unit",
   all("unit" in r for r in rows if "role" in r)
   and len({r["unit"] for r in rows if "role" in r}) == 1)
ok("journal: flushed per turn (all four messages already on disk)",
   sum(1 for r in rows if "role" in r) == 4)

ag4, *_ = mk(trace_path=tp)                                 # stop → start: the SAME life resumes
ok("wake: the life is reloaded and regrouped into units",
   len(ag4.units) == 1 and len(ag4.units[0]) == 4)
ok("wake: born date recovered from the first line", ag4.born is not None)

with open(tp, "a") as f:                                    # died mid-turn: a dangling user turn
    f.write(json.dumps({"unit": 9, "at": "x", "role": "user",
                        "content": [{"type": "text", "text": "[Bob] dangling"}]}) + "\n")
ag5, *_ = mk(trace_path=tp)
ok("wake: a dangling user turn is left ALONE (no invented assistant turn; merging handles it)",
   ag5.units[-1][-1]["role"] == "user" and "dangling" in str(ag5.units[-1][-1])
   and wf(P.flatten(ag5.units, 0)) is True)

tp2 = os.path.join(tempfile.mkdtemp(prefix="val_life2_"), "trace.jsonl")
with open(tp2, "w") as f:                                   # died after willing an act
    f.write(json.dumps({"unit": 1, "at": "x", "role": "user", "content": [{"type": "text", "text": "[Bob] go"}]}) + "\n")
    f.write(json.dumps({"unit": 1, "at": "x", "role": "assistant",
                        "content": [{"type": "tool_use", "id": "zz", "name": "BashOut", "input": {"command": "x"}}]}) + "\n")
ag6, *_ = mk(trace_path=tp2)
ok("heal: a dangling tool_use gets a synthetic result + boundary (opens_unit restored)",
   wf(P.flatten(ag6.units, 0)) is True
   and any(b.get("tool_use_id") == "zz" and "asleep before" in b["content"]
           for t in ag6.units[-1] for b in t["content"] if isinstance(b, dict))
   and P.opens_unit(ag6.units[0][0]))

tp3 = os.path.join(tempfile.mkdtemp(prefix="val_life3_"), "trace.jsonl")
with open(tp3, "w") as f:                                   # a leading PARTIAL unit must be discarded
    f.write(json.dumps({"unit": 5, "at": "x", "role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": "old", "content": "r"}]}) + "\n")
    f.write(json.dumps({"unit": 5, "at": "x", "role": "assistant", "content": [{"type": "text", "text": "(reasoning) x"}]}) + "\n")
    f.write(json.dumps({"unit": 6, "at": "x", "role": "user", "content": [{"type": "text", "text": "[Bob] clean"}]}) + "\n")
    f.write(json.dumps({"unit": 6, "at": "x", "role": "assistant", "content": [{"type": "text", "text": "(reasoning) y"}]}) + "\n")
ag7, *_ = mk(trace_path=tp3)
ok("wake: a leading partial unit is discarded so the view needs no rewriting",
   len(ag7.units) == 1 and P.opens_unit(ag7.units[0][0]) and wf(P.flatten(ag7.units, 0)) is True)

# ═══ 10 · the dynamic identity ═══
sysp = ag.identity.render(body.describe(), NOW)
ok("organ lists + pairings generated from the live body",
   "- TelegramIn — messages from people" in sysp and "- BashOut — Run a shell command" in sysp
   and "- BashOut → returns through BashIn" in sysp)
ok("liveness generated: who can reach it, who it can reach",
   "LISTENING — Bob, Alice can reach you here" in sysp and "READY — you can reach: Bob, Alice" in sysp)
ok("%%REACH%% named from the live body", "send it with TelegramOut, naming who" in sysp
   and "%%REACH%%" not in sysp)
ok("plain text framed as thought, not speech",
   "Plain text is thinking out loud — NOT speech" in sysp and "reaches NO ONE" in sysp)
ok("memory asymmetry stated: reads either, writes only memory",
   "You write only to memory" in sysp and "Your harness writes it; you never do" in sysp)
ok("the unit is taught as a recall primitive", '"unit": 41207' in sysp)
ok("no source dump, no unverifiable config",
   "```python" not in sysp and all(k not in sysp for k in
   ("TELEGRAM_BOT_TOKEN", "TELEGRAM_PEOPLE", "os.environ", "DEEPSEEK_API_KEY", "docker", "container")))
ok("prompt is lean (<3k tokens)", len(sysp) // 4 < 3000)
_new = P.Sensor("WebhookIn", P.EXTERNAL, "HTTP webhooks")
body.sensors.append(_new)
ok("adding a sensor updates the self-model with no prompt edit",
   "- WebhookIn — HTTP webhooks" in ag.identity.render(body.describe(), NOW))
body.sensors.remove(_new)

# ═══ 11 · act results are capped so one turn can never blow the window ═══
ok("OUT_CAP exists and is modest", 1000 < P.OUT_CAP < 100000)

# ═══ 12 · ONE CLOCK: the journal is UTC, so a memory's ## timestamp is greppable in the trace ═══
import datetime as _dt
ok("stamp() is UTC and tz-aware", P.now().tzinfo is not None
   and abs((P.now() - _dt.datetime.now(_dt.timezone.utc)).total_seconds()) < 2)
ok("Signal.at is UTC-aware (so render/trace/memory all agree)",
   P.Signal("x", P.EXTERNAL).at.tzinfo is not None)
_rows = [json.loads(l) for l in open(tp)]
_parsed = [P.parse_at(r["at"]) for r in _rows if r.get("at")]
ok("every journalled 'at' the code wrote is UTC-aware",
   len([d for d in _parsed if d]) >= 5 and all(d.tzinfo is not None for d in _parsed if d))
ok("parse_at degrades to None on junk rather than raising", P.parse_at("x") is None)
ok("a UTC `date`-style memory stamp prefix-matches the trace's 'at' (the JOIN works)",
   any(r["at"].startswith(P.now().strftime("%Y-%m-%d")) for r in _rows if r.get("at")))

# ═══ 13 · the beat never asserts what is false ═══
c = P.TimeSensor(0.01, 0.02)
ok("newborn: no claim about the past", c.last is None)
c.resume(P.now() - _dt.timedelta(hours=4, minutes=3))
ok("after wake: resume() seeds the real gap", c.last is not None
   and P.human(P.now() - c.last) == "4h 3m")
_q3 = []
class _S:
    def put(self, s): _q3.append(s)
c.beats = 0; c._stir.clear()
threading.Thread(target=c._beat, args=(_S(),), daemon=True).start(); time.sleep(0.08)
ok("a beat after sleep reports the gap, NOT 'first moment'",
   _q3 and "quiet for 4h" in str(_q3[0].content) and "first moment" not in str(_q3[0].content))
ok("human() formats plainly", (P.human(_dt.timedelta(seconds=45)) == "45s"
   and P.human(_dt.timedelta(minutes=7)) == "7m" and P.human(_dt.timedelta(hours=2)) == "2h"))

# ═══ 14 · the assistant turn records the MODEL only ═══
_p = P.AnthropicProvider.__new__(P.AnthropicProvider)
class _TU:
    type, id, name, input = "tool_use", "u9", "BashOut", {"command": "x"}
ok("_record has no `cut` parameter — the bug is unreachable, not corrected",
   "cut" not in P.AnthropicProvider._record.__code__.co_varnames)
ok("_record returns None when the model produced nothing (no invented turn)",
   _p._record("", "", []) is None)
_r = _p._record("thought hard", "said aloud", [_TU()])
ok("_record: labels kept, tool_use LAST",
   [b["type"] for b in _r["content"]] == ["text", "text", "tool_use"]
   and _r["content"][0]["text"].startswith("(reasoning)")
   and _r["content"][1]["text"].startswith("(thought — no one heard this)"))
class _NoId:
    type, id, name, input = "tool_use", None, "BashOut", {}
class _Resp:
    content = [_TU(), _NoId()]
ok("_parse drops a tool_use with no id (the second unpaired path)",
   len(P.AnthropicProvider._parse(_Resp())[2]) == 1)
_h = [[{"role": "user", "content": [{"type": "text", "text": "[Bob] x"}]},
       {"role": "assistant", "content": [{"type": "tool_use", "id": "z", "name": "BashOut", "input": {}}]}]]
P.heal(_h)
ok("heal synthesizes only tool_results — no invented assistant turn",
   len(_h[0]) == 3 and _h[0][2]["role"] == "user"
   and _h[0][2]["content"][0]["tool_use_id"] == "z")
_h2 = [[{"role": "user", "content": [{"type": "text", "text": "[Bob] dangling"}]}]]
P.heal(_h2)
ok("heal leaves a dangling USER turn alone (consecutive user turns merge)", len(_h2[0]) == 1)

# ═══ 15 · the REAL API accepts what a cut now produces ═══
if os.environ.get("DEEPSEEK_API_KEY") and os.environ.get("VAL_LIVE"):
    from anthropic import Anthropic
    _c = Anthropic(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com/anthropic")
    _T = [{"name": "BashOut", "description": "run",
           "input_schema": {"type": "object", "properties": {"command": {"type": "string"}},
                            "required": ["command"]}}]
    _live = [{"role": "user", "content": [{"type": "text", "text": "[Bob · 10:00] do it"}]},
             _p._record("reasoning here", "saying here", [_TU()]),
             {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "u9", "content": "[interrupted — never ran]"},
                 {"type": "text", "text": "[Bob · 10:01] wait, stop"},
                 {"type": "text", "text": P.CUT_NOTE}]}]
    try:
        _c.messages.create(model=P.MODEL, max_tokens=16, tools=_T,
                           thinking={"type": "disabled"}, messages=_live)
        ok("LIVE: the real API accepts a cut-turn history", True)
    except Exception as e:
        ok(f"LIVE: the real API accepts a cut-turn history — {str(e)[:90]}", False)
else:
    print("SKIP  LIVE api check (set VAL_LIVE=1 to run it)")

print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
