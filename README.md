# 3806ICT Logic and Automated Reasoning — Assignment 1

**First-Order Logic Sequent Calculus Prover**
Griffith University · Trimester 1, 2026

---

## Overview

Implements backward proof search for First-Order Logic using the **LK′ sequent calculus** (Algorithm 2). Two solvers are provided and compared:

| Solver | File | Description |
|---|---|---|
| Baseline | `fol_solver/baseline.py` | Naive backward search, fixed rule order, no loop detection |
| Improved | `fol_solver/improved.py` | Memoization, non-branching rules first, smart term selection |

---

## Structure

```
fol_solver/
    parser.py     # FOL AST + TPTP fof/cnf parser
    baseline.py   # Naive solver
    improved.py   # Optimised solver
    main.py       # CLI entry point
```

---

## Requirements

- Python 3.9+  
- No external dependencies

---

## Usage

```bash
cd fol_solver

# Run built-in test suite (18 tests + TPTP PUZ001+1)
python main.py tests

# Run on a TPTP problem file
python main.py tptp ../TPTP-v9.2.1/Problems/PUZ/PUZ001+1.p

# Prove a single formula
python main.py solve "p(a) | ~p(a)"
python main.py solve "p(a), p(a)=>q(a) |- q(a)" --method improved
```

Optional flags: `--method baseline|improved|both`, `--timeout <ms>`

---

## Input Syntax

TPTP FOF subset. Key operators:

| Operator | Syntax |
|---|---|
| Negation | `~p(X)` |
| Conjunction / Disjunction | `p & q` / `p \| q` |
| Implication / Biconditional | `p => q` / `p <=> q` |
| Universal / Existential | `![X]:p(X)` / `?[X]:p(X)` |
| Equality / Inequality | `X = Y` / `X != Y` |
| Constants / Variables | lowercase `a` / uppercase `X` |

---

## Test Cases

18 built-in tests across three difficulty levels plus one TPTP benchmark:

- **Easy (E1–E7):** identity, modus ponens, ∧-elim, ∨-intro, excluded middle, contradiction, non-provable
- **Medium (M1–M6):** chaining, ∀-instantiation, De Morgan, contrapositive
- **Hard (H1–H5):** distributed quantifiers, Drinker paradox, double negation
- **TPTP PUZ001+1:** Dreadbury Mansion — *"Who killed Aunt Agatha?"* (13 axioms, theorem)

---

## References

- Pelletier, F. J. (1986). *Seventy-five Problems for Testing Automatic Theorem Provers.*
- TPTP Problem Library v9.2.1 — https://tptp.org
