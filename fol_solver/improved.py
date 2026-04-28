"""
improved.py - Improved Algorithm 2 with optimizations:
1. Memoization (loop detection via sequent key)
2. Apply non-branching rules first (deterministic priority)
3. Smart term selection (constants from goal first)
"""
import time
from parser import (
    Formula, Atom, Eq, Not, And, Or, Imp, Forall, Exists,
    Term, Var, Const, Func,
    Sequent, subst, collect_constants
)
from baseline import Result


class ImprovedSolver:
    def __init__(self, max_depth=80, timeout_ms=5000, max_inst=3):
        self.max_depth = max_depth
        self.timeout_ms = timeout_ms
        self.max_inst = max_inst
        self.fresh_id = 0
        self.start = 0
        self.nodes = 0
        self.memo = {}

    def fresh_var(self):
        self.fresh_id += 1
        return f"_v{self.fresh_id}"

    def solve(self, sequent: Sequent) -> Result:
        r = Result()
        self.fresh_id = 0
        self.nodes = 0
        self.memo = {}
        self.start = time.time()
        try:
            r.success = self._prove(sequent, 0, set())
        except TimeoutError:
            r.timeout = True
            r.success = False
        r.nodes = self.nodes
        r.time_ms = (time.time() - self.start) * 1000
        return r

    def _check_timeout(self):
        if (time.time() - self.start) * 1000 > self.timeout_ms:
            raise TimeoutError()

    def _prove(self, seq: Sequent, depth: int, visiting: set) -> bool:
        self.nodes += 1
        self._check_timeout()
        if depth > self.max_depth:
            return False

        key = seq.key()

        # Memoization
        if key in self.memo:
            return self.memo[key]
        # Loop detection
        if key in visiting:
            return False

        # Axiom check (cheap, do first)
        for l in seq.left:
            for r in seq.right:
                if l == r:
                    self.memo[key] = True
                    return True
        for r in seq.right:
            if isinstance(r, Eq) and r.left == r.right:
                self.memo[key] = True
                return True

        visiting = visiting | {key}

        # IMPROVEMENT: try non-branching rules first
        result = self._try_nonbranching(seq, depth, visiting)
        if result is not None:
            self.memo[key] = result
            return result

        # Then branching rules
        result = self._try_branching(seq, depth, visiting)
        if result is not None:
            self.memo[key] = result
            return result

        # Then quantifier rules
        result = self._try_quantifiers(seq, depth, visiting)
        if result is not None:
            self.memo[key] = result
            return result

        self.memo[key] = False
        return False

    # ---------- Non-branching rules (always safe to apply) ----------
    def _try_nonbranching(self, seq: Sequent, depth: int, visiting):
        for i, f in enumerate(seq.left):
            if isinstance(f, Not):
                return self._prove(Sequent(
                    seq.left[:i] + seq.left[i+1:],
                    seq.right + [f.f]), depth+1, visiting)
            if isinstance(f, And):
                return self._prove(Sequent(
                    seq.left[:i] + [f.left, f.right] + seq.left[i+1:],
                    seq.right), depth+1, visiting)
        for i, f in enumerate(seq.right):
            if isinstance(f, Not):
                return self._prove(Sequent(
                    seq.left + [f.f],
                    seq.right[:i] + seq.right[i+1:]), depth+1, visiting)
            if isinstance(f, Or):
                return self._prove(Sequent(
                    seq.left,
                    seq.right[:i] + [f.left, f.right] + seq.right[i+1:]),
                    depth+1, visiting)
            if isinstance(f, Imp):
                return self._prove(Sequent(
                    seq.left + [f.left],
                    seq.right[:i] + [f.right] + seq.right[i+1:]),
                    depth+1, visiting)
        return None  # nothing to do

    # ---------- Branching rules ----------
    def _try_branching(self, seq: Sequent, depth: int, visiting):
        for i, f in enumerate(seq.left):
            if isinstance(f, Or):
                left1 = seq.left[:i] + [f.left] + seq.left[i+1:]
                left2 = seq.left[:i] + [f.right] + seq.left[i+1:]
                return (self._prove(Sequent(left1, seq.right), depth+1, visiting)
                        and self._prove(Sequent(left2, seq.right), depth+1, visiting))
            if isinstance(f, Imp):
                rest = seq.left[:i] + seq.left[i+1:]
                if not self._prove(Sequent(rest, seq.right + [f.left]), depth+1, visiting):
                    return False
                return self._prove(Sequent(rest + [f.right], seq.right), depth+1, visiting)
        for i, f in enumerate(seq.right):
            if isinstance(f, And):
                r1 = seq.right[:i] + [f.left] + seq.right[i+1:]
                r2 = seq.right[:i] + [f.right] + seq.right[i+1:]
                return (self._prove(Sequent(seq.left, r1), depth+1, visiting)
                        and self._prove(Sequent(seq.left, r2), depth+1, visiting))
        return None

    # ---------- Quantifier rules (most expensive last) ----------
    def _try_quantifiers(self, seq: Sequent, depth: int, visiting):
        # Existential left -> fresh constant (deterministic, easy)
        for i, f in enumerate(seq.left):
            if isinstance(f, Exists):
                c = Const(self.fresh_var())
                new_f = subst(f.f, f.var, c)
                return self._prove(Sequent(
                    seq.left[:i] + [new_f] + seq.left[i+1:], seq.right),
                    depth+1, visiting)
        # Universal right -> fresh constant
        for i, f in enumerate(seq.right):
            if isinstance(f, Forall):
                c = Const(self.fresh_var())
                new_f = subst(f.f, f.var, c)
                return self._prove(Sequent(seq.left,
                    seq.right[:i] + [new_f] + seq.right[i+1:]),
                    depth+1, visiting)
        # Universal left -> instantiate (branching: try each ground term)
        for i, f in enumerate(seq.left):
            if isinstance(f, Forall):
                terms = self._smart_terms(seq)
                for t in terms[:self.max_inst]:
                    new_f = subst(f.f, f.var, t)
                    if new_f in seq.left:
                        continue  # already there
                    if self._prove(Sequent(list(seq.left) + [new_f], seq.right),
                                   depth+1, visiting):
                        return True
                return False
        # Existential right -> instantiate
        for i, f in enumerate(seq.right):
            if isinstance(f, Exists):
                terms = self._smart_terms(seq)
                for t in terms[:self.max_inst]:
                    new_f = subst(f.f, f.var, t)
                    if new_f in seq.right:
                        continue
                    if self._prove(Sequent(seq.left, list(seq.right) + [new_f]),
                                   depth+1, visiting):
                        return True
                return False
        return None

    def _smart_terms(self, seq: Sequent):
        """Prioritize constants from goal (right side) first."""
        right_consts = set()
        for f in seq.right: collect_constants(f, right_consts)
        left_consts = set()
        for f in seq.left: collect_constants(f, left_consts)
        ordered = list(right_consts) + [c for c in left_consts if c not in right_consts]
        if not ordered:
            ordered = [Const('a')]
        return ordered
