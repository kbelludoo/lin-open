# B6_LOGIC_V1: Deductive Agent Capability & Policy Inference (Nim Engine)
import std/[strutils, sequtils, times, sets, algorithm]

type
  Binding = object
    origin: string
    target: string
    cap: string

  Diagnostics = object
    nodesExplored: int
    backtracks: int
    unificationsAttempted: int
    unificationsSucceeded: int

proc cmpBindings(a, b: Binding): int =
  let c1 = cmp(a.origin, b.origin)
  if c1 != 0: return c1
  let c2 = cmp(a.target, b.target)
  if c2 != 0: return c2
  return cmp(a.cap, b.cap)

proc loadAndSolve(diag: var Diagnostics): (seq[Binding], seq[Binding], int64) =
  var caps = initHashSet[string]()
  let rawCaps = [
    ("ag_01", "cap_read"), ("ag_01", "cap_write"), ("ag_01", "cap_delegate"),
    ("ag_02", "cap_read"), ("ag_02", "cap_transform"),
    ("ag_03", "cap_audit"),
    ("ag_04", "cap_read"), ("ag_04", "cap_delegate"),
    ("ag_05", "cap_transform"),
    ("ag_06", "cap_write"),
    ("ag_07", "cap_audit"),
    ("ag_08", "cap_read"),
    ("ag_09", "cap_transform"),
    ("ag_10", "cap_delegate")
  ]
  for (a, c) in rawCaps:
    caps.incl(a & ":" & c)

  var activeContracts = initHashSet[string]()
  for a in ["ag_01", "ag_02", "ag_04", "ag_05", "ag_06", "ag_08", "ag_09", "ag_10"]:
    activeContracts.incl(a)

  let trustEdges = [
    ("ag_01", "ag_02", 4),
    ("ag_01", "ag_04", 5),
    ("ag_02", "ag_05", 3),
    ("ag_04", "ag_08", 4),
    ("ag_04", "ag_09", 2),
    ("ag_06", "ag_01", 5),
    ("ag_06", "ag_07", 3),
    ("ag_07", "ag_03", 4),
    ("ag_10", "ag_06", 4)
  ]

  let allCaps = ["cap_read", "cap_write", "cap_audit", "cap_delegate", "cap_transform"]

  let t0 = cpuTime()

  var direct: seq[Binding] = @[]
  for (fromAg, toAg, level) in trustEdges:
    diag.nodesExplored.inc
    diag.unificationsAttempted.inc
    if level >= 3:
      diag.unificationsSucceeded.inc
      diag.unificationsAttempted.inc
      if toAg in activeContracts:
        diag.unificationsSucceeded.inc
        diag.unificationsAttempted.inc
        if (fromAg & ":cap_delegate") in caps:
          diag.unificationsSucceeded.inc
          for c in allCaps:
            diag.unificationsAttempted.inc
            if (fromAg & ":" & c) in caps:
              diag.unificationsSucceeded.inc
              direct.add(Binding(origin: fromAg, target: toAg, cap: c))
            else:
              diag.backtracks.inc
        else:
          diag.backtracks.inc
      else:
        diag.backtracks.inc
    else:
      diag.backtracks.inc

  var rawDerivations = direct
  var frontier: seq[(string, string, string, int)] = @[]
  for b in direct:
    if b.cap == "cap_delegate":
      frontier.add((b.origin, b.target, b.cap, 1))

  while frontier.len > 0:
    let (orig, interm, _, depth) = frontier.pop()
    if depth > 10: continue
    diag.nodesExplored.inc
    for next in direct:
      diag.unificationsAttempted.inc
      if next.origin == interm:
        diag.unificationsSucceeded.inc
        rawDerivations.add(Binding(origin: orig, target: next.target, cap: next.cap))
        if next.cap == "cap_delegate":
          frontier.add((orig, next.target, next.cap, depth + 1))
      else:
        diag.backtracks.inc

  let t1 = cpuTime()
  let wallTimeUs = int64((t1 - t0) * 1_000_000.0)

  var distinctSet = initHashSet[string]()
  var distinctList: seq[Binding] = @[]
  for d in rawDerivations:
    let key = d.origin & ":" & d.target & ":" & d.cap
    if key notin distinctSet:
      distinctSet.incl(key)
      distinctList.add(d)

  distinctList.sort(cmpBindings)
  return (rawDerivations, distinctList, wallTimeUs)

proc main() =
  var diag = Diagnostics()
  let (rawDerivs, distinctList, wallTimeUs) = loadAndSolve(diag)

  let totalCount = rawDerivs.len
  let distinctCount = distinctList.len
  let eliminated = totalCount - distinctCount

  var bindingsJson = "["
  for i, b in distinctList:
    if i > 0: bindingsJson.add(",")
    bindingsJson.add("{\"?Cap\":\"" & b.cap & "\",\"?Origin\":\"" & b.origin & "\",\"?Target\":\"" & b.target & "\"}")
  bindingsJson.add("]")

  echo "{\"engine\":\"nim-native\",\"version\":\"2.2.0\",\"spec_id\":\"B6_LOGIC_V1\",\"status\":\"SUCCESS\",\"solutions_distinct\":" & $distinctCount & ",\"solutions_total_derivations\":" & $totalCount & ",\"duplicate_bindings_eliminated\":" & $eliminated & ",\"diagnostics\":{\"nodes_explored\":" & $diag.nodesExplored & ",\"backtracks\":" & $diag.backtracks & ",\"unifications_attempted\":" & $diag.unificationsAttempted & ",\"unifications_succeeded\":" & $diag.unificationsSucceeded & ",\"wall_time_us\":" & $wallTimeUs & "},\"bindings\":" & bindingsJson & "}"

when isMainModule:
  main()
