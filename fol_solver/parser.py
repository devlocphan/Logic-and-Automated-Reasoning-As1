"""
parser.py - FOL AST and parser
Combines formula representation and parser in one file.
"""
from dataclasses import dataclass, field
from typing import List, Tuple
import re


# ============================================================
# AST: Terms and Formulas
# ============================================================

class Term:
    pass

@dataclass(frozen=True)
class Var(Term):
    name: str
    def __str__(self): return self.name

@dataclass(frozen=True)
class Const(Term):
    name: str
    def __str__(self): return self.name

@dataclass(frozen=True)
class Func(Term):
    name: str
    args: Tuple[Term, ...]
    def __str__(self): return f"{self.name}({','.join(str(a) for a in self.args)})"


class Formula:
    pass

@dataclass(frozen=True)
class Atom(Formula):
    pred: str
    args: Tuple[Term, ...]
    def __str__(self):
        if not self.args: return self.pred
        return f"{self.pred}({','.join(str(a) for a in self.args)})"

@dataclass(frozen=True)
class Eq(Formula):  # equality
    left: Term
    right: Term
    def __str__(self): return f"{self.left}={self.right}"

@dataclass(frozen=True)
class Not(Formula):
    f: Formula
    def __str__(self): return f"~{self.f}"

@dataclass(frozen=True)
class And(Formula):
    left: Formula
    right: Formula
    def __str__(self): return f"({self.left} & {self.right})"

@dataclass(frozen=True)
class Or(Formula):
    left: Formula
    right: Formula
    def __str__(self): return f"({self.left} | {self.right})"

@dataclass(frozen=True)
class Imp(Formula):
    left: Formula
    right: Formula
    def __str__(self): return f"({self.left} => {self.right})"

@dataclass(frozen=True)
class Forall(Formula):
    var: str
    f: Formula
    def __str__(self): return f"(![{self.var}]:{self.f})"

@dataclass(frozen=True)
class Exists(Formula):
    var: str
    f: Formula
    def __str__(self): return f"(?[{self.var}]:{self.f})"


@dataclass
class Sequent:
    """Antecedents |- Consequents (multi-conclusion)."""
    left: List[Formula] = field(default_factory=list)
    right: List[Formula] = field(default_factory=list)

    def __str__(self):
        l = ", ".join(str(f) for f in self.left)
        r = ", ".join(str(f) for f in self.right)
        return f"{l} |- {r}"

    def key(self):
        # canonical key for memoization/loop detection
        l = sorted(str(f) for f in self.left)
        r = sorted(str(f) for f in self.right)
        return ("|".join(l), "|".join(r))


# ============================================================
# Substitution and helpers
# ============================================================

def subst_term(t: Term, var: str, repl: Term) -> Term:
    if isinstance(t, Var):
        return repl if t.name == var else t
    if isinstance(t, Const):
        return t
    if isinstance(t, Func):
        return Func(t.name, tuple(subst_term(a, var, repl) for a in t.args))
    return t

def subst(f: Formula, var: str, repl: Term) -> Formula:
    if isinstance(f, Atom):
        return Atom(f.pred, tuple(subst_term(a, var, repl) for a in f.args))
    if isinstance(f, Eq):
        return Eq(subst_term(f.left, var, repl), subst_term(f.right, var, repl))
    if isinstance(f, Not):
        return Not(subst(f.f, var, repl))
    if isinstance(f, And):
        return And(subst(f.left, var, repl), subst(f.right, var, repl))
    if isinstance(f, Or):
        return Or(subst(f.left, var, repl), subst(f.right, var, repl))
    if isinstance(f, Imp):
        return Imp(subst(f.left, var, repl), subst(f.right, var, repl))
    if isinstance(f, Forall):
        if f.var == var: return f
        return Forall(f.var, subst(f.f, var, repl))
    if isinstance(f, Exists):
        if f.var == var: return f
        return Exists(f.var, subst(f.f, var, repl))
    return f

