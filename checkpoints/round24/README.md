# R24 conditional offline N28 research checkpoint

R24 repairs absolute deadline supervision, input progress reporting and
read-only cache validation, then completes the same 166,970-member limited
third-replacement union that R23 left unprocessed. Two candidates qualify;
the selected constellation lowers internal Tmax by 1,490.7857564479928 seconds
from the fixed R18 incumbent S. The original B0 remains the feasibility
reference and S remains this experiment's improvement reference.

| Processing | Independently verified |
| --- | ---: |
| T100 negative certificate | 166675 |
| T90 negative certificate | 239 |
| Full evaluation | 56 |
| Total | 166970 |

Unprocessed, unknown and candidate-result reuse are zero. Negative
certificates are not full evaluations. The conclusion covers only the
declared three-anchor third-replacement union, not the full catalog
three-replacement neighborhood or global optimality.

Selected identity:
`5e7b2b28cd8d1e2254b5968ad24db2bcc8e7dd61121b01468da6ea530a464a69`.

Relative to S, remove `{676,1412,2021}` and add `{196,1118,1997}`. Relative
to B0, remove `{676,1217,1284,1412}` and add `{196,1118,1997,2023}`.
The 28 catalog indices are
`[38,70,135,196,220,222,263,279,358,478,514,548,777,911,946,974,1118,1222,1370,1419,1931,1941,1949,1995,1997,2023,2049,2092]`.

| Metric, seconds | B0 | Fixed S | R24 selected |
| --- | ---: | ---: | ---: |
| mask T90 | 283728.33914436615 | 283626.3948020579 | 281750.47161919123 |
| mask T100 | 595089.2108747589 | 595089.2108747589 | 595089.2108747589 |
| pooled internal Tavg | 9413.983168107334 | 9251.526570870468 | 9360.61944171291 |
| internal Tmax | 172730.31608610202 | 132051.28738869302 | 130560.50163224502 |

The selected mean uses its actual 170 internal gaps, versus 175 for S.
Tavg increases by 109.0928708424417 seconds from S but stays below B0 by
53.36372639442379 seconds. Eligibility uses the original B0 constraints
and the conservative one-second Tmax improvement requirement against S;
the experiment did not add first/tail waiting constraints.

| Target | Selected first wait, seconds | Selected tail wait, seconds |
| --- | ---: | ---: |
| YangtzeRiverDelta | 3260.222305165 | 4570.868130479008 |
| Island_1 | 28608.394606022 | 4642.345470258035 |
| Island_2 | 35025.745550436 | 136700.71607742802 |

The main-region first wait increases from 1974.677382557 seconds and the
Island_1 first wait increases from 1984.348333089 seconds. Tail waits and
Island_2 first wait are unchanged. Boundary-inclusive Tmax remains
136700.71607742802 seconds. These costs are reported separately from
internal Tmax.

Mask coverage is 43070/43070. Original-domain coverage is 43070/43424,
with 354 uncovered points; original-domain T90 is 288686.03926296614
seconds and T100 is null. Missing points do not establish physical
unreachability or confirm that the temporary mask is official.

The [selected orbit CSV](selected_orbits.csv) is the new 2404-byte R24
artifact, SHA-256
`3d434ab103260c83be1cdcd7710ed212478239ba00b69a87d04d4e31cfb60221`.
R18/R19 checkpoints and their original selected file remain preserved.
The compact [evidence record](evidence.json) binds source, scientific and
delivery hashes; full input arrays, candidate logs and work trees remain
local.

The final frozen source has 434 consumers, preserving 400 earlier files
and six earlier checkpoint inputs. R24 passes 73 new tests, 788 historical
tests and 26 binding counterexamples. Research, export child, launcher,
finalizer and actual enclosing Shell exits are zero; the direct export
child has no Shell and its Shell field is null. Independent all-exits
readback completed at 4835.302668809891 preparation-inclusive seconds.

Clock and reporting limitations are retained. The first attachment read
preceded precise paired UTC/QPC sampling; a conservative earlier UTC
start was retained throughout, rather than resetting the budget. Strict
first-action paired sampling was not achieved. The final sealed report
has an inherited "round 23" title typo and the package description also
retains that wording, while its profile, contract and execution are
ROUND24; the immutable report and source were not edited.
The first complete attempt and the later failed engineering counterexample
are preserved. All four final jobs were refrozen and fully rerun after
the fixes under the same original budget; no candidate results were reused.

The cumulative source commit also includes previously uncommitted R20-R23
modules. R20/R21 found no further improvement in their declared spaces;
the new R22 rerun completed its declared space and delivery. The earlier
R22 delivery-blocked attempt and R23 input-timeout BLOCKED result remain
historical failures. R23 processed zero candidates, not a no-improvement
result.

This is conditional archived-component research. Saved mixed heights,
the 0.81-degree half-angle/direct-AreaTarget protocol and temporary mask
are not confirmed official rules; EOP ends in 2019 while the scenario is
in 2027. Official readiness is UNRESOLVED and official score is null.
There is no new whole-constellation STK validation, native activation or
experimental Git write. K12 and all previous outcomes remain unchanged.

Original delivery:
`G:\gpt-file\Codex\outputs\bd-fmb\round24\20261101T121155_offline`.
The all-exits observation and external Chinese summary live under the
matching `G:\fmb666\work\round24` directory. Some failed/preparation logs
remain only in original work and are indexed rather than fully re-exported.

A fresh clone does not contain the local input ZIP, matrix, historical
deliveries or same-machine runtime needed for scientific replay. This
commit preserves the 142 newly added source Git blobs as the frozen raw
bytes; use `core.autocrlf=false` when checking out those new files. The
existing parent commit already normalizes line endings for 41 older
consumer files and two older evidence JSON files; their content is
unchanged and this commit does not rewrite them. A checkout alone therefore
does not reproduce every historical raw-byte identity. The original
consumed-source ZIP remains the authoritative frozen execution snapshot.
