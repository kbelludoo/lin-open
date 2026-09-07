#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lin-obfuscate — safe obfuscator for LIN sources (stdlib only).

Renames ONLY user-owned identifiers, preserving everything the toolchain
matches by name. Verified against compiler/lin.zig (VmComp) and
transpile/c/tool/lin_c0_front.c:

NEVER renamed (denylist):
  - string literal contents ("...") — semantic (ex. zig_ty compares them)
  - @-directives: whole @LIN:... header lines, @NAME{...} metadata lines,
    and any @ident token in code (ex. @rem intrinsic in C0)
  - _-led identifiers (_lia_shl/_lia_shr/..., _ helpers) — matched by name
  - identifiers right after a dot (.length/.charCodeAt/.charAt/...) — idem
  - keywords/types: while, continue, true, false, int, string, bool, any
  - callees not defined in the input set (host builtins: skip_ws,
    read_ident, slice2, jss_trim, starts_lit, ...) — keeps linkage
  - // comments are dropped (never renamed, never kept)

Renamed (uniform textual substitution, so semantics/steps are unchanged):
  - fn names defined with `!name(` (global map across the input set,
    so cross-file calls keep working)
  - params and assigned locals `name =` (per-file map; VM locals are
    per-function, a file-global 1:1 map stays correct)

Receipts bind the source hash (R4), so regenerate receipts from the
obfuscated output: it is a NEW source with a NEW digest.

Usage:
  python3 tools/lin_obfuscate.py in.lin -o out.lin [--minify] [--keep-exports]
  python3 tools/lin_obfuscate.py a.lin b.lin --out-dir dist/ [--minify]
  python3 tools/lin_obfuscate.py in.lin --map-out map.json   # audit trail

Validate afterwards (gates that matter):
  zig-out/bin/lin_native check out.lin
  zig-out/bin/lin_native vm out.lin <fn> [args...]   # value+steps must match
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

IDENT = r"[A-Za-z_$][A-Za-z0-9_$]*"
FN_DEF_RE = re.compile(r"!(?!=)\s*([A-Za-z_$][A-Za-z0-9_$]*)\s*\(([^()]*)\)")
ASSIGN_RE = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*(?<![=!<>])=(?![=>])")
CALL_RE = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
PARAM_RE = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*:")
EXPORTS_RE = re.compile(r"=ex\{(.*?)\}")
STR_RE = re.compile(r'"(?:\\.|[^"\\])*"')

# Never emitted as generated names, never renamed when occurring as code.
KEYWORDS = {
    "while", "continue", "true", "false",
    "int", "string", "bool", "any",
    "if", "else", "for", "return", "let", "var", "const",
    "ex",  # =ex{...} directive keyword
}


def split_segments(src: str):
    """Yield (kind, text): 'str' | 'directive' | 'code' | 'nl'.

    Comments (// outside strings) are dropped here.
    """
    i, n = 0, len(src)
    buf: list[str] = []

    def flush_code():
        if buf:
            yield ("code", "".join(buf))
            buf.clear()

    while i < n:
        c = src[i]
        if c == '"':
            m = STR_RE.match(src, i)
            if not m:  # unterminated: keep rest as code, fail closed later
                buf.append(src[i:])
                break
            yield from flush_code()
            yield ("str", m.group(0))
            i = m.end()
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            yield from flush_code()
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "@" and (not buf or "".join(buf).strip() == ""):
            # directive at line start (possibly multi-line @NAME{...} block)
            end = directive_end(src, i)
            yield from flush_code()
            yield ("directive", src[i:end])
            i = end
            continue
        if c == "\n":
            buf.append(c)
            yield from flush_code()
            i += 1
            continue
        buf.append(c)
        i += 1
    yield from flush_code()


