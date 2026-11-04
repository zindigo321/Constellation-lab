# ConstellationLab: Satellite Constellation Optimization for Global Coverage and Regional Revisit

This project addresses a satellite constellation design challenge from Dongyi Technology: improving global coverage and regional revisit performance. It uses **Python to generate and optimize constellations and STK 11 to build simulation models and validate their performance**. The intended workflow is:

```text
Satellite count -> Orbital parameters -> Simulation and evaluation -> Optimization -> Export
```

**Current status: R25-R28 research release.** A standalone generator supports integer satellite counts from 2 to 100. The R28 batch pipeline has passed diagnostic acceptance within a limited native STK workload on the same machine. This public release contains the generator, offline batch storage and statistics modules, and synthetic checks. Full 28-satellite validation on the official grids and the final competition submission are still pending. `official_score=null`.

Start with the [R25 generator](research/round25/README.md) and [R28 offline modules](research/round28/README.md). The [stage status document](docs/r25-r28-status.md) records validation scope and timing limitations. Those linked historical documents retain their original language. The sections below preserve the original project plan; planned interfaces and targets should not be read as completed capabilities. The legacy `src.cli` is not the new general-purpose N-only entry point.

### Run the published standalone tools

From the repository root, using Python 3.11, the environment used for acceptance:

```powershell
# Generate a 28-satellite constellation without starting STK.
python -B research/round25/program/generate.py 28 --out work/generated/N28

# Run the published synthetic storage and integration checks without STK.
python -B research/round28/checks/store_counterexamples.py work/r28-store-checks
python -B research/round28/checks/synthetic_smoke.py --out work/r28-synthetic-checks
```

Each output directory must be new. The generator writes `orbits.csv`, `config.json`, and `COMPLETE.json`. Successful parameter generation requires exit code 0 and valid completion bindings. It does not establish coverage or revisit performance. The synthetic checks use fixture data and do not reproduce the native STK experiments.

## 1. Objectives and Deliverables

- Accept an integer satellite count `N`, where `1 < N <= 100`, and generate exactly `N` satellites with valid orbital parameters.
- Improve global coverage efficiency and revisit performance over the Yangtze River Delta for a fixed satellite count.
- Export altitude `h`, inclination `i`, right ascension of the ascending node `RAAN`, and argument of latitude `u` for each satellite at a common epoch in J2000.
- Deliver the algorithm, source code, operating instructions, and **a complete 28-satellite STK project with global coverage and regional revisit analysis**.
- Establish a Walker baseline, then investigate orbital plane, phase, and altitude changes under identical evaluation conditions.

Although the challenge background mentions reducing satellite count, the direct input is a specified `N`. The initial scope optimizes performance at fixed `N`; satellite count minimization is a separate problem. Attitude controller design, energy scheduling, communications scheduling, and comprehensive collision avoidance are outside the current scope.

## 2. Design and Simulation Conditions

| Item | Challenge specification / project interpretation |
| --- | --- |
| Satellites and orbits | Optical remote sensing satellites in circular sun-synchronous orbits, `e = 0` |
| Altitude | 500-700 km, defined relative to the mean Earth radius |
| Propagation | J2; J2 Perturbation in STK 11 |
| Propagation step | 30 s |
| Initial reference frame | J2000 |
| Simulation period | January 1, 2027, 00:00:00 to January 8, 2027, 00:00:00; seven days; time system pending confirmation |
| Payload | Linear pushbroom optical camera |
| Swath width | Specified as `15 * h / 530 km`; provisionally interpreted as `W(km) = 15 * h(km) / 530`, pending confirmation |
| Default attitude | Body +Z toward Earth's center, +X along the direction of motion, and +Y completing a right-handed frame |
| Along-track / cross-track field of view | 0.001622 degrees / 0.81 degrees; full-angle versus half-angle convention pending confirmation |
| Global coverage grid | 1 degree by 1 degree over the organizer's valid evaluation domain |
| Yangtze River Delta revisit grid | 0.1 degree by 0.1 degree; official boundary pending |
| Coverage analysis time settings | Recommended 10 s globally and 1 s regionally; configured separately from the 30 s propagation step |
| Imaging constraints | Ideal continuous geometric imaging, without energy, thermal, storage, communications, or weather constraints |

