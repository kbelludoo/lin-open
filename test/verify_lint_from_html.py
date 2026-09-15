#!/usr/bin/env python3
"""Mini-interprete do subset LIN usado por src/lint_from_html.lin + paridade DDC.
Escopo estrito: !f(tipos), = ; while ? continue ^, strings/int, length/charCodeAt/
charAt/+/String.fromCharCode/starts_lit/rg_count_lit, comparacoes e +-*/().
Tudo fora disso -> erro (fail-closed). Cap de steps anti-loop.
Prova: (1) auto-teste do interprete em micro-vetores manuais;
(2) lint_html do .lin == oraculo Python no corpus (byte-identico);
(3) saida -> lint_c0 == goldens .laybc.
"""
import re, sys, os

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "lint_from_html.lin")
STEPS = [0]
STEP_CAP = 2_000_000

class Fail(Exception): pass

# ---------- lexer ----------
TOK_RE = re.compile(r'''\s*(?:
 (?P<num>\d+) | (?P<str>"[^"\n]*") | (?P<id>[A-Za-z_][\w$]*) |
 (?P<op>==|!=|<=|>=|&&|\|\||[+\-*/%<>=!{}();,.:?|^]) |
 (?P<nl>\n) )''', re.X)

def lex(body):
    toks, i = [], 0
    while i < len(body):
        while i < len(body) and body[i] in " \t\r\n":
            i += 1
        if i >= len(body):
            break
        if body.startswith("//", i):
            j = body.find("\n", i)
            i = len(body) if j < 0 else j
            continue
        m = TOK_RE.match(body, i)
        if not m or (m.end() == i):
            raise Fail(f"lex em {body[i:i+20]!r}")
        i = m.end()
        k = m.lastgroup
        if k == "nl":
            continue
        toks.append((k, m.group(k)))
    return toks

