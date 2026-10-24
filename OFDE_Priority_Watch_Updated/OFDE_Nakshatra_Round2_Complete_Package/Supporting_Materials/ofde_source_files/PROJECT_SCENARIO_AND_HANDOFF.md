# OFDE Project Scenario & Handoff Summary

**Project:** Orbital Future Decision Engine (OFDE)  
**Team:** Fantastic 4  
**Track/theme:** software-only space debris / orbital traffic decision support  
**Event context from prior conversation:** Nakshatra Aerospace Hackathon 2026; final was described as an offline 12-hour event on 24 October 2026 at MITS Campus, Gwalior. Confirm current venue, timing, submission rules and exact rubric with the organizers.

## 1. The core idea
OFDE is intended as an uncertainty-aware decision-support layer after a satellite/debris close-approach alert. Conventional orbital analysis already includes tracking, propagation and conjunction assessment; OFDE should not claim to invent those. The proposed extension is to compare plausible future outcomes and candidate scenarios, expose uncertainty, consider more than one object and time horizon, and help a human reviewer understand trade-offs.

The concept tagline used in project material is: **“From one predicted future → to plausible futures.”**

## 2. Example scenario
A spacecraft (illustrative label `SAT-X`) and another catalogued object/debris (illustrative label `DEBRIS-07`) may pass close to one another. The system should:
1. Ingest orbital data and record source, epoch, retrieval time and object identifiers.
2. Propagate both object states using a documented, appropriate model.
3. Calculate relative position and separation over a declared time window.
4. Estimate time of closest approach (TCA), closest-approach distance and relative velocity.
5. If the uncertainty inputs and method support it, run an uncertainty ensemble and visualize a Future State Envelope.
6. Compare a no-action baseline with clearly described hypothetical candidate manoeuvre scenarios.
7. Check whether an alternative changes exposure to other objects and over multiple horizons (e.g., 24 hours, 7 days, 30 days) only if these calculations are implemented and validated.
8. Show assumptions, source data, run settings, limitations and evidence so a human can review the result.

## 3. Terms the team should understand
- **TLE (Two-Line Element set):** a compact format for orbital elements, designed to be used with compatible general perturbations models. It is not a direct sensor image and is not a perfect, timeless orbit.
- **GP / OMM:** General Perturbations data / Orbit Mean-Elements Message; OMM is a more modern message format that can carry GP orbital data.
- **SGP4:** a standard propagator commonly used with TLE/GP data. Do not use TLE elements with an unrelated propagation method without understanding the compatibility implications.
- **Epoch:** the reference date/time associated with the orbital data.
- **Propagation:** estimate an object's future state from an initial state and a motion model.
- **Conjunction:** a predicted close approach between two space objects.
- **TCA:** time at which the predicted separation is minimum within the analysis interval.
- **Miss distance / dCA:** minimum predicted separation at TCA.
- **Relative position:** difference between the two objects' position vectors.
- **Covariance:** a mathematical representation of uncertainty and correlation in a state estimate. Do not fabricate covariance if it is not supplied or justified.
- **Monte Carlo:** repeated simulations using samples from stated uncertainty assumptions. It does not automatically make results realistic; input distributions matter.
- **Future State Envelope:** OFDE's visualization/concept for showing a spread of possible future states. It is only as defensible as its model and uncertainty assumptions.
- **Decision sensitivity:** how often or how strongly the preferred scenario changes when assumptions/inputs vary.
- **Threat Transfer:** a project-defined way to discuss whether an action reduces one close-approach concern while increasing another. Define its exact formula before displaying it.
- **FEI (Future Exposure Index):** project-defined metric, not a universal aerospace standard. Document units, normalization, weights and limitations.
- **Δv:** change in velocity used to describe a manoeuvre scenario. A conceptual Δv is not a flight-qualified manoeuvre command.
- **TEME / ECI / ECEF:** coordinate frames with different definitions. Coordinate-frame and time conversions must be handled consistently.
- **TCA refinement:** numerical search to refine a minimum after an initial time grid; a numerical optimizer cannot fix wrong input data or wrong physics.

## 4. Useful base equations
These are standard mathematical definitions, not evidence that the code already implements them:

Relative position:
`r_rel(t) = r_2(t) - r_1(t)`

Separation:
`d(t) = ||r_rel(t)|| = sqrt(x_rel^2 + y_rel^2 + z_rel^2)`

Time of closest approach over the chosen interval:
`TCA = arg min_t d(t)`

Relative velocity:
`v_rel(t) = v_2(t) - v_1(t)`

Scenario distance change:
`Δd = d_alternative - d_baseline`

Finite-difference sensitivity for a metric `f` and parameter `x`:
`S_x ≈ [f(x + Δx) - f(x)] / Δx`

A covariance matrix is often written `P = E[(x - μ)(x - μ)^T]`. Monte Carlo sample statistics can summarize an ensemble, but only when sampling assumptions are stated. No single universal FEI formula exists; OFDE must define and test its own formula transparently.

## 5. Potential data sources
- **CelesTrak:** public GP/TLE-related catalog data and documentation.
- **Space-Track.org:** orbital data service requiring account access and compliance with its terms.
- **NASA Orbital Debris Program Office:** debris environment research and technical background.
- **ESA Space Debris Office / Space Environment:** debris and space-environment research.
- **Operator or mission data:** potentially higher-quality but not necessarily public or available to the team.
- **Synthetic fixtures:** useful for deterministic tests and offline demos, but must be visibly labelled synthetic/hypothetical and never passed off as live orbital data.

Record the source, object identifier, raw input, epoch, retrieval date/time, model/library version, settings and run ID. Do not assume public TLE data alone provides all covariance needed for operational collision probability.

