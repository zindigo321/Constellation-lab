from dataclasses import dataclass, asdict
import math
import re
from .io import read_csv, write_csv
from .orbit import sso_inclination

FIELDS = ['sat_id', 'plane_id', 'altitude_km', 'inclination_deg', 'raan_deg', 'arg_lat_deg']


@dataclass(frozen=True)
class Orbit:
    sat_id: str
    plane_id: int
    altitude_km: float
    inclination_deg: float
    raan_deg: float
    arg_lat_deg: float


def validate_n(n):
    if isinstance(n, bool) or not isinstance(n, int) or not 2 <= n <= 100:
        raise ValueError('N must be an integer in [2, 100]')
    return n


def validate(rows, n=None):
    validate_n(len(rows) if n is None else n)
    if n is not None and len(rows) != n:
        raise ValueError('satellite count differs from requested N')
    names, states = set(), set()
    for r in rows:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', r.sat_id) or r.sat_id in names:
            raise ValueError('sat_id must be unique ASCII identifier')
        names.add(r.sat_id)
        if isinstance(r.plane_id, bool) or not isinstance(r.plane_id, int) or r.plane_id < 0:
            raise ValueError('plane_id must be a nonnegative integer')
        values = (r.altitude_km, r.inclination_deg, r.raan_deg, r.arg_lat_deg)
        if not all(math.isfinite(v) for v in values):
            raise ValueError('all orbit values must be finite')
        if abs(r.inclination_deg - sso_inclination(r.altitude_km)) > 1e-7:
            raise ValueError('inclination violates configured secular SSO relation')
        if not 0 <= r.raan_deg < 360 or not 0 <= r.arg_lat_deg < 360:
            raise ValueError('angles must be in [0, 360)')
        state = tuple(round(v, 8) for v in values)
        if state in states:
            raise ValueError('duplicate initial orbital state')
        states.add(state)
    return rows


def read_orbits(path):
    rows = read_csv(path)
    if not rows or set(rows[0]) != set(FIELDS):
        raise ValueError('orbit CSV headers must be: ' + ','.join(FIELDS))
    result = [Orbit(r['sat_id'], int(r['plane_id']), *(float(r[k]) for k in FIELDS[2:])) for r in rows]
    return validate(result)


def write_orbits(path, rows):
    validate(rows)
    write_csv(path, FIELDS, [asdict(r) for r in rows])
