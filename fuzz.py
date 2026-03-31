#!/usr/bin/env python3
import sys
import atheris

with atheris.instrument_imports():
    pass

TARGETS = []
try:
    import fuzz as _m
    if hasattr(_m, 'fuzz_task_loading'):
        TARGETS.append(getattr(_m, 'fuzz_task_loading'))
except Exception:
    pass
try:
    import scripts.benchmark as _m
    if hasattr(_m, 'load_tasks'):
        TARGETS.append(getattr(_m, 'load_tasks'))
except Exception:
    pass
try:
    import scripts.lib_grading as _m
    if hasattr(_m, 'load_default_judge_api_key'):
        TARGETS.append(getattr(_m, 'load_default_judge_api_key'))
except Exception:
    pass
try:
    import scripts.lib_tasks as _m
    if hasattr(_m, 'load_all_tasks'):
        TARGETS.append(getattr(_m, 'load_all_tasks'))
except Exception:
    pass
try:
    import scripts.lib_tasks as _m
    if hasattr(_m, 'load_task'):
        TARGETS.append(getattr(_m, 'load_task'))
except Exception:
    pass
try:
    import scripts.lib_upload as _m
    if hasattr(_m, 'upload_results'):
        TARGETS.append(getattr(_m, 'upload_results'))
except Exception:
    pass
try:
    import scripts.generate_token_cost_maps as _m
    if hasattr(_m, 'parse_args'):
        TARGETS.append(getattr(_m, 'parse_args'))
except Exception:
    pass


def _call_target(fn, data: bytes):
    txt = data.decode('utf-8', errors='ignore')
    for arg in (data, txt):
        try:
            fn(arg)
            return
        except TypeError:
            continue

@atheris.instrument_func
def TestOneInput(data):
    if not TARGETS:
        return
    for fn in TARGETS:
        try:
            _call_target(fn, data)
        except (ValueError, TypeError, UnicodeDecodeError, AssertionError):
            pass


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()

if __name__ == '__main__':
    main()
