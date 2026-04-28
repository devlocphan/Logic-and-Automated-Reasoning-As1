"""
main.py - CLI entry point. Includes a small built-in test set and TPTP file runner.

Usage:
    python main.py tests                       # run built-in tests (both solvers)
    python main.py tptp <path_to_file.p>       # run on a TPTP problem file
    python main.py solve "<formula>" [--method baseline|improved]
"""
import sys
import time
import argparse
from parser import Parser, Sequent, Not
from baseline import BaselineSolver
from improved import ImprovedSolver


# ============================================================
# Built-in test set (hand-written, with expected results)
# Format: (name, difficulty, antecedents_text, goal_text, expected)
# ============================================================
TESTS = [
    # EASY
    ("E1_identity",       "easy",   ["p(a)"],            "p(a)",                       True),
    ("E2_modus_ponens",   "easy",   ["p(a)", "p(a)=>q(a)"], "q(a)",                    True),
    ("E3_and_elim",       "easy",   ["p(a) & q(a)"],     "p(a)",                       True),
    ("E4_or_intro",       "easy",   ["p(a)"],            "p(a) | q(a)",                True),
    ("E5_excluded_mid",   "easy",   [],                  "p(a) | ~p(a)",               True),
    ("E6_contradiction",  "easy",   ["p(a)", "~p(a)"],   "q(a)",                       True),
    ("E7_not_provable",   "easy",   [],                  "p(a)",                       False),

    # MEDIUM
    ("M1_chain",          "medium", ["p(a)", "p(a)=>q(a)", "q(a)=>r(a)"], "r(a)",      True),
    ("M2_forall_inst",    "medium", ["![X]:p(X)"],       "p(a)",                       True),
    ("M3_forall_imp",     "medium", ["![X]:(p(X)=>q(X))", "p(a)"], "q(a)",             True),
    ("M4_exists_intro",   "medium", ["p(a)"],            "?[X]:p(X)",                  True),
    ("M5_demorgan",       "medium", ["~(p(a) | q(a))"],  "~p(a) & ~q(a)",              True),
    ("M6_contrapositive", "medium", ["p(a)=>q(a)", "~q(a)"], "~p(a)",                  True),

    # HARD
    ("H1_distrib_forall_and", "hard", ["![X]:(p(X) & q(X))"], "(![X]:p(X)) & (![X]:q(X))", True),
    ("H2_exists_or",      "hard",   ["?[X]:(p(X) | q(X))"], "(?[X]:p(X)) | (?[X]:q(X))", True),
    ("H3_drinker",        "hard",   [],                  "?[X]:(p(X) => ![Y]:p(Y))",   True),
    ("H4_swap_quant_bad", "hard",   ["![X]:?[Y]:r(X,Y)"], "?[Y]:![X]:r(X,Y)",          False),
    ("H5_double_neg",     "hard",   [],                  "p(a) => ~~p(a)",             True),
]


def build_sequent(parser: Parser, ants_text, goal_text) -> Sequent:
    left = [parser.parse_formula(t) for t in ants_text]
    right = [parser.parse_formula(goal_text)]
    return Sequent(left, right)


def run_tests(method='both', timeout_ms=3000):
    parser = Parser()
    solvers = []
    if method in ('baseline', 'both'):
        solvers.append(("Baseline", BaselineSolver(timeout_ms=timeout_ms)))
    if method in ('improved', 'both'):
        solvers.append(("Improved", ImprovedSolver(timeout_ms=timeout_ms)))

    print(f"\n{'='*78}")
    print(f"{'Test':<22}{'Diff':<8}{'Expect':<8}", end="")
    for name, _ in solvers:
        print(f"{name+' Result':<14}{name+' ms':<10}{name+' nodes':<10}", end="")
    print()
    print('='*78)

    summary = {name: {'correct': 0, 'time': 0, 'nodes': 0} for name, _ in solvers}

    for name, diff, ants, goal, expected in TESTS:
        try:
            seq = build_sequent(parser, ants, goal)
        except Exception as e:
            print(f"{name:<22}PARSE ERROR: {e}")
            continue

        print(f"{name:<22}{diff:<8}{str(expected):<8}", end="")
        for sname, solver in solvers:
            r = solver.solve(seq)
            ok = (r.success == expected)
            mark = "OK" if ok else "FAIL"
            verdict = "PROVED" if r.success else ("TIMEOUT" if r.timeout else "no")
            print(f"{verdict+'/'+mark:<14}{r.time_ms:<10.1f}{r.nodes:<10}", end="")
            if ok: summary[sname]['correct'] += 1
            summary[sname]['time'] += r.time_ms
            summary[sname]['nodes'] += r.nodes
        print()

    print('='*78)
    total = len(TESTS)
    print(f"\nSUMMARY ({total} tests):")
    for sname, _ in solvers:
        s = summary[sname]
        print(f"  {sname:<10} accuracy={s['correct']}/{total} ({100*s['correct']/total:.0f}%)  "
              f"total_time={s['time']:.1f}ms  total_nodes={s['nodes']}")
    if len(solvers) == 2:
        b, i = summary['Baseline'], summary['Improved']
        if i['time'] > 0:
            print(f"  Speedup (Baseline/Improved): {b['time']/i['time']:.2f}x")


