"""J2 mean secular sun-synchronous constraint, km / seconds / degrees."""
import math

R_MEAN = 6371.0
MU = 398600.4415
R_J2 = 6378.1363
J2 = math.sqrt(5.0) * 0.484165143790815e-3
YEAR_S = 365.2421897 * 86400.0
CONSTANTS = dict(earth_mean_radius_km=R_MEAN, mu_km3_s2=MU,
                 j2_reference_radius_km=R_J2, j2=J2, year_seconds=YEAR_S,
                 provenance='Local STK 11.6 Earth.cb and EGM2008.grv; C20 reference epoch J2000; secular variation not applied')


def nodal_rate(altitude_km, inclination_deg):
    a = R_MEAN + altitude_km
    return -1.5 * J2 * math.sqrt(MU / a**3) * (R_J2 / a)**2 * math.cos(math.radians(inclination_deg))


def sso_inclination(altitude_km):
    if not math.isfinite(altitude_km) or not 500 <= altitude_km <= 700:
        raise ValueError('altitude_km must be finite and in [500, 700]')
    a = R_MEAN + altitude_km
    c = -(2 * math.pi / YEAR_S) / (1.5 * J2 * math.sqrt(MU / a**3) * (R_J2 / a)**2)
    return math.degrees(math.acos(c))


def cartesian(row):
    """Circular J2000 r,v in km and km/s; omega=0, true anomaly=u."""
    a = R_MEAN + row.altitude_km
    i, o, u = map(math.radians, (row.inclination_deg, row.raan_deg, row.arg_lat_deg))
    co, so, ci, si, cu, su = math.cos(o), math.sin(o), math.cos(i), math.sin(i), math.cos(u), math.sin(u)
    r = (a*(co*cu-so*su*ci), a*(so*cu+co*su*ci), a*su*si)
    v = math.sqrt(MU/a)
    return r, (v*(-co*su-so*cu*ci), v*(-so*su+co*cu*ci), v*cu*si)