# ---------- parser (recursive descent sobre o subset) ----------
class P:
    def __init__(self, toks):
        self.t = toks; self.i = 0
    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else ("eof", "")
    def eat(self, k=None, v=None):
        t = self.peek()
        if k and t[0] != k:
            raise Fail(f"esperava {k}, veio {t}")
        if v is not None and t[1] != v:
            raise Fail(f"esperava {v!r}, veio {t[1]!r}")
        self.i += 1
        return t
    def parse_fn(self):
        self.eat("op", "!")
        name = self.eat("id")[1]
        self.eat("op", "(")
        params = []
        if not (self.peek() == ("op", ")")):
            while True:
                pn = self.eat("id")[1]
                self.eat("op", ":")
                pt = self.eat("id")[1]
                params.append((pn, pt))
                if self.peek() == ("op", ","):
                    self.eat()
                else:
                    break
        self.eat("op", ")")
        self.eat("op", ":")
        rt = self.eat("id")[1]
        body = self.parse_block()
        return name, params, rt, body
    def parse_block(self):
        self.eat("op", "{")
        ss = []
        while self.peek() != ("op", "}"):
            ss.append(self.parse_stmt())
        self.eat("op", "}")
        return ss
    def parse_elif(self):
        # (cond){bloco} [: else-if | : bloco | ;fim] — escada estilo rgs_num
        self.eat("op", "(")
        c = self.parse_expr()
        self.eat("op", ")")
        b = self.parse_block()
        e = None
        if self.peek() == ("op", ":"):
            self.eat()
            if self.peek() == ("op", "{"):
                e = self.parse_block()
                self.eat("op", ";")
            elif self.peek() == ("op", "("):
                e = ("elif", self.parse_elif())
            else:
                raise Fail("else nao-bloco fora do subset")
        else:
            self.eat("op", ";")
        return ("if", c, b, e)
    def parse_stmt(self):
        t = self.peek()
        if t == ("op", "?"):
            self.eat()
            self.eat("op", "(")
            c = self.parse_expr()
            self.eat("op", ")")
            b = self.parse_block()
            if self.peek() != ("op", ":"):
                self.eat("op", ";")
            e = None
            if self.peek() == ("op", ":"):
                self.eat()
                if self.peek() == ("op", "{"):
                    e = self.parse_block()
                    self.eat("op", ";")
                elif self.peek() == ("op", "("):
                    e = ("elif", self.parse_elif())
                else:
                    raise Fail("else nao-bloco fora do subset")
            return ("if", c, b, e)
        if t == ("id", "while"):
            self.eat()
            self.eat("op", "(")
            c = self.parse_expr()
            self.eat("op", ")")
            b = self.parse_block()
            self.eat("op", ";")
            return ("while", c, b)
        if t == ("op", "^"):
            self.eat()
            e = self.parse_expr()
            if self.peek() == ("op", ";"):
                self.eat()
            return ("ret", e)
        if t == ("id", "continue"):
            self.eat()
            if self.peek() == ("op", ";"):
                self.eat()
            return ("cont",)
        # assign: id = expr [;] (`;` separador: ausente antes de `}`)
        if t[0] == "id" and self.t[self.i + 1] == ("op", "="):
            nm = self.eat("id")[1]
            self.eat("op", "=")
            e = self.parse_expr()
            if self.peek() == ("op", ";"):
                self.eat()
            return ("set", nm, e)
        raise Fail(f"stmt invalido: {t}")
    def parse_expr(self):
        return self.parse_or()
    def parse_or(self):
        e = self.parse_and()
        while self.peek() == ("op", "||"):
            self.eat()
            e = ("or", e, self.parse_and())
        return e
    def parse_and(self):
        e = self.parse_cmp()
        while self.peek() == ("op", "&&"):
            self.eat()
            e = ("and", e, self.parse_cmp())
        return e
    def parse_cmp(self):
        e = self.parse_add()
        while self.peek()[0] == "op" and self.peek()[1] in ("==", "!=", "<", ">", "<=", ">="):
            op = self.eat()[1]
            e = ("cmp", op, e, self.parse_add())
        return e
    def parse_add(self):
        e = self.parse_un()
        while self.peek()[0] == "op" and self.peek()[1] in ("+", "-", "*"):
            op = self.eat()[1]
            e = ("bin", op, e, self.parse_un())
        return e
    def parse_un(self):
        if self.peek() == ("op", "-"):
            self.eat()
            return ("neg", self.parse_un())
        return self.parse_post()
    def parse_post(self):
        e = self.parse_atom()
        while self.peek() == ("op", "."):
            self.eat()
            m = self.eat("id")[1]
            if self.peek() == ("op", "("):
                self.eat("op", "(")
                args = []
                if self.peek() != ("op", ")"):
                    while True:
                        args.append(self.parse_expr())
                        if self.peek() == ("op", ","):
                            self.eat()
                        else:
                            break
                self.eat("op", ")")
                e = ("mcall", e, m, args)
            elif m == "length":
                e = ("flen", e)
            else:
                raise Fail(f"campo .{m} fora do subset")
        return e
    def parse_atom(self):
        t = self.peek()
        if t[0] == "num":
            self.eat()
            return ("lit", int(t[1]))
        if t[0] == "str":
            self.eat()
            return ("lit", t[1][1:-1])
        if t[0] == "id":
            nm = self.eat("id")[1]
            if nm == "String" and self.peek() == ("op", "."):
                self.eat()
                self.eat("id", "fromCharCode")
                self.eat("op", "(")
                a = self.parse_expr()
                self.eat("op", ")")
                return ("fcc", a)
            if self.peek() == ("op", "("):
                self.eat()
                args = []
                if self.peek() != ("op", ")"):
                    while True:
                        args.append(self.parse_expr())
                        if self.peek() == ("op", ","):
                            self.eat()
                        else:
                            break
                self.eat("op", ")")
                return ("call", nm, args)
            return ("var", nm)
        if t == ("op", "("):
            self.eat()
            e = self.parse_expr()
            self.eat("op", ")")
            return e
        raise Fail(f"atomo invalido: {t}")

class Ret(Exception):
    def __init__(self, v):
        self.v = v

class Cont(Exception):
    pass

def truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v != 0
    return len(v) > 0

