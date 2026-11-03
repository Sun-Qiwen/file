"""Synthetic vector-add demonstration; no hardware or real bitstream involved."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    a = np.arange(-64, 64, dtype=np.int16)
    b = np.arange(127, -1, -1, dtype=np.int16)
    reference = a.astype(np.int32) + b.astype(np.int32)
    actual = np.array([int(x) + int(y) for x, y in zip(a, b)], dtype=np.int32)
    broken = actual.copy(); broken[-1] += 1
    for name, value in [('reference', reference), ('actual', actual), ('broken', broken)]:
        np.save(out / (name + '.npy'), value, allow_pickle=False)
    rows = []
    for group, values in [('A1', [100, 101, 99]), ('B', [70, 69, 71]), ('A2', [101, 100, 99])]:
        for i, ms in enumerate([500] + values):
            rows.append(dict(case='synthetic-vector-add', group=group, iteration=i,
                             warmup=int(i == 0), correct=1, elapsed_ms=ms,
                             run_id='synthetic-only', environment_id='no-board',
                             artifact_id='synthetic-a' if group != 'B' else 'synthetic-b',
                             timing_boundary='synthetic-call-wall', input_id='synthetic-vector-128',
                             reference_id='numpy-int32-add'))
    with (out / 'samples.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    contract = dict(build_id='synthetic-not-for-loading', artifacts={})
    for kind in ('bit', 'hwh'):
        path = out / ('synthetic-' + kind + '.txt')
        path.write_text('Synthetic identity test only. Not a hardware artifact.\n', encoding='utf-8')
        contract['artifacts'][kind] = dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (out / 'contract.json').write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
    checks = [
        ('golden', ['compare', out / 'reference.npy', out / 'actual.npy'], 0),
        ('negative', ['compare', out / 'reference.npy', out / 'broken.npy'], 1),
        ('performance', ['aba', out / 'samples.csv'], 0),
        ('identity', ['artifacts', out / 'contract.json'], 0),
    ]
    results = []
    for name, argv, expected in checks:
        command = [sys.executable, '-B', str(ROOT / 'scripts' / 'evidence.py'),
                   *map(str, argv), '--out', str(out / (name + '.json'))]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        results.append(dict(name=name, expected_exit=expected, actual_exit=result.returncode,
                            passed=result.returncode == expected))
        if result.returncode != expected:
            print(result.stdout + result.stderr, file=sys.stderr)
    report = dict(data_origin='synthetic', board_tested=False, checks=results,
                  passed=all(r['passed'] for r in results))
    (out / 'demo.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
