#!/usr/bin/env python3
"""Offline PYNQ evidence checks. No board, network, overlay download or EDA runs."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def compare(args):
    import numpy as np
    for value in (args.atol, args.rtol):
        if not math.isfinite(value) or value < 0:
            raise ValueError('Tolerances must be finite and nonnegative')
    ref = np.load(args.reference, allow_pickle=False)
    got = np.load(args.actual, allow_pickle=False)
    result = dict(scope='offline_array_comparison', passed=False, mode=args.mode,
                  reference_sha256=sha256(args.reference), actual_sha256=sha256(args.actual),
                  atol=args.atol, rtol=args.rtol)
    if not isinstance(ref, np.ndarray) or not isinstance(got, np.ndarray):
        raise ValueError('Only .npy arrays are supported')
    if ref.shape != got.shape:
        return dict(result, reason='shape mismatch'), 1
    if ref.dtype != got.dtype:
        return dict(result, reason='dtype mismatch'), 1
    if ref.dtype.kind not in 'biuf':
        raise ValueError('Only boolean, integer and real floating arrays are supported')
    result.update(shape=list(ref.shape), dtype=str(ref.dtype), elements=int(ref.size))
    if ref.size == 0:
        return dict(result, reason='empty output'), 1
    if not np.isfinite(ref).all() or not np.isfinite(got).all():
        return dict(result, reason='nonfinite array value'), 1
    if args.mode == 'exact':
        # Preserve all integer bits; uint64/int64 must not pass through float64.
        if args.atol != 0 or args.rtol != 0:
            raise ValueError('Tolerances are not used in exact mode')
        equal = ref == got
    else:
        if ref.dtype.kind != 'f':
            raise ValueError('Float tolerance mode requires floating arrays')
        # Compare directly so a tolerance-boundary value is not perturbed by scaling.
        a, b = ref.astype(np.longdouble), got.astype(np.longdouble)
        with np.errstate(over='ignore', under='ignore'):
            error = np.abs(b - a)
            bound = args.atol + args.rtol * np.abs(a)
        if not np.isfinite(error).all() or not np.isfinite(bound).all():
            raise ValueError('Comparison arithmetic overflow; choose consistent smaller units before comparison')
        equal = error <= bound
    bad = np.flatnonzero(~equal)
    result.update(passed=bad.size == 0, mismatch_count=int(bad.size))
    if bad.size:
        pos = int(bad[0])
        def scalar(value):
            if ref.dtype.kind in 'biu':
                return int(value)
            f = float(value)
            return f if math.isfinite(f) else str(value)
        result['first_mismatch'] = dict(index=[int(i) for i in np.unravel_index(pos, ref.shape)],
                                        reference=scalar(ref.flat[pos]), actual=scalar(got.flat[pos]))
    return result, 0 if result['passed'] else 1


def summary(values):
    ordered = sorted(values)
    return dict(n=len(values), mean_ms=statistics.mean(values), median_ms=statistics.median(values),
                min_ms=min(values), max_ms=max(values), std_population_ms=statistics.pstdev(values),
                p95_nearest_rank_ms=ordered[math.ceil(0.95 * len(ordered)) - 1])


def aba(args):
    if not math.isfinite(args.drift_pct) or args.drift_pct < 0:
        raise ValueError('Drift threshold must be finite and nonnegative')
    with args.samples.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'case', 'group', 'iteration', 'warmup', 'correct', 'elapsed_ms', 'run_id',
                    'environment_id', 'artifact_id', 'timing_boundary', 'input_id', 'reference_id'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Missing CSV columns: ' + ', '.join(sorted(required - set(reader.fieldnames or []))))
        rows = list(reader)
    if not rows:
        raise ValueError('Empty sample file')
    cases, seen = {}, set()
    for row in rows:
        if any(not row.get(key) for key in required):
            raise ValueError('Empty required CSV value')
        if row['group'] not in ('A1', 'B', 'A2') or row['warmup'] not in ('0', '1') or row['correct'] not in ('0', '1'):
            raise ValueError('Invalid group, warmup or correct flag')
        elapsed = float(row['elapsed_ms'])
        if not math.isfinite(elapsed) or elapsed <= 0:
            raise ValueError('elapsed_ms must be positive and finite')
        if not row['iteration'].isdigit():
            raise ValueError('iteration must be a nonnegative integer')
        key = (row['case'], row['group'], int(row['iteration']))
        if key in seen:
            raise ValueError('Duplicate iteration in a case/group')
        seen.add(key)
        row['_elapsed'] = elapsed
        cases.setdefault(row['case'], []).append(row)
    result = dict(scope='offline_aba_statistics', input_sha256=sha256(args.samples), input_rows=len(rows),
                  board_verified_by_this_tool=False, data_checks_passed=True,
                  drift_threshold_pct=args.drift_pct, cases={})
    for name, records in cases.items():
        for field in ('run_id', 'environment_id', 'timing_boundary', 'input_id', 'reference_id'):
            if len({r[field] for r in records}) != 1:
                raise ValueError(f'{name}: inconsistent {field}')
        order = []
        for record in records:
            if not order or order[-1] != record['group']:
                order.append(record['group'])
        if order != ['A1', 'B', 'A2']:
            raise ValueError(f'{name}: expected contiguous A1, B, A2 groups')
        stats, artifacts = {}, {}
        for group in order:
            subset = [r for r in records if r['group'] == group]
            ids = {r['artifact_id'] for r in subset}
            if len(ids) != 1:
                raise ValueError(f'{name}/{group}: inconsistent artifact_id')
            artifacts[group] = next(iter(ids))
            measured = [r['_elapsed'] for r in subset if r['warmup'] == '0']
            if not measured:
                raise ValueError(f'{name}/{group}: no measured samples')
            encountered_measurement = False
            for r in subset:
                if r['warmup'] == '0': encountered_measurement = True
                elif encountered_measurement: raise ValueError(f'{name}/{group}: warmup occurs after measurement')
            stats[group] = dict(summary(measured), warmup_n=len(subset) - len(measured))
        if artifacts['A1'] != artifacts['A2']:
            raise ValueError(f'{name}: baseline artifact changed at A2')
        a1, b, a2 = (stats[g]['mean_ms'] for g in order)
        faster_a = min(a1, a2)
        drift = abs(a2 - a1) / faster_a * 100
        correct = all(r['correct'] == '1' for r in records)
        case = dict(groups=stats, artifacts=artifacts, all_rows_correct=correct,
                    baseline_drift_pct=drift, drift_within_threshold=drift <= args.drift_pct,
                    average_baseline_saved_ms=(a1 + a2) / 2 - b,
                    conservative_saved_ms=faster_a - b,
                    conservative_reduction_pct=(faster_a - b) / faster_a * 100,
                    warnings=[])
        if min(s['n'] for s in stats.values()) < 10:
            case['warnings'].append('Fewer than 10 measured samples in at least one group; limited distribution evidence')
        case['declared_context'] = {key: records[0][key] for key in
                                   ('run_id', 'environment_id', 'timing_boundary', 'input_id', 'reference_id')}
        result['cases'][name] = case
        result['data_checks_passed'] &= correct and case['drift_within_threshold']
    return result, 0 if result['data_checks_passed'] else 1


def artifacts(args):
    contract = json.loads(args.contract.read_text(encoding='utf-8'))
    if not isinstance(contract.get('build_id'), str) or not contract['build_id'].strip():
        raise ValueError('Contract needs a nonempty build_id')
    entries = contract.get('artifacts', {})
    result = dict(scope='offline_file_identity', build_id=contract['build_id'],
                  contract_sha256=sha256(args.contract), file_hashes_match=True,
                  semantic_pairing='not_proven', board_verified_by_this_tool=False, artifacts={})
    for key in ('bit', 'hwh'):
        entry = entries.get(key, {})
        expected = entry.get('sha256', '')
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-fA-F]{64}', expected):
            raise ValueError(f'{key}: expected a full SHA256')
        path = entry.get('path')
        if not isinstance(path, str) or not path:
            raise ValueError(f'{key}: missing file path')
        actual_path = (args.root or args.contract.parent) / path
        actual = sha256(actual_path)
        match = actual == expected.lower()
        result['artifacts'][key] = dict(path=path, expected_sha256=expected.lower(), actual_sha256=actual, matches=match)
        result['file_hashes_match'] &= match
    return result, 0 if result['file_hashes_match'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('compare', help='Compare two .npy output arrays')
    p.add_argument('reference', type=Path); p.add_argument('actual', type=Path)
    p.add_argument('--mode', choices=('exact', 'float'), default='exact')
    p.add_argument('--atol', type=float, default=0); p.add_argument('--rtol', type=float, default=0)
    p.set_defaults(handler=compare)
    p = subs.add_parser('aba', help='Summarize ordered A1/B/A2 CSV samples')
    p.add_argument('samples', type=Path)
    p.add_argument('--drift-pct', type=float, default=5, help='Project-specific allowed A1/A2 mean drift (default 5 percent)')
    p.set_defaults(handler=aba)
    p = subs.add_parser('artifacts', help='Verify bit/HWH file hashes against a build contract')
    p.add_argument('contract', type=Path); p.add_argument('--root', type=Path)
    p.set_defaults(handler=artifacts)
    for sub in subs.choices.values():
        sub.add_argument('--out', required=True, type=Path, help='New JSON file; existing files are not overwritten')
    args = parser.parse_args()
    try:
        report, code = args.handler(args)
    except (ValueError, OSError, TypeError, KeyError, ImportError, AttributeError) as error:
        report, code = dict(scope='offline_check', error=str(error)), 2
    try:
        with args.out.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=True, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
