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
    # tread profiles
    ('Crowned defaults', {'profile': 'crowned'}, 'ok', None),
    ('Crowned flat crown, rolled edges', {'profile': 'crowned', 'pc_crown_r': 0, 'pc_shoulder_r': 6}, 'ok', None),
    ('Crown radius under half the crown', {'profile': 'crowned', 'pc_crown_r': 5}, 'error',
     'more than half the crown width'),
    ('Shoulders turn vertical early', {'profile': 'crowned', 'pc_shoulder_r': 3}, 'error',
     'Shoulder radius must be more than'),
    ('Crown wider than the tire', {'profile': 'crowned', 'pc_crown_w': 25}, 'error', 'more than the tire width'),
    ('Steep shoulders', {'profile': 'crowned', 'pc_shoulder_r': 5}, 'warn', 'from vertical'),
    ('Squeeze opens a sliver at the faces', {'pattern': 'gothic', 'g_count': 14, 'profile': 'crowned',
                                             'pc_crown_w': 0, 'pc_crown_r': 0, 'pc_shoulder_r': 20},
     'warn', '(at the faces)'),
    ('Crown too deep for the zone', {'profile': 'crowned', 'tire_od': 80, 'pc_crown_w': 0, 'pc_crown_r': 0,
                                     'pc_shoulder_r': 11}, 'error', 'needs at least 2 mm'),
    ('Grooved defaults: lands gap', {'profile': 'grooved'}, 'warn', 'Warning (at the lands)'),
    ('Grooved defaults, bulge 0.12', {'profile': 'grooved', 'g_bulge': 0.12}, 'ok', None),
    ('Groove wider than the tire', {'profile': 'grooved', 'pg_contact_w': 30}, 'error', 'more than the tire width'),
    ('Groove as wide as the ball', {'profile': 'grooved', 'pg_ball_d': 15}, 'error', 'less than the ball diameter'),
    ('Groove bottom leaves no spoke zone', {'profile': 'grooved', 'tire_od': 70}, 'error', 'Spoke zone is only'),
    ('Honeycomb collapses at groove bottom', {'pattern': 'honey', 'h_count': 14, 'h_rows': 2, 'h_lines': 1,
                                              'profile': 'grooved', 'pg_ball_d': 30, 'pg_contact_w': 20},
     'error', 'At the groove bottom'),
    ('Grooved open honeycomb, flat cells', {'pattern': 'honey', 'tire_od': 88, 'bore_d': 64, 'width': 40,
                                            'h_count': 40, 'h_rows': 2, 'h_lines': 1, 'outer_lines': 0,
                                            'keep_open': True, 'profile': 'grooved', 'pg_contact_w': 30},
     'warn', 'Warning (at the groove bottom)'),
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
    crown = mod.CrownProfile(30, 18, 80, 12)
    groove = mod.GrooveProfile(40, 127, 30)
    crowned = settings(mod, {'profile': 'crowned'})
    grooved = settings(mod, {'profile': 'grooved', 'width': 40, 'pg_contact_w': 30, 'tire_od': 88})
    g_lands = mod.compute(grooved)['radii'][3]
    old_groove = {'profile': 'Grooved', '_script_version': '1.12', 'tire_od': 91.5946, 'width': 40,
                  'pg_ball_d': 127, 'pg_contact_w': 30}
    checks = [
        # settings migration from earlier versions
        ('migrate keep_outer (Gothic)', mod.migrate({'pattern': 'Gothic arch', 'keep_outer': False}).get('keep_open'),
         True),
        ('migrate keep_outer (Honeycomb)', mod.migrate({'pattern': 'Honeycomb', 'keep_outer': True}).get('keep_open'),
         True),
        ('migrate square pegs', mod.migrate({'a_peg_w': 5.0}).get('a_peg_dia'), 5.0),
        ('pre-profile settings load flat', dict(mod.DEFAULTS, **mod.migrate({'pattern': 'Honeycomb'}))['profile'],
         'Flat'),
        # profile geometry (values worked out by hand)
        ('crown edge drop', round(crown.edge, 2), 2.95),
        ('crown face angle', round(crown.max_angle, 1), 37.8),
        ('groove depth', round(groove.depth, 2), 1.80),
        ('groove edge angle', round(groove.max_angle, 1), 13.7),
        ('groove edge sits on the OD', round(groove.drop_z(5.0), 9), 0.0),
        ('loft sections hit the knots', all(any(abs(z - k) < 1e-9 for z in crown.sections(0, 30))
                                            for k in (0, 6, 24, 30)), True),
        ('crowned record skips groove keys', 'pg_ball_d' in mod.relevant_keys(crowned), False),
        ('crowned record keeps crown keys', 'pc_crown_w' in mod.relevant_keys(crowned), True),
        # a grooved tire's OD is the groove bottom; it is built from the lands
        ('grooved: groove bottom = tire OD', round(2 * (g_lands - groove.depth), 6), 88.0),
        ('grooved: name keeps the OD as given', 'OD88 ' in mod.compute(grooved)['label'], True),
        ('migrate 1.12 grooved OD (lands)', round(mod.migrate(old_groove)['tire_od'], 2), 88.0),
        ('crowned OD unchanged (the crown)', mod.compute(crowned)['radii'][3], 48.0),
    ]
    for label, got, want in checks:
        good = got == want
        failed += 0 if good else 1
        print('%s  %-40s got %r want %r' % ('PASS' if good else 'FAIL', label, got, want))
    print('\n%d failure(s)' % failed)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
