"""R25 N-only deterministic generator. Standard library only; no STK or search."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile

BUNDLE = Path(__file__).resolve().parent
sys.path.insert(0, str(BUNDLE))  # supports python -I -S and any caller cwd
from core.constellation import generate as core_generate
from core.orbit import CONSTANTS, nodal_rate, YEAR_S
from core.schema import FIELDS, validate_n

VERSION = 'R25-balanced-1.1.0'


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                       allow_nan=False) + '\n').encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_policy():
    policy = json.loads((BUNDLE / 'policy.json').read_text(encoding='utf-8'))
    # This version has a single reviewed strategy; changed policies need a new version.
    fixed = {'algorithm_version': VERSION, 'altitude_km': 600.0,
             'raan0_deg': 0.0, 'phase0_deg': 0.0, 'eccentricity': 0.0,
             'arg_perigee_deg': 0.0, 'reference_frame': 'J2000',
             'epoch': '2027-01-01 00:00:00', 'stop': '2027-01-08 00:00:00',
             'time_system': 'UTCG', 'propagator': 'J2Perturbation',
             'propagation_step_s': 30.0, 'sso_residual_tolerance_rad_s': 1e-15}
    if any(policy.get(k) != v or isinstance(policy.get(k), bool)
           for k, v in fixed.items()):
        raise ValueError('policy is incompatible with algorithm version ' + VERSION)
    return policy


def automatic_planes(n):
    validate_n(n)
    low = math.isqrt(2 * n)
    nearest = low + (8 * n >= (2 * low + 1) ** 2)
    return min(n, max(2, nearest))


def generate(n):
    """Return independent rows and complete metadata; N is the only design input."""
    validate_n(n)
    policy = load_policy()
    planes = automatic_planes(n)
    family = 'walker' if n % planes == 0 else 'balanced'
    # With even P and odd equal population, F=1 puts an opposite-plane pair
    # at the same node at epoch. Opposite parity removes that node coincidence.
    phase_factor = (0 if planes == 2 else 2) if (n % planes == 0 and planes % 2 == 0 and (n // planes) % 2 == 1) else 1
    orbits = core_generate(n, planes=planes, family=family, f=phase_factor,
                          altitude=policy['altitude_km'], raan0=0., phase0=0.)
    rows = [asdict(row) for row in orbits]
    target_rate = 2 * math.pi / YEAR_S
    residual = max(abs(nodal_rate(row.altitude_km, row.inclination_deg) - target_rate)
                   for row in orbits)
    if residual > policy['sso_residual_tolerance_rad_s']:
        raise ValueError('J2 secular SSO rate residual exceeds tolerance')
    plane_table = []
    for p in range(planes):
        members = [row for row in rows if row['plane_id'] == p]
        plane_table.append(dict(plane_id=p, count=len(members),
                                raan_deg=members[0]['raan_deg'],
                                phase_offset_deg=(360*phase_factor*p/n) % 360,
                                satellite_ids=[row['sat_id'] for row in members]))
    metadata = dict(schema_version=1, algorithm_version=VERSION, n=n,
                    family='Walker-Delta' if family == 'walker' else 'custom-balanced-Delta',
                    planes=planes, phase_factor=phase_factor, allocation=plane_table, policy=policy,
                    constants=dict(CONSTANTS), constants_provisional=True,
                    altitude_definition='a_km = earth_mean_radius_km + altitude_km',
                    circular_element_mapping='e=0; omega=0; true_anomaly=arg_lat_deg; J2000',
                    target_node_rate_rad_s=target_rate,
                    sso_formula='-1.5*J2*sqrt(mu/a^3)*(R_J2/a)^2*cos(i); e=0',
                    max_sso_residual_rad_s=residual,
                    parameter_status='PASS', performance_status='UNVALIDATED',
                    native_validation_status='NOT_RUN', official_score=None,
                    identity_role='GENERIC_R25_CANDIDATE; separate from B0, S and R24',
                    input_kind='current deterministic generation from N and bundled policy; no orbit caches',
                    source_sha256={p.relative_to(BUNDLE).as_posix(): sha(p.read_bytes())
                                   for p in sorted([BUNDLE/'generate.py', BUNDLE/'policy.json',
                                                    * (BUNDLE/'core').glob('*.py')])})
    return rows, metadata


def render(n):
    rows, metadata = generate(n)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    csv_data = stream.getvalue().encode('utf-8')
    metadata['orbit_csv_sha256'] = sha(csv_data)
    return csv_data, json_bytes(metadata)


def export(n, out):
    # Validate and render fully before creating any output directory.
    csv_data, config_data = render(n)
    target = Path(out).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError('output already exists; choose a new directory: ' + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + target.name + '.UNCOMMITTED-', dir=target.parent))
    location = staging
    try:
        for name, data in [('orbits.csv', csv_data), ('config.json', config_data)]:
            with (staging/name).open('xb') as stream:
                stream.write(data)
            if (staging/name).read_bytes() != data:
                raise OSError('output readback mismatch: ' + name)
        receipt = dict(status='PASS', n=n, algorithm_version=VERSION,
                       performance_status='UNVALIDATED', native_validation_status='NOT_RUN',
                       official_score=None,
                       files={'orbits.csv': dict(bytes=len(csv_data), sha256=sha(csv_data)),
                              'config.json': dict(bytes=len(config_data), sha256=sha(config_data))})
        receipt_data = json_bytes(receipt)
        with (staging/'RECEIPT.pending').open('xb') as stream:
            stream.write(receipt_data)
        if (staging/'RECEIPT.pending').read_bytes() != receipt_data:
            raise OSError('receipt readback mismatch')
        if target.exists():
            raise FileExistsError('output appeared while writing; no overwrite')
        os.rename(staging, target)
        location = target
        os.rename(target/'RECEIPT.pending', target/'COMPLETE.json')
        return receipt
    except (OSError, ValueError) as error:
        # Keep partial evidence, never emit a success receipt for incomplete writes.
        if not (location/'COMPLETE.json').exists():
            try:
                with (location/'FAILED.txt').open('x', encoding='utf-8') as stream:
                    stream.write(type(error).__name__ + ': ' + str(error))
            except OSError:
                pass  # Original I/O error remains the failure returned to caller.
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description='R25 N-only constellation generator; performance UNVALIDATED')
    parser.add_argument('N', type=int, help='required integer satellite count, 2..100')
    parser.add_argument('--out', type=Path, help='new output directory; default: ./N<N>')
    args = parser.parse_args(argv)
    try:
        receipt = export(args.N, args.out if args.out is not None else Path.cwd()/f'N{args.N}')
    except ValueError as error:
        parser.error(str(error))
    except OSError as error:
        print('OUTPUT_ERROR: ' + str(error), file=sys.stderr)
        return 3
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