## 6. How to improve accuracy responsibly
1. Use fresh, correctly identified data and preserve its epoch and provenance.
2. Use a propagation method compatible with the input format and document its version and assumptions.
3. Handle UTC/time standards, coordinate frames, units and transformations consistently.
4. Refine the TCA search and test convergence as the time step is reduced.
5. Compare results against trusted reference cases or independent implementations.
6. Model uncertainty only from defensible inputs; run ensemble-size/convergence checks if using Monte Carlo.
7. Validate baseline/no-action and zero-Δv behaviour; verify that a zero manoeuvre reproduces the baseline within numerical tolerance.
8. Evaluate other objects and horizons to test secondary consequences, if those features are implemented.
9. Keep reproducible run configurations and publish limitations alongside metrics.
10. Avoid claiming “more accurate than existing projects” without a fair benchmark, suitable reference truth, defined error metric and repeatable results. A stronger, defensible claim is that the prototype makes uncertainty and scenario trade-offs easier to inspect.

## 7. Honest prototype boundaries
The existing files describe a proposed architecture and presentation, not proof that every feature is implemented. Treat each capability as **implemented and tested**, **implemented but not validated**, **conceptual**, or **not implemented** after inspecting the actual code. Do not claim live telemetry, true collision probability, validated Monte Carlo, flight-qualified manoeuvre optimization, autonomous control, or superior accuracy unless supported by evidence.

Threat Transfer, FEI and Decision Sensitivity are project-defined concepts unless a specific authoritative standard is identified. Do not label FEI as an industry-standard risk score. OFDE is decision support; a human remains responsible for interpretation and decisions.

## 8. Suggested judge Q&A
**What problem are you solving?**  
We focus on the decision that follows a close-approach alert: helping a reviewer compare plausible outcomes and understand uncertainty and secondary effects, rather than replacing established tracking systems.

**Isn't conjunction assessment already available?**  
Yes. Our concept builds on established propagation and conjunction assessment. The intended contribution is the explainable scenario-comparison layer after an alert.

**What is a TLE?**  
A Two-Line Element set is a compact orbital-data format used with compatible propagation models such as SGP4. Its age and source affect prediction quality.

**Where does your data come from?**  
We plan to use documented public orbital data where available, plus labelled synthetic fixtures for repeatable offline tests. Each run should identify its source and epoch. We will not call fixtures live data.

**Does your tool detect debris physically?**  
No. It is software-only and consumes orbital data; it is not radar, telescope hardware or a physical debris detector.

**How do you calculate TCA?**  
Propagate both objects over a stated interval, calculate their separation as a function of time, then locate and refine the minimum. The implementation must be tested for convergence and boundary cases.

**What is Monte Carlo?**  
It repeatedly samples stated uncertain inputs and runs the model to examine the distribution of outcomes. It is only credible if its input distributions and convergence are justified.

**What is the Future State Envelope?**  
Our name for a visualization of the spread of possible future states under declared uncertainty assumptions—not a guarantee that every real future lies inside it.

**What is FEI?**  
Future Exposure Index is our project-defined summary metric. It is not a universal aerospace standard, and its formula, normalization, weights and limits must be documented.

**Can a manoeuvre solve one risk but create another?**  
Potentially, which is why multi-object scenario comparison is valuable. We should demonstrate this only with a reproducible calculation or a clearly labelled hypothetical example.

**Is the system autonomous?**  
No. It is decision support; a human reviews the assumptions and outputs. It does not issue spacecraft commands.

**How do you prove accuracy?**  
With reference cases, error metrics, time-step convergence, TCA stability, zero-manoeuvre checks, ensemble convergence and repeatable tests. We should not invent accuracy numbers before running those tests.

**How is this better than current systems?**  
We should not claim universally better accuracy. Our goal is to make uncertainty, alternative scenarios, multi-object effects and decision sensitivity visible in one explainable workflow. Any comparative performance claim needs benchmark evidence.

**What happens if the data are stale or missing?**  
The application should show the source and epoch, warn or reject unsuitable inputs, and avoid silently filling missing values.

**What if SGP4 or a data API is unavailable at the event?**  
Use a labelled offline fixture for the demo, disclose it clearly, and avoid pretending the result is live. The team should verify which dependencies are actually installed and working before the event.

**What is the biggest limitation?**  
Output quality depends on input data, propagation and frame/time handling, and defensible uncertainty assumptions. A student prototype is not flight-qualified operational software.

## 9. Team and event preparation
Prior project material names Fantastic 4 and identifies Anuj Singh as team leader, with Sarthak Gavnekar and Nitin Chherke as members; some deck variants list a fourth member differently (Dinesh versus Chirag Lalwani). Confirm the correct official member list before sharing/submission.

Before the event:
- Confirm exact official problem statement, rubric, time limits and allowed AI/data/tool rules.
- Select one final presentation deck and reconcile any conflicting team-name/member details.
- Run the application from a clean start on the target laptop, including offline mode.
- Prepare screenshots and test logs only from genuine runs.
- Keep the source data, test fixtures, run settings and limitations available for judges.
- Make a short demo: input → propagation → distance/TCA → uncertainty (if implemented) → scenario comparison → validation evidence → limitations.

## 10. Reference starting points
- CelesTrak: https://celestrak.org/
- Space-Track: https://www.space-track.org/
- NASA Orbital Debris Program Office: https://orbitaldebris.jsc.nasa.gov/
- ESA Space Debris: https://www.esa.int/Space_Safety/Space_Debris

Verify the exact documents and data versions used, and record access dates in the final research report.