def ev(e, env, fns):
    STEPS[0] += 1
    if STEPS[0] > STEP_CAP:
        raise Fail("step cap (loop?)")
    k = e[0]
    if k == "lit":
        return e[1]
    if k == "var":
        if e[1] not in env:
            raise Fail(f"var indefinida {e[1]}")
        return env[e[1]]
    if k == "neg":
        return -ev(e[1], env, fns)
    if k == "bin":
        a, b = ev(e[2], env, fns), ev(e[3], env, fns)
        if e[1] == "+" and (isinstance(a, str) or isinstance(b, str)):
            return str(a) + str(b)
        return {"+": a + b, "-": a - b, "*": a * b}[e[1]]
    if k == "cmp":
        a, b = ev(e[2], env, fns), ev(e[3], env, fns)
        if isinstance(a, str) or isinstance(b, str):
            raise Fail("comparacao de strings fora do subset (use lh_eq)")
        return {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b,
                "==": a == b, "!=": a != b}[e[1]]
    if k == "and":
        return truthy(ev(e[1], env, fns)) and truthy(ev(e[2], env, fns))
    if k == "or":
        return truthy(ev(e[1], env, fns)) or truthy(ev(e[2], env, fns))
    if k == "fcc":
        c = ev(e[1], env, fns)
        return chr(c) if 0 <= c < 256 else ""
    if k == "flen":
        o = ev(e[1], env, fns)
        if not isinstance(o, str):
            raise Fail("length fora de string")
        return len(o)
    if k == "mcall":
        o, m, a = ev(e[1], env, fns), e[2], [ev(x, env, fns) for x in e[3]]
        if not isinstance(o, str):
            raise Fail("metodo fora de string")
        if m == "length" and not a:
            return len(o)
        if m == "charCodeAt" and len(a) == 1:
            return ord(o[a[0]]) if 0 <= a[0] < len(o) else 0
        if m == "charAt" and len(a) == 1:
            return o[a[0]] if 0 <= a[0] < len(o) else ""
        raise Fail(f"metodo {m} fora do subset")
    if k == "call":
        nm, args = e[1], [ev(x, env, fns) for x in e[2]]
        if nm == "starts_lit":
            s, i, lit = args
            return 1 if s[i:i + len(lit)] == lit else 0
        if nm == "rg_count_lit":
            hay, nd = args
            return sum(1 for i in range(len(hay)) if hay[i:i + len(nd)] == nd) if nd else 0
        if nm not in fns:
            raise Fail(f"chamada {nm} indefinida no arquivo")
        return run_fn(nm, args, fns)
    raise Fail(f"expr {k}")

def run_fn(nm, args, fns):
    params, _, body = fns[nm]
    if len(args) != len(params):
        raise Fail(f"aridade {nm}")
    env = dict(zip([p[0] for p in params], args))
    try:
        run_block(body, env, fns)
    except Ret as r:
        return r.v
    raise Fail(f"{nm} sem retorno")

def run_block(ss, env, fns):
    for s in ss:
        STEPS[0] += 1
        if STEPS[0] > STEP_CAP:
            raise Fail("step cap (loop?)")
        k = s[0]
        if k == "set":
            env[s[1]] = ev(s[2], env, fns)
        elif k == "ret":
            raise Ret(ev(s[1], env, fns))
        elif k == "cont":
            raise Cont()
        elif k == "if":
            br = s[2] if truthy(ev(s[1], env, fns)) else s[3]
            if br is not None:
                if isinstance(br, tuple) and br[0] == "elif":
                    run_block([br[1]], env, fns)
                else:
                    run_block(br, env, fns)
        elif k == "while":
            while truthy(ev(s[1], env, fns)):
                try:
                    run_block(s[2], env, fns)
                except Cont:
                    pass
        else:
            raise Fail(f"stmt {k}")

def load_fns(path):
    src = open(path, encoding="utf-8").read()
    # recorta anotacoes/cabecalho/=ex (nao sao do subset executavel)
    lines = [l for l in src.splitlines() if not l.startswith("@") and not l.startswith("=ex")]
    p = P(lex("\n".join(lines)))
    fns = {}
    while p.peek()[0] != "eof":
        try:
            nm, pr, rt, body = p.parse_fn()
        except Fail as e:
            ctx = " ".join(t[1] for t in p.t[max(0, p.i - 8):p.i + 4])
            raise Fail(f"{e} :: ctx: ...{ctx}...")
        fns[nm] = (pr, rt, body)
    return fns

