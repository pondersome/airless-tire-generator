"""Offline smoke test of the add-in's geometry and validation rules.

Usage:
    python tools/smoke_test.py

Each case gives setting overrides and the expected outcome:
    'ok'           builds with no messages
    'note'/'warn'  builds, with at least one message starting Note:/Warning:
    'error'        refused (OK would be disabled in the dialog)
Exits non-zero if any case doesn't match, so it can run before a commit.
"""
import sys

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import load_addin, settings  # noqa: E402

CASES = [
    # (description, overrides, expected, optional text the message must contain)
    ('Gothic defaults', {'pattern': 'gothic'}, 'ok', None),
    ('Gothic 24 arches merge', {'pattern': 'gothic', 'g_count': 24}, 'note', 'merge'),
    ('Gothic no rim, bulge 0.15: narrow gap', {'pattern': 'gothic', 'outer_lines': 0}, 'warn', 'narrower than one line'),
    ('Gothic no rim, bulge 0.12', {'pattern': 'gothic', 'outer_lines': 0, 'g_bulge': 0.12}, 'ok', None),
    ('Gothic apex toward hub', {'pattern': 'gothic', 'g_apex': 'Toward hub', 'g_bulge': 0.05}, 'ok', None),
    ('Spoke as thick as a rim', {'pattern': 'gothic', 'g_spoke_lines': 4}, 'error', 'thinner than both rims'),
    ('Curved defaults', {'pattern': 'curved'}, 'ok', None),
    ('Curved S-curve', {'pattern': 'curved', 'c_shape': 'S-curve (two arcs)', 'c_bulge': 0.25}, 'ok', None),
    ('Curved alternate, odd count', {'pattern': 'curved', 'c_alternate': True, 'c_count': 15}, 'error', 'even'),
    ('Curved alternate, even count', {'pattern': 'curved', 'c_alternate': True, 'c_lean': 10, 'c_bulge': 0.2}, 'ok', None),
    ('Honeycomb defaults', {'pattern': 'honey'}, 'ok', None),
    ('Honeycomb too coarse collapses', {'pattern': 'honey', 'h_count': 12}, 'error', 'collapse'),
    ('Honeycomb brick', {'pattern': 'honey', 'h_angle': 0}, 'ok', None),
    ('Honeycomb auxetic -20', {'pattern': 'honey', 'h_angle': -20}, 'ok', None),
    ('Honeycomb auxetic -30 merges', {'pattern': 'honey', 'h_angle': -30}, 'note', 'merge'),
    ('Honeycomb no rim closed', {'pattern': 'honey', 'outer_lines': 0}, 'ok', None),
    ('Honeycomb no rim open', {'pattern': 'honey', 'outer_lines': 0, 'keep_open': True}, 'ok', None),
    ('Honeycomb 128 cells, 2-line walls', {'pattern': 'honey', 'h_count': 128, 'outer_lines': 0,
                                           'keep_open': True}, 'error', 'no longer than they are thick'),
    ('Honeycomb 128 cells, 1-line walls', {'pattern': 'honey', 'h_count': 128, 'h_lines': 1,
                                           'outer_lines': 0, 'keep_open': True}, 'warn', 'tiny'),
    ('Mixed anchors', {'a_peg_n': 6, 'a_t_n': 6, 'a_t_phase': 20, 'a_dt_n': 6, 'a_dt_phase': 40}, 'ok', None),
    ('Peg stem as wide as head', {'a_peg_n': 8, 'a_peg_stem_w': 4}, 'error', 'narrower than the head'),
    ('Peg hole too big for wall', {'a_peg_n': 8, 'a_peg_id': 2.8}, 'error', 'thinner than one line'),
    ('Peg hole ok', {'a_peg_n': 8, 'a_peg_id': 2.5}, 'ok', None),
    ('Dovetail tip not wider', {'a_dt_n': 3, 'a_dt_tip_w': 3}, 'error', 'wider than the root'),
    ('T-slot head not wider', {'a_t_n': 2, 'a_t_head_w': 2}, 'error', 'wider than the neck'),
    ('Dovetails crowd at tips', {'a_dt_n': 20, 'a_dt_d': 8}, 'warn', 'tips'),
    ('Anchors overlap each other', {'a_peg_n': 12, 'a_t_n': 12}, 'warn', 'overlap'),
]


def classify(err, warns):
    if err:
        return 'error'
    if any(w.startswith('Warning') for w in warns):
        return 'warn'
    if warns:
        return 'note'
    return 'ok'


def main():
    mod = load_addin()
    failed = 0
    for desc, over, expected, text in CASES:
        p = settings(mod, over)
        err, warns = mod.assess(p)
        got = classify(err, warns)
        msgs = ([err] if err else []) + warns
        good = got == expected and (text is None or any(text in m for m in msgs))
        failed += 0 if good else 1
        print('%s  %-40s expected %-5s got %-5s %s'
              % ('PASS' if good else 'FAIL', desc, expected, got, (' | '.join(msgs))[:110]))
    # settings migration from earlier versions
    checks = [
        (mod.migrate({'pattern': 'Gothic arch', 'keep_outer': False}).get('keep_open'), True),
        (mod.migrate({'pattern': 'Honeycomb', 'keep_outer': True}).get('keep_open'), True),
        (mod.migrate({'a_peg_w': 5.0}).get('a_peg_dia'), 5.0),
    ]
    for i, (got, want) in enumerate(checks):
        good = got == want
        failed += 0 if good else 1
        print('%s  migration check %d: got %r want %r' % ('PASS' if good else 'FAIL', i + 1, got, want))
    print('\n%d failure(s)' % failed)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
