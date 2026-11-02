import math
from .schema import Orbit, validate, validate_n
from .orbit import sso_inclination


def default_planes(n):
    validate_n(n)
    # Deterministic factor choice, 28 -> 7 x 4. Prime N selects 1 or N planes.
    return min((p for p in range(1, n+1) if n % p == 0), key=lambda p: (abs(p-math.sqrt(2*n)), p))


def generate(n, planes=None, family='walker', f=None, altitude=600., raan0=0., phase0=0., phases=None, spacings=None):
    validate_n(n)
    planes = default_planes(n) if planes is None else planes
    if isinstance(planes, bool) or not isinstance(planes, int) or not 1 <= planes <= n:
        raise ValueError('planes must be integer in [1,N]')
    if family not in ('walker', 'balanced', 'custom'):
        raise ValueError('unknown constellation family')
    if family == 'walker' and n % planes:
        raise ValueError('Walker requires P to divide N; use balanced for arbitrary P')
    f=(1 if planes>1 else 0) if f is None else f
    if isinstance(f, bool) or not isinstance(f, int) or not 0 <= f < planes:
        raise ValueError('Walker F must be in [0,P-1]')
    if not all(math.isfinite(v) for v in (altitude, raan0, phase0)):
        raise ValueError('parameters must be finite')
    raan0 %= 360
    phase0 %= 360
    q, r = divmod(n, planes)
    counts = [q + (p < r) for p in range(planes)]
    phases = [0.] * planes if phases is None else list(phases)
    spacings = [1.] * planes if spacings is None else list(spacings)
    if len(phases) != planes or not all(math.isfinite(v) for v in phases):
        raise ValueError('one finite phase offset per plane required')
    if len(spacings) != planes or not all(math.isfinite(v) and v > 0 for v in spacings):
        raise ValueError('one positive RAAN spacing per plane required')
    if family != 'custom' and (any(v != 0 for v in phases) or len(set(spacings)) != 1):
        raise ValueError('free phases / nonuniform RAAN require custom family')
    inc = sso_inclination(altitude)
    rows, offset = [], 0.
    for p, count in enumerate(counts):
        for s in range(count):
            rows.append(Orbit(f'Sat{len(rows)+1:03d}', p, altitude, inc,
                              (raan0+offset) % 360,
                              (phase0+360*s/count+360*f*p/n+phases[p]) % 360))
        offset += 360*spacings[p]/sum(spacings)
    return validate(rows, n)