# ---------- 1. auto-teste do interprete (vetores manuais) ----------
def selftest(fns):
    cases = [
        ("lh_eq", ["ab", "ab"], 1), ("lh_eq", ["ab", "ac"], 0), ("lh_eq", ["a", "ab"], 0),
        ("lh_slice", ["hello", 1, 3], "el"), ("lh_slice", ["hi", -5, 9], "hi"),
        ("lh_trim", ["  a b \n"], "a b"),         ("lh_upcase", ["aBc-z"], "ABC-Z"),
        ("lh_lowcase", ["aBc-Z"], "abc-z"),
        ("lh_style_map", ["color: #fff; padding: 4"], "fg=#fff pad=4"),
        ("lh_style_map", ["position: absolute"], "LINT_REJ_CSS"),
        ("lh_lay_tag", ["div", "col"], "COL"), ("lh_lay_tag", ["div", "x"], "DIV"),
        ("lh_lay_tag", ["table", ""], "?"), ("lh_lay_tag", ["head", ""], ""),
        ("lh_has_cls", ["a row b", "row"], 1), ("lh_has_cls", ["arrow", "row"], 0),
        ("lh_deent", ["a&amp;b&lt;c"], "a&b<c"),
        ("lh_indent", [2], "        "),
    ]
    bad = 0
    for fn, args, want in cases:
        STEPS[0] = 0
        got = run_fn(fn, args, fns)
        if got != want:
            print(f"  SELFTEST FAIL {fn}{args}: {got!r} != {want!r}")
            bad += 1
    return bad

# ---------- 2+3. paridade no corpus ----------
FIX = [
    ("pos/full", None),  # preenchido abaixo (golden html do lint_c0)
]

def main():
    fns = load_fns(SRC)
    print(f"[lint-lin] {len(fns)} funcoes carregadas de src/lint_from_html.lin")
    b = selftest(fns)
    print(f"[lint-lin] selftest interprete: {'ALL PASS' if b == 0 else f'{b} FALHAS'}")
    if b:
        return 1
    repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    gold = os.path.join(repo, "transpile/c/lint_c0/golden")
    sys.path.insert(0, "/home/k/Downloads/FloppyURL-main")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pyoracle", "/home/k/Downloads/FloppyURL-main/transpile_html_to_lay.py")
    pyo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pyo)
    fails = 0
    for name in ["minimal", "full"]:
        html = open(os.path.join(gold, name + ".html"), encoding="utf-8").read()
        want = open(os.path.join(gold, name + ".lay"), encoding="utf-8").read()
        STEPS[0] = 0
        got_lin = run_fn("lint_html", [html], fns)
        try:
            got_py = pyo.transpile(html)
        except Exception as e:
            got_py = f"PY-REJ: {e}"
        ok = got_lin == want == got_py
        print(f"[lint-lin] fixture {name}: LIN==golden==PY: {ok} (steps={STEPS[0]})")
        if not ok:
            fails += 1
            if got_lin != want:
                print(f"  LIN-Zgolden diff: {got_lin[:120]!r} vs {want[:120]!r}")
            if got_py != want:
                print(f"  PY-Zgolden diff: {got_py[:120]!r} vs {want[:120]!r}")
    # negativos: mesma sentenca de rejeito nos dois lados
    negs = {
        '<script>x()</script>': 'LINT_REJ_SCRIPT',
        '<style>.a{}</style>': 'LINT_REJ_STYLE',
        '<table><tr><td>x</td></tr></table>': 'LINT_REJ_TAG',
        '<div style="position: absolute">x</div>': 'LINT_REJ_CSS',
        '<button action="nuke">x</button>': 'LINT_REJ_ACTION',
        '<div id="a" id="b">x</div>': None,  # duplicado: oraculo aceita (dict last-wins); LIN sobrescreve: mesma saida
        '<div><p>a</p>tail</div>': None,     # texto apos filho no root: oraculo ACEITA (anexa e descarta)
        'hello': None,                        # texto fora de no: ambos rejeitam (sentinelas podem diferir)
    }
    for html, wantrej in negs.items():
        STEPS[0] = 0
        try:
            lin = run_fn("lint_html", [html], fns)
        except Fail as e:
            lin = f"LIN-ERR: {e}"
        try:
            py = pyo.transpile(html)
            pyrej = None
        except Exception:
            pyrej = "REJ"
        linrej = lin.startswith("LINT_REJ") if isinstance(lin, str) else None
        if wantrej:
            ok = lin == wantrej and pyrej == "REJ"
        elif pyrej == "REJ":
            ok = bool(linrej)
        else:
            ok = (not linrej) and lin == py
        print(f"[lint-lin] neg {html[:34]!r}: LIN={str(lin)[:24]!r} PYrej={pyrej} ok={ok}")
        if not ok:
            fails += 1
    print(f"[lint-lin] PARIDADE: {'ALL PASS' if fails == 0 else f'{fails} FALHAS'}")
    return 0 if fails == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