def directive_end(src: str, start: int) -> int:
    """End offset of an @-directive starting at `start` (line start).

    Single line normally; if the first line opens `{`, extend through the
    balanced closing `}` (string-aware) — metadata blocks like
    @SPEC{...} spanning lines are verbatim, never code.
    """
    line_end = src.find("\n", start)
    if line_end == -1:
        line_end = len(src)
    first = src[start:line_end]
    if "{" not in first:
        return line_end
    depth = 0
    i = start
    n = len(src)
    ins = False
    while i < n:
        c = src[i]
        if ins:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == '"':
                ins = False
            i += 1
            continue
        if c == '"':
            ins = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n  # unbalanced: take rest (fail closed downstream at check)


def code_idents_with_ctx(code: str):
    """Yield (ident, prev_sig_char) for each ident token in code."""
    for m in re.finditer(IDENT, code):
        s = m.group(0)
        j = m.start() - 1
        while j >= 0 and code[j] in " \t":
            j -= 1
        prev = code[j] if j >= 0 else ""
        yield s, prev


def short_names(taken: set[str]):
    """Deterministic generator: a..z, a0.., aa.. — never $-/_-led, never taken."""
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    n = 0
    while True:
        if n < 26:
            cand = alphabet[n]
        else:
            k, rest = divmod(n - 26, 26)
            cand = alphabet[k % 26] + (alphabet[rest] if k >= 26 else alphabet[rest])
            if k >= 26:
                cand = f"o{n}"
        n += 1
        if cand in taken or cand in KEYWORDS:
            continue
        taken.add(cand)
        yield cand