Do not add illumination, solar elevation, or other filters without a corresponding organizer requirement. Coarser grids may be used during search, but final results must be recomputed under the common evaluation conditions.

### Items to confirm before formal comparison

1. **Time system and Earth constants.** UTCG may be used provisionally if recorded as an assumption. Confirm the official epoch convention, mean Earth radius, and J2 parameters before formal evaluation.
2. **Field of view and swath width.** STK 11 rectangular sensor angle properties use half-angles. A planar approximation with a cross-track half-angle of 0.81 degrees at 530 km gives `2h * tan(0.81 degrees)`, approximately 15 km. This supports an interpretation but does not replace official confirmation. Verify along-track and cross-track directions through ground projection rather than relying on Horizontal / Vertical property names alone.
3. **Regional boundary and valid global points.** Obtain the official polygon or point set. Temporary regions are for debugging. All candidates must use the same fixed evaluation points; do not change the denominator based on a candidate's actual coverage or remove uncovered points.
4. **Interfaces and scoring.** Confirm the official input/output format, evaluated satellite counts, treatment of interval boundaries, and invalid-point rules. Counts of 30, 60, and 100 are example test cases; the 28-satellite engineering deliverable is a separate requirement.

## 3. Metrics and Optimization Objectives

| Metric | Definition | Direction | Score weight |
| --- | --- | --- | --- |
| `T90` | First time cumulative coverage reaches 90% of valid global grid points | Minimize | 28 |
| `T100` | First time every valid global grid point has been covered at least once | Minimize | 12 |
| `Tavg` | Mean of all valid revisit gaps over the Yangtze River Delta | Minimize | 42 |
| `Tmax` | Maximum valid revisit gap over the Yangtze River Delta | Minimize | 18 |

Cumulative global coverage is the number of valid points observed at least once divided by the total number of valid points. Repeated observations do not increase the count. Use the specified point-count convention rather than substituting area weighting.

For **each grid point**, merge overlapping or touching access intervals from all satellites, then calculate the gaps between consecutive merged intervals:

```text
gap = start of next access - end of previous access
```

Pool the valid gaps across all points before calculating the mean and maximum. Do not average per-point means directly, or assume that STK's built-in revisit reports implement the challenge's exact convention.

The documented score for one satellite-count case is:

```text
S_N = 28 * T90_best / T90 + 12 * T100_best / T100
    + 42 * Tavg_best / Tavg + 18 * Tmax_best / Tmax
```

Here, `*_best` denotes the best metric among valid competing submissions with the same satellite count. These values are unknown during development. Internal optimization records the four raw metrics and compares them against a fixed baseline. A weighted internal loss may use weights of `0.28 / 0.12 / 0.42 / 0.18`; **an internal objective value is not an official score**. Retain Pareto candidates where the metrics have meaningful tradeoffs.

Record exceptional cases explicitly:

- If 90% coverage is not reached within seven days, both global coverage terms receive zero. If 90% is reached but 100% is not, only the `T100` term receives zero.
- Store unreached thresholds as missing values with an explicit failure status. Do not report seven days as a measured threshold time.
- If required regional points have fewer than two valid accesses, retain them and apply the challenge's applicable zero-score rule; do not discard them to improve the reported mean.
- Incorrect satellite counts, invalid parameters, propagation failures, or invalid formats make the corresponding case invalid.
- Record the gap from the simulation start to the first access and from the final access to the simulation end separately. Their inclusion in official revisit statistics remains pending confirmation.

## 4. Software and Environment

