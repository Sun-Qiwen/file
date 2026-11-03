"""Compile the C++ example and verify positive/negative native testbench runs.

No HLS/Vivado invocation, hardware access, or existing-output overwrite.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='g++', help='GCC/Clang-compatible C++ executable')
    parser.add_argument('--out', required=True, type=Path, help='New native build/output directory')
    args = parser.parse_args()
    compiler = shutil.which(args.compiler)
    if compiler is None:
        parser.error('C++ compiler not found; pass --compiler with its path')
    dest = args.out.resolve()
    if dest.exists():
        parser.error('Output exists; choose a new --out directory')
    dest.mkdir(parents=True)
    tmp = dest / 'tmp'; tmp.mkdir()
    source = Path(__file__).resolve().parent
    executable = dest / ('vector_add_test.exe' if os.name == 'nt' else 'vector_add_test')
    env = dict(os.environ)
    env.update({key: str(tmp) for key in ('TMP', 'TEMP', 'TMPDIR')})
    env['PATH'] = str(Path(compiler).parent) + os.pathsep + env.get('PATH', '')
    result = {'scope': 'native_cpp_only', 'pass': False, 'hls_synthesized': False,
              'rtl_cosimulated': False, 'board_tested': False, 'compiler': str(compiler),
              'source_sha256': {}, 'steps': []}
    for name in ('vector_add.hpp', 'vector_add.cpp', 'testbench.cpp', 'run_native.py', 'run_hls.tcl'):
        result['source_sha256'][name] = hashlib.sha256((source / name).read_bytes()).hexdigest()

    def run(label, command, expected, marker='', timeout=120):
        try:
            process = subprocess.run(command, cwd=dest, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                     errors='replace', timeout=timeout, check=False)
            log, code = process.stdout, process.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            log, code = str(error), None
        (dest / (label + '.log')).write_text(log, encoding='utf-8')
        passed = code == expected and marker in log
        result['steps'].append({'name': label, 'command': [str(x) for x in command],
                                'returncode': code, 'expected_returncode': expected,
                                'required_marker': marker, 'pass': passed})
        print(label + ': ' + ('PASS' if passed else 'FAIL'))
        return passed

    ok = run('compiler', [compiler, '--version'], 0)
    command = [compiler, '-std=c++14', '-O2', '-Wall', '-Wextra', '-Wno-unknown-pragmas']
    if os.name == 'nt':
        command += ['-static-libgcc', '-static-libstdc++']
    command += [str(source / 'vector_add.cpp'), str(source / 'testbench.cpp'), '-o', str(executable)]
    if ok: ok = run('build', command, 0)
    if ok: ok = run('positive', [str(executable)], 0, 'PASS cases=36', timeout=30)
    if ok: ok = run('negative', [str(executable), '--inject-error'], 1,
                    'INJECTED_ERROR_DETECTED', timeout=30)
    result['pass'] = ok
    (dest / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