def run_tptp(path: str, method='both', timeout_ms=10000):
    parser = Parser()
    print(f"\nParsing TPTP file: {path}")
    axioms, conjecture = parser.parse_tptp_file(path)
    print(f"  Loaded {len(axioms)} axiom(s)")
    if conjecture is None:
        print("  No conjecture found.")
        return
    print(f"  Conjecture: {conjecture}")
    seq = Sequent(list(axioms), [conjecture])

    solvers = []
    if method in ('baseline', 'both'):
        solvers.append(("Baseline", BaselineSolver(timeout_ms=timeout_ms, max_depth=100)))
    if method in ('improved', 'both'):
        solvers.append(("Improved", ImprovedSolver(timeout_ms=timeout_ms, max_depth=200)))

    for name, solver in solvers:
        print(f"\n--- {name} ---")
        r = solver.solve(seq)
        verdict = "PROVED" if r.success else ("TIMEOUT" if r.timeout else "FAILED")
        print(f"  Result : {verdict}")
        print(f"  Time   : {r.time_ms:.1f} ms")
        print(f"  Nodes  : {r.nodes}")


def run_solve(formula_text: str, method='baseline', timeout_ms=5000):
    parser = Parser()
    # Allow "ants |- goal" form
    if '|-' in formula_text:
        l, r = formula_text.split('|-', 1)
        left = [parser.parse_formula(p.strip()) for p in l.split(',') if p.strip()]
        right = [parser.parse_formula(r.strip())]
    else:
        left = []
        right = [parser.parse_formula(formula_text)]
    seq = Sequent(left, right)

    solver = BaselineSolver(timeout_ms=timeout_ms) if method == 'baseline' \
             else ImprovedSolver(timeout_ms=timeout_ms)
    print(f"Sequent: {seq}")
    r = solver.solve(seq)
    print(f"Result: {'PROVED' if r.success else ('TIMEOUT' if r.timeout else 'NOT PROVED')}")
    print(f"Time:   {r.time_ms:.2f} ms")
    print(f"Nodes:  {r.nodes}")


def main():
    ap = argparse.ArgumentParser(description="FOL Algorithm 2 prover")
    sub = ap.add_subparsers(dest='cmd')

    pt = sub.add_parser('tests', help='Run built-in test set')
    pt.add_argument('--method', choices=['baseline', 'improved', 'both'], default='both')
    pt.add_argument('--timeout', type=int, default=3000)

    pp = sub.add_parser('tptp', help='Run on a TPTP .p file')
    pp.add_argument('file')
    pp.add_argument('--method', choices=['baseline', 'improved', 'both'], default='both')
    pp.add_argument('--timeout', type=int, default=10000)

    ps = sub.add_parser('solve', help='Solve one formula')
    ps.add_argument('formula')
    ps.add_argument('--method', choices=['baseline', 'improved'], default='baseline')
    ps.add_argument('--timeout', type=int, default=5000)

    args = ap.parse_args()
    if args.cmd == 'tests':
        run_tests(args.method, args.timeout)
    elif args.cmd == 'tptp':
        run_tptp(args.file, args.method, args.timeout)
    elif args.cmd == 'solve':
        run_solve(args.formula, args.method, args.timeout)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