| Software / tool | Intended use | Environment policy |
| --- | --- | --- |
| Windows + STK 11 | J2 propagation, payload modeling, access and coverage validation, project export | Record the exact STK 11.x version |
| Python | Constellation generation, optimization, statistics, and export | Main implementation language |
| NumPy and SciPy | Numerical calculations, parameter search, and optimization | Add as required by the algorithms |
| pandas and Matplotlib | Data preparation, coverage curves, and comparisons | Analysis and reporting |
| comtypes or pywin32 | Python-to-STK COM automation | Select and record a tested bridge |
| Git / GitHub Desktop | Version control and collaboration | Review changes before committing and pushing |

Prefer an existing working Python environment. The original setup plan suggested trying Python 3.10 if a new environment was needed; compatibility with the installed STK version and COM bridge must be tested rather than assumed. The published standalone R25/R28 subset was accepted on Windows with Python 3.11 and uses only the standard library. Lock dependencies after successful environment testing and record Python/STK versions and architecture.

The planned STK 11 automation route uses `STK11.Application`, `Personality2`, and the Object Model / Connect interfaces. See the [STK 11.4.1 training manual](https://help.agi.com/stk/11.4.1/LinkedDocuments/Printed%20Manual%20-%20Comprehensive.pdf).

Check whether the license supports Coverage Definition / Figure of Merit and the required automation features. If coverage modules are unavailable, start with sensor Access calculations for a small set of ground points, then assess full-grid cost and available licensing. Parameter generation must remain independently runnable without starting STK.

## 5. Constellation Design and Optimization

### Step 1: Establish a reproducible baseline

The original baseline plan uses 28 satellites in seven orbital planes with four satellites per plane. Save altitude, sun-synchronous inclination, RAAN, and phase parameters. The challenge describes a reference constellation reaching 90% coverage in four days and full coverage within a week, but does not supply its complete initial parameters. **That description is a reference to reproduce, not a measured result from this project.**

Uniform Walker-Delta candidates can use the following parameterization, with angles in degrees:

```text
N = P * S
RAAN_p = RAAN_0 + 360 * p / P
u_(p,s) = u_0 + 360 * s / S + 360 * F * p / N
p = 0, ..., P-1; s = 0, ..., S-1; F = 0, ..., P-1
```

Enumerate plane count `P` and phase factor `F`, then search altitude `h`, global RAAN offset `RAAN_0`, and global phase `u_0`. Describe alternative plane distributions as separate constellation families instead of mixing their definitions with Walker-Delta.

### Step 2: Enforce sun-synchronous constraints and support different N

Derive inclination from altitude using the J2 nodal precession relationship. Do not keep an arbitrary inclination fixed while changing altitude from 500 to 700 km, or search altitude and inclination independently. Use `a = R_mean + h` for circular orbits, calculate inclination with the common Earth constants, and validate nodal precession in STK.

For equal-population orbital planes, enumerate factors of `N`. For other counts, support custom unequal-population constellations: assign `floor(N/P)` satellites to each plane, distribute the remainder, and design the phases separately. This extension does not directly inherit the standard Walker phase formula. Always verify that the total satellite count equals `N`.

### Step 3: Combine coarse screening with detailed evaluation

1. Generate uniform baselines and candidates with different `P / F / h` values. Start with interpretable enumeration and bounded searches.
2. Use an STK-calibrated approximation of J2 secular perturbations, Earth-fixed transformations, and imaging-strip geometry for fast screening. Include the evolution of RAAN and orbital phase; compare representative trajectories and access windows before relying on the approximation.
3. Fix the screening budget and send promising candidates to STK 11 for detailed validation. Record ranking agreement between the approximation and STK.
4. After the basic workflow is stable, consider differential evolution or local phase perturbations. Separate discrete choices from continuous parameters; multi-objective methods are a later option.
5. If uniform designs provide insufficient improvement, introduce per-plane RAAN offsets and nonuniform phases. Defer multiple-altitude shells to control the number of variables.

Check orbital validity and regional revisit feasibility before comparing performance. Fix random seeds and candidate or runtime budgets, and cache repeated parameter evaluations. Run early STK automation serially to avoid contention for the same application instance.

## 6. STK 11 Modeling and Python Integration

The planned modeling workflow is:

1. Connect to or start STK 11 from Python and create a scenario with the common epoch and time interval.
2. Create satellites from the exported parameters. Set J2000, J2 Perturbation, a 30 s propagation step, and circular initial orbits. Convert altitude to semimajor axis using the agreed mean Earth radius.
3. For circular orbits, fix argument of perigee to zero and set initial true anomaly equal to `u`. Preserve argument of latitude, and align the orbital element conventions and initial-state mapping between Python and STK.
4. Configure the specified attitude and rectangular pushbroom sensor. Verify boresight, sensor installation, and along-track/cross-track ground projections.
5. Create global and regional Coverage Definitions using the camera Sensors as assets. Export grid coordinates and access intervals for independent metric calculation in Python.
6. Save the project and associated satellite, sensor, and region files. Close and reopen it to check completeness and reproducibility.

For rectangular sensors, `HorizontalHalfAngle` and `VerticalHalfAngle` correspond to the sensor XZ and YZ planes; their ground directions depend on installation attitude. See the [STK 11.4 rectangular sensor interface](https://help.agi.com/stkdevkit/11.4.0/Content/DocX/STKObjects~IAgSnRectangularPattern.html).

**Time accuracy requires separate validation.** A narrow along-track field of view can produce accesses shorter than one second. Propagation step, analysis time settings, report sampling, and event-solver accuracy are distinct settings. Testing visibility only once per second can miss events. Check STK access search, interpolation, and convergence settings, and perform convergence comparisons on representative accesses. Keep internal precision experiments separate from the required final configuration. See the [STK access computation settings](https://help.agi.com/stk/content/stk/CompSettings.htm).

## 7. Original Implementation Roadmap

The original plan allocated approximately six weeks without fixed calendar dates. This is a planning reference, not a statement of current completion or a remaining-time estimate. The first two weeks prioritized a 28-satellite constellation that could be generated, imported, and evaluated.

| Stage | Suggested time | Main work | Acceptance target |
| --- | --- | --- | --- |
| Requirements and environment | Week 1 | Confirm boundaries, sensor angles, time and scoring conventions; check licensing; export one satellite access | Environment record, open questions, and a working automation connection |
| Baseline and parameter interface | Week 2 | Generate the 28-satellite 7-by-4 baseline; validate input and export orbits; import into STK | Exactly 28 valid rows, a reopenable project, and initial statistics |
| Common evaluation workflow | Week 3 | Build grids, merge accesses, calculate four metrics, and check timing accuracy | Reproducible results and agreement with sampled STK accesses |
| Constellation search | Week 4 | Enumerate planes, phase, altitude, and global offsets; screen and validate candidates | Baseline comparisons showing gains and tradeoffs |
| Multiple counts and robustness | Week 5 | Test 30/60/100, non-divisible counts, boundaries, invalid inputs, and repeated seeds | Valid output for different N, with documented cost and limits |
| Engineering and documentation | Week 6 | Select a 28-satellite design, recompute final metrics, and prepare independent execution | Complete STK project, results, instructions, and demonstration material |

Work may be divided among algorithms, STK simulation, and data/documentation. Keep a runnable version at each stage. If time is limited, prioritize the evaluation workflow and bounded search before nonuniform constellations, multiple shells, or complex multi-objective optimization.

## 8. Repository Layout and Interfaces

The current repository separates historical research code from the newer published standalone tools:

```text
repository/
|-- README.md
|-- requirements-smoke.txt       # Dependencies for the historical smoke environment
|-- configs/                    # Per-round configurations
|-- src/                        # Historical implementation and round-specific modules
|-- tools/                      # Execution, inspection, and export utilities
|-- tests/                      # Regression and boundary checks
|-- checkpoints/                # Selected historical candidate snapshots
|-- docs/                       # Round reports and stage status
`-- research/
    |-- SOURCE_MAP.json         # Source identity and provenance
    |-- round25/program/        # Standalone N-only generator
    `-- round28/
        |-- src/                # Offline batch storage and statistics modules
        `-- checks/             # Published synthetic checks
```

The internal orbit table uses:

```text
sat_id, h_km, i_deg, raan_deg, u_deg
```

Store the epoch, reference frame, Earth constants, time system, and fixed eccentricity in an accompanying configuration. Normalize periodic angles to `[0, 360)` and validate inclination separately. Add an adapter when the official interface is confirmed; the internal CSV is not an official submission specification.

The original design proposed the following interfaces. **These remain illustrative planning examples, not the published general-purpose entry points:**

```powershell
# Planned general-purpose generation interface.
python -m src.cli generate --n 28 --output results/n28/orbits.csv

# Planned STK evaluation interface.
python -m src.cli evaluate --input results/n28/orbits.csv --engine stk11

# Planned optimization interface.
python -m src.cli optimize --n 28 --seed 42 --output results/n28_search
```

Use the R25 command near the top of this README for the released N-only generator. The legacy `src.cli` retains its historical behavior.

## 9. Validation and Final Delivery

Keep satellite count, point set, simulation period, payload, propagation model, and numerical settings fixed when comparing designs. Save configurations, orbital parameters, random seeds, runtime, software versions, four raw metrics, and exceptional states. Label approximate evaluations separately from native STK results.

The following is a template for formal results. Populate it only after the required simulations; it does not represent existing validated measurements.

| N | Design | T90 | T100 | Tavg | Tmax | Valid revisit point fraction | Runtime | Conditions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 28 | Uniform 7-by-4 baseline | Pending | Pending | Pending | Pending | Pending | Pending | Common STK 11 settings |
| 28 | Optimized candidate | Pending | Pending | Pending | Pending | Pending | Pending | Identical to baseline |

Final-delivery acceptance targets:

- [ ] Complete source code and dependency instructions; the generator accepts different N without manual per-satellite editing.
- [ ] Valid satellite counts, orbital ranges, sun-synchronous constraints, units, and epoch.
- [ ] A complete 28-satellite STK project and all associated files, verified after relocation and recomputation.
- [ ] Global cumulative coverage curves, T90/T100, regional revisit distributions, and Tavg/Tmax backed by raw data.
- [ ] Required engineering and scale checks, updated to match the official evaluation cases.
- [ ] Baseline and candidate comparisons under identical conditions, including tradeoffs and unmet targets.
- [ ] Algorithm documentation covering variable definitions, plane and phase design, optimization, and the mapping to STK parameters.
- [ ] Large temporary caches excluded from ordinary commits; required large project files delivered using an appropriate repository or artifact mechanism.

These are final acceptance targets. The R25 generator and R26-R28 diagnostic results do not close the full checklist. Current status remains:

```text
full_N28_admission = CLOSED
formal_full_grid_validation = NOT_RUN
official_readiness = UNRESOLVED
official_score = null
```

R28 reduced the D workload's Store file count from 6,242 to 101, approximately 61.8 times fewer files. This does not establish an equivalent runtime improvement; the new D run did not demonstrate a shorter total runtime. Query plans and snapshots still have materialization costs. The initial timing sample was taken out of the required order; a disclosed 120-second budget deduction is not a proven upper bound on unmeasured preparation time.

The published subset does not contain the complete native STK collector, full engineering project, machine resources, or raw native experimental data. Passing the public synthetic checks does not reproduce the native experiments or validate official performance.

## 10. Version Control and Manual Submission

Stage releases include source code, configurations, tests, and execution instructions. Raw data, work caches, local handoff files, generated run artifacts, and STK projects are excluded from ordinary Git commits. Execution and acceptance claims must refer to the corresponding evidence.

Review, stage, commit, and push changes manually. In GitHub Desktop, use **File -> Add local repository**, select the local project folder, inspect the README diff, and enter a commit message before committing and pushing.

For a README-only change, the equivalent Git commands are:

```powershell
git diff -- README.md
git add README.md
git commit -m "docs: translate project README into English"
git push origin main
```

These commands are provided for manual use; review the current branch and changes before running them.

Repository: [zindigo321/fxyd6](https://github.com/zindigo321/fxyd6).