def collect_constants(f: Formula, out: set):
    if isinstance(f, Atom):
        for a in f.args: _collect_term_consts(a, out)
    elif isinstance(f, Eq):
        _collect_term_consts(f.left, out); _collect_term_consts(f.right, out)
    elif isinstance(f, Not):
        collect_constants(f.f, out)
    elif isinstance(f, (And, Or, Imp)):
        collect_constants(f.left, out); collect_constants(f.right, out)
    elif isinstance(f, (Forall, Exists)):
        collect_constants(f.f, out)

def _collect_term_consts(t: Term, out: set):
    if isinstance(t, Const):
        out.add(t)
    elif isinstance(t, Func):
        for a in t.args: _collect_term_consts(a, out)


# ============================================================
# Tokenizer + Parser (TPTP fof syntax)
# ============================================================

class Parser:
    """Parses TPTP FOF formulas and full TPTP files."""

    def __init__(self):
        self.tokens = []
        self.pos = 0
        self._fresh = 0

    # ---------- Tokenizer ----------
    def _tokenize(self, text: str):
        # Strip comments
        text = re.sub(r'%[^\n]*', '', text)
        # Normalize unicode operators to ASCII
        text = (text.replace('⊢', '|-').replace('¬', '~')
                    .replace('∀', '!').replace('∃', '?')
                    .replace('∧', '&').replace('∨', '|')
                    .replace('→', '=>').replace('≠', '!='))
        token_spec = [
            ('SKIP',    r'\s+'),
            ('OP',      r'<=>|<~>|=>|<=|!=|\|-|\?\*|!>|@\+|@-|::=|:='),
            ('PUNCT',   r'[(),.\[\]:]'),
            ('SINGLE',  r'[!?~&|=]'),
            ('DOLLAR',  r'\$[a-zA-Z_]\w*'),
            ('WORD',    r'[A-Za-z_][A-Za-z0-9_]*'),
            ('NUM',     r'\d+'),
        ]
        regex = '|'.join(f'(?P<{n}>{p})' for n, p in token_spec)
        out = []
        for m in re.finditer(regex, text):
            kind = m.lastgroup
            val = m.group()
            if kind == 'SKIP': continue
            out.append((kind, val))
        return out

    def _peek(self, offset=0):
        i = self.pos + offset
        return self.tokens[i] if i < len(self.tokens) else (None, None)

    def _eat(self, val=None, kind=None):
        k, v = self._peek()
        if val is not None and v != val:
            raise SyntaxError(f"Expected '{val}', got '{v}'")
        if kind is not None and k != kind:
            raise SyntaxError(f"Expected {kind}, got {k}({v})")
        self.pos += 1
        return v

    def _accept(self, val):
        if self._peek()[1] == val:
            self.pos += 1
            return True
        return False

    # ---------- Parse formulas ----------
    def parse_formula(self, text: str) -> Formula:
        self.tokens = self._tokenize(text)
        self.pos = 0
        f = self._parse_imp()
        return f

    def _parse_imp(self):
        # right-associative implication, equivalence
        left = self._parse_or()
        while True:
            op = self._peek()[1]
            if op == '=>':
                self.pos += 1
                right = self._parse_imp()
                left = Imp(left, right)
            elif op == '<=>':
                self.pos += 1
                right = self._parse_imp()
                # encode A <=> B as (A=>B) & (B=>A)
                left = And(Imp(left, right), Imp(right, left))
            elif op == '<=':
                self.pos += 1
                right = self._parse_imp()
                left = Imp(right, left)
            else:
                break
        return left

    def _parse_or(self):
        left = self._parse_and()
        while self._peek()[1] == '|':
            self.pos += 1
            right = self._parse_and()
            left = Or(left, right)
        return left

    def _parse_and(self):
        left = self._parse_unary()
        while self._peek()[1] == '&':
            self.pos += 1
            right = self._parse_unary()
            left = And(left, right)
        return left

    def _parse_unary(self):
        k, v = self._peek()
        if v == '~':
            self.pos += 1
            return Not(self._parse_unary())
        if v == '!' or v == '?':
            return self._parse_quantifier()
        if v == '(':
            self.pos += 1
            f = self._parse_imp()
            self._eat(')')
            return f
        return self._parse_atom()

    def _parse_quantifier(self):
        q = self._eat()  # ! or ?
        self._eat('[')
        vars_ = [self._eat(kind='WORD')]
        while self._accept(','):
            vars_.append(self._eat(kind='WORD'))
        self._eat(']')
        self._eat(':')
        body = self._parse_unary()
        # Build nested quantifiers
        for v in reversed(vars_):
            body = Forall(v, body) if q == '!' else Exists(v, body)
        return body

    def _parse_atom(self):
        # term [= term | != term] OR predicate(args) OR $true/$false
        t1 = self._parse_term()
        op = self._peek()[1]
        if op == '=':
            self.pos += 1
            t2 = self._parse_term()
            return Eq(t1, t2)
        if op == '!=':
            self.pos += 1
            t2 = self._parse_term()
            return Not(Eq(t1, t2))
        # If t1 was a Func, treat it as Atom (predicate application)
        if isinstance(t1, Func):
            return Atom(t1.name, t1.args)
        if isinstance(t1, Const):
            # 0-ary predicate or special $true/$false
            if t1.name == '$true':
                # encode as Eq of fresh constant to itself
                return Eq(Const('_t'), Const('_t'))
            if t1.name == '$false':
                return Not(Eq(Const('_t'), Const('_t')))
            return Atom(t1.name, ())
        if isinstance(t1, Var):
            return Atom(t1.name, ())
        raise SyntaxError(f"Cannot parse atom from {t1}")

    def _parse_term(self) -> Term:
        k, v = self._peek()
        if k != 'WORD' and k != 'DOLLAR':
            raise SyntaxError(f"Expected term, got {v}")
        self.pos += 1
        # function application?
        if self._peek()[1] == '(':
            self.pos += 1
            args = [self._parse_term()]
            while self._accept(','):
                args.append(self._parse_term())
            self._eat(')')
            return Func(v, tuple(args))
        # Variable (uppercase first letter) vs constant
        if v[0].isupper():
            return Var(v)
        return Const(v)

    # ---------- Parse TPTP file ----------
    def parse_tptp_file(self, path: str) -> Tuple[List[Formula], Formula]:
        """Returns (axioms, conjecture)."""
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Remove comments
        content = re.sub(r'%[^\n]*', '', content)
        # Find each fof(...)  or cnf(...) block, ending in ).
        axioms = []
        conjecture = None
        # Use balanced-paren matching by scanning
        i = 0
        while i < len(content):
            m = re.match(r'\s*(fof|cnf|tff)\s*\(', content[i:])
            if not m:
                i += 1
                continue
            start = i + m.end()  # position after opening (
            depth = 1
            j = start
            while j < len(content) and depth > 0:
                if content[j] == '(': depth += 1
                elif content[j] == ')': depth -= 1
                j += 1
            inner = content[start:j-1]
            # split top-level commas
            parts = self._split_top_commas(inner)
            if len(parts) >= 3:
                name = parts[0].strip()
                role = parts[1].strip()
                formula_text = ','.join(parts[2:]).strip()
                # remove outer parens around formula if present
                formula_text = formula_text.strip()
                if formula_text.startswith('(') and formula_text.endswith(')'):
                    # check balanced
                    pass
                try:
                    formula = self.parse_formula(formula_text)
                except Exception as e:
                    print(f"  [skip {name}: parse error: {e}]")
                    i = j
                    # also skip trailing dot
                    while i < len(content) and content[i] in '. \n\t': i += 1
                    continue
                if role in ('axiom', 'hypothesis', 'definition', 'assumption', 'lemma', 'theorem'):
                    axioms.append(formula)
                elif role == 'conjecture':
                    conjecture = formula
                elif role == 'negated_conjecture':
                    conjecture = Not(formula)  # treat as goal negated
            i = j
        return axioms, conjecture

    def _split_top_commas(self, s: str):
        out = []
        depth = 0
        cur = []
        for ch in s:
            if ch == '(' or ch == '[': depth += 1
            elif ch == ')' or ch == ']': depth -= 1
            if ch == ',' and depth == 0:
                out.append(''.join(cur))
                cur = []
            else:
                cur.append(ch)
        if cur: out.append(''.join(cur))
        return out
