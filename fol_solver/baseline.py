"""
baseline.py - Algorithm 2 (naive backward proof search) from textbook page 67.
Uses LK' sequent calculus rules.
"""
import time
from parser import (
    Formula, Atom, Eq, Not, And, Or, Imp, Forall, Exists,
    Term, Var, Const, Func,
    Sequent, subst, collect_constants
)


class Result:
    def __init__(self):
        self.success = False
        self.nodes = 0
        self.time_ms = 0.0
        self.timeout = False


class BaselineSolver:
    """Naive backward proof search."""

    def __init__(self, max_depth=50, timeout_ms=5000, max_inst=2):
        self.max_depth = max_depth
        self.timeout_ms = timeout_ms
        self.max_inst = max_inst   # instances per universal/existential
        self.fresh_id = 0
        self.start = 0
        self.nodes = 0

    def fresh_var(self):
        self.fresh_id += 1
        return f"_v{self.fresh_id}"

    def solve(self, sequent: Sequent) -> Result:
        r = Result()
        self.fresh_id = 0
        self.nodes = 0
        self.start = time.time()
        try:
            r.success = self._prove(sequent, 0)
        except TimeoutError:
            r.timeout = True
            r.success = False
        r.nodes = self.nodes
        r.time_ms = (time.time() - self.start) * 1000
        return r

    def _check_timeout(self):
        if (time.time() - self.start) * 1000 > self.timeout_ms:
            raise TimeoutError()

    def _prove(self, seq: Sequent, depth: int) -> bool:
        self.nodes += 1
        self._check_timeout()
        if depth > self.max_depth:
            return False

        # Axiom rule: same formula on both sides
        for l in seq.left:
            for r in seq.right:
                if l == r:
                    return True
        # Reflexivity for equality
        for r in seq.right:
            if isinstance(r, Eq) and r.left == r.right:
                return True

        # Try to apply some rule to a non-atomic formula
        # LEFT side rules
        for i, f in enumerate(seq.left):
            if isinstance(f, Not):
                new_left = seq.left[:i] + seq.left[i+1:]
                new_right = seq.right + [f.f]
                return self._prove(Sequent(new_left, new_right), depth+1)
            if isinstance(f, And):
                new_left = seq.left[:i] + [f.left, f.right] + seq.left[i+1:]
                return self._prove(Sequent(new_left, seq.right), depth+1)
            if isinstance(f, Or):
                # branching: prove with f.left and with f.right
                left1 = seq.left[:i] + [f.left] + seq.left[i+1:]
                left2 = seq.left[:i] + [f.right] + seq.left[i+1:]
                return (self._prove(Sequent(left1, seq.right), depth+1)
                        and self._prove(Sequent(left2, seq.right), depth+1))
            if isinstance(f, Imp):
                # A => B left:  prove A on right, OR have B on left
                left_rest = seq.left[:i] + seq.left[i+1:]
                # branch 1: prove |- A
                b1 = self._prove(Sequent(left_rest, seq.right + [f.left]), depth+1)
                if not b1: return False
                # branch 2: B on left
                b2 = self._prove(Sequent(left_rest + [f.right], seq.right), depth+1)
                return b2
            if isinstance(f, Exists):
                # introduce fresh constant
                c = Const(self.fresh_var())
                new_f = subst(f.f, f.var, c)
                new_left = seq.left[:i] + [new_f] + seq.left[i+1:]
                return self._prove(Sequent(new_left, seq.right), depth+1)
            if isinstance(f, Forall):
                # try instantiations with each ground constant in sequent
                terms = self._ground_terms(seq)
                for t in terms[:self.max_inst]:
                    new_f = subst(f.f, f.var, t)
                    # keep original (can be reused)
                    new_left = list(seq.left) + [new_f]
                    if self._prove(Sequent(new_left, seq.right), depth+1):
                        return True
                return False

        # RIGHT side rules
        for i, f in enumerate(seq.right):
            if isinstance(f, Not):
                new_right = seq.right[:i] + seq.right[i+1:]
                new_left = seq.left + [f.f]
                return self._prove(Sequent(new_left, new_right), depth+1)
            if isinstance(f, And):
                # branching: both sides
                r1 = seq.right[:i] + [f.left] + seq.right[i+1:]
                r2 = seq.right[:i] + [f.right] + seq.right[i+1:]
                return (self._prove(Sequent(seq.left, r1), depth+1)
                        and self._prove(Sequent(seq.left, r2), depth+1))
            if isinstance(f, Or):
                new_right = seq.right[:i] + [f.left, f.right] + seq.right[i+1:]
                return self._prove(Sequent(seq.left, new_right), depth+1)
            if isinstance(f, Imp):
                new_right = seq.right[:i] + [f.right] + seq.right[i+1:]
                new_left = seq.left + [f.left]
                return self._prove(Sequent(new_left, new_right), depth+1)
            if isinstance(f, Forall):
                c = Const(self.fresh_var())
                new_f = subst(f.f, f.var, c)
                new_right = seq.right[:i] + [new_f] + seq.right[i+1:]
                return self._prove(Sequent(seq.left, new_right), depth+1)
            if isinstance(f, Exists):
                terms = self._ground_terms(seq)
                for t in terms[:self.max_inst]:
                    new_f = subst(f.f, f.var, t)
                    new_right = list(seq.right) + [new_f]
                    if self._prove(Sequent(seq.left, new_right), depth+1):
                        return True
                return False

        # All atoms, no axiom matched
        return False

    def _ground_terms(self, seq: Sequent):
        consts = set()
        for f in seq.left: collect_constants(f, consts)
        for f in seq.right: collect_constants(f, consts)
        if not consts:
            consts.add(Const('a'))
        return list(consts)