def obfuscate(sources: dict[str, str], keep_exports: bool, minify: bool):
    segs_of = {name: list(split_segments(src)) for name, src in sources.items()}
    code_of = {
        name: "".join(t for k, t in segs if k == "code")
        for name, segs in segs_of.items()
    }

    # 1. defined fns across the whole input set (global map: cross-file safe)
    fn_defs: list[str] = []
    seen_fn: set[str] = set()
    for code in code_of.values():
        for m in FN_DEF_RE.finditer(code):
            if m.group(1) not in seen_fn:
                seen_fn.add(m.group(1))
                fn_defs.append(m.group(1))

    exports_of: dict[str, list[str]] = {}
    for name, src in sources.items():
        m = EXPORTS_RE.search(src)
        exports_of[name] = (
            [e.strip() for e in m.group(1).split(",") if e.strip()]
            if m else []
        )
    exported = (
        {e for v in exports_of.values() for e in v} if keep_exports else set()
    )

    # names that exist anywhere (generated names must avoid them)
    all_idents: set[str] = set()
    for code in code_of.values():
        for ident, _ in code_idents_with_ctx(code):
            all_idents.add(ident)

    taken = set(all_idents) | KEYWORDS
    gen = short_names(taken)

    fn_map: dict[str, str] = {}
    for fn in fn_defs:
        if fn.startswith("_") or fn in KEYWORDS or fn in exported:
            continue
        fn_map[fn] = next(gen)

    # 2. per-file params + assigned locals. Guard: a name that is CALLED
    #    (`name(`) but never DEFINED in the input set is a host builtin
    #    (skip_ws, q, ...) — renaming it would break linkage, so keep it.
    called_undefined: dict[str, set[str]] = {}
    for name, code in code_of.items():
        s: set[str] = set()
        for m in CALL_RE.finditer(code):
            j = m.start(1) - 1
            while j >= 0 and code[j] in " \t":
                j -= 1
            if j >= 0 and code[j] in ".@":
                continue
            callee = m.group(1)
            if callee not in seen_fn and callee not in KEYWORDS:
                s.add(callee)
        called_undefined[name] = s

    out: dict[str, str] = {}
    maps: dict[str, dict[str, str]] = {}
    for name, segs in segs_of.items():
        code = code_of[name]
        host_calls = called_undefined[name]
        cands: list[str] = []
        seen_c: set[str] = set()

        def consider(ident: str):
            if ident in seen_c or ident in fn_map:
                return
            seen_c.add(ident)
            if ident.startswith("_") or ident in KEYWORDS:
                return
            if ident in host_calls:
                return  # host builtin linkage: keep verbatim
            cands.append(ident)

        for m in FN_DEF_RE.finditer(code):  # params of each def
            for p in PARAM_RE.finditer(m.group(2)):
                consider(p.group(1))
        for m in ASSIGN_RE.finditer(code):  # `name =` binds a VM local
            j = m.start(1) - 1
            while j >= 0 and code[j] in " \t":
                j -= 1
            if j >= 0 and code[j] == ".":
                continue
            consider(m.group(1))
        var_map = {v: next(gen) for v in cands}
        full_map = {**fn_map, **var_map}
        maps[name] = full_map

        # 3. rewrite code segments only (strings/directives byte-identical);
        #    skip idents after `.` (methods) or `@` (@rem intrinsic)
        def make_repl(seg: str):
            def repl(m: re.Match) -> str:
                ident = m.group(0)
                j = m.start() - 1
                while j >= 0 and seg[j] in " \t":
                    j -= 1
                prev = seg[j] if j >= 0 else ""
                if prev == "." or prev == "@":
                    return ident
                return full_map.get(ident, ident)

            return repl

        # assemble: directives keep their lines; body pretty or minified
        directives = [t for k, t in segs if k == "directive"]
        # body = code+strings interleaved, in original order
        body_segs: list[str] = []
        for k, t in segs:
            if k == "code":
                body_segs.append(re.sub(IDENT, make_repl(t), t))
            elif k == "str":
                body_segs.append(t)
        body = "".join(body_segs)

        def ex_repl(m: re.Match) -> str:
            items = [e.strip() for e in m.group(1).split(",")]
            return "=ex{" + ",".join(full_map.get(e, e) for e in items) + "}"

        if minify:
            body = re.sub(r"[ \t]+", " ", body)
            body = re.sub(r"\s*\n\s*", " ", body)
            body = re.sub(r"\s*([(){}\[\];,:!?^=<>+\-*/|&%@.])\s*", r"\1", body)
            body = body.strip()
            text = "\n".join(d.rstrip() for d in directives) + "\n" + body + "\n"
        else:
            body = re.sub(r"[ \t]+", " ", body)
            body = re.sub(r"\n\s*\n+", "\n", body).strip() + "\n"
            text = "\n".join(d.rstrip() for d in directives) + "\n" + body
        # directives already emitted; drop the duplicated originals is
        # unnecessary: body no longer contains them (they were segments)
        text = EXPORTS_RE.sub(ex_repl, text, count=1) if "=ex{" in text else text
        out[name] = text
    return out, maps


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Safe LIN obfuscator (stdlib only).")
    ap.add_argument("inputs", nargs="+", help=".lin input files")
    ap.add_argument("-o", "--output", help="output file (single input only)")
    ap.add_argument("--out-dir", help="output dir (multi-file, global fn map)")
    ap.add_argument("--minify", action="store_true",
                    help="collapse whitespace (directives keep their lines)")
    ap.add_argument("--keep-exports", action="store_true",
                    help="do not rename fns listed in =ex{} (external callers)")
    ap.add_argument("--map-out", help="write rename map JSON (audit trail)")
    args = ap.parse_args(argv)

    if args.output and (len(args.inputs) != 1 or args.out_dir):
        print("error: -o takes exactly one input and no --out-dir", file=sys.stderr)
        return 2

    sources: dict[str, str] = {}
    for f in args.inputs:
        p = Path(f)
        if not p.is_file():
            print(f"error: not found: {f}", file=sys.stderr)
            return 2
        sources[f] = p.read_text(encoding="utf-8")

    out, maps = obfuscate(sources, args.keep_exports, args.minify)

    if args.out_dir:
        d = Path(args.out_dir)
        d.mkdir(parents=True, exist_ok=True)
        for f, text in out.items():
            (d / Path(f).name).write_text(text, encoding="utf-8")
            print(f"wrote {d / Path(f).name}")
    elif args.output:
        Path(args.output).write_text(out[args.inputs[0]], encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(out[args.inputs[0]])

    if args.map_out:
        Path(args.map_out).write_text(
            json.dumps(maps, indent=2, sort_keys=True), encoding="utf-8"
        )
        print(f"map: {args.map_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
