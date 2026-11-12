---
name: neqsim-thermoml-experimental-data
calculation_basis: "screening"
version: "0.1.0"
description: "Fetch published experimental thermophysical data (density, VLE, viscosity, solubility, heat capacity) from the NIST/TRC ThermoML Archive by DOI with no login, flatten it into state points with expanded uncertainties, and score a NeqSim model against it with AAD, bias and within-uncertainty statistics. USE WHEN: validating or tuning an EOS or kij against measured data, finding measurements for a binary or mixture, or backing a benchmark with citable experiments rather than another model."
last_verified: "2026-11-12"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["trc.nist.gov"]
---

# ThermoML Experimental Data (NIST/TRC, no login)

The ThermoML Archive is the IUPAC-standard, XML-formatted collection of experimental thermophysical and
thermochemical data published in a set of journals (J. Chem. Eng. Data, Fluid Phase Equilibria,
J. Chem. Thermodynamics, Thermochimica Acta, Int. J. Thermophysics). It is the one open source of **measured**
data with stated uncertainties, which is what an EOS check needs. Complements
`neqsim-benchmark-reference-data` (model-based references such as CoolProp, GERG, IAPWS): use that skill for
reference-equation checks and this one when the claim must rest on experiments.

Access verified without login on 2026-11-12: `GET https://trc.nist.gov/ThermoML/<DOI>.xml` returns the document
(HTTP 200). The archive's search API (`/ThermoML-API/objects?query=...`) returned HTTP 503 during verification, so
treat search as best-effort and use DOIs as the primary key.

## When to Use

- A PVT, EOS or kij claim must be backed by published measurements (density, saturation, solubility, viscosity).
- You have a literature DOI and want the numbers as tidy state points instead of retyping tables.
- You need experimental uncertainty to judge whether a deviation is real or inside the measurement scatter.
- Do not use it for data not published in the covered journals, or as a substitute for company PVT reports.

## Inputs

An article DOI (or a compound or author query for best-effort search), the property to extract
(`property_contains`, for example `density`), and a model callable that maps one point (T, P, composition) to a value.

## Outputs

- `ThermomlReport` with citation, compounds (names, InChIKey, formula) and datasets.
- `DataPoint` rows: T [K], P [bara], mole fractions, property, unit, phase, value, expanded uncertainty.
- `ComparisonSummary`: `n_points`, `n_skipped`, AAD %, bias %, max deviation %, fraction within uncertainty, status.
- `ThermomlClient.provenance()`: URL, DOI, retrieval time and cache flag for `results.json` / `SOURCES.md`.

## Engineering Method

1. Get the DOI (archive browse page, literature search, or `ThermomlClient.search()` when the API is up).
2. `report = ThermomlClient(cache_dir=...).get_report(doi)`; inspect `report.compounds` and `report.datasets`.
3. Select points: `report.points(property_contains="density", phase_contains="liquid", component="methane")`.
4. Map ThermoML compound names to NeqSim component names (they differ, for example `octan-1-ol` vs `1-octanol`).
5. `compare_points(points, model, tolerance_pct)`; read `n_skipped` before trusting AAD, then judge against the
   reported expanded uncertainty, not only against the percentage tolerance.
6. Use at least three independent points or datasets before reporting PASS; record DOI and retrieval date.
7. For tuning, split the points: fit on one dataset, validate on another article.

## Python Usage Pattern

```python
from thermoml_experimental_data import ThermomlClient, compare_points
from neqsim import jneqsim

client = ThermomlClient(cache_dir=".thermoml_cache")
report = client.get_report("10.1021/je3001427")

def srk_density(point):
    if point.temperature_k is None or point.pressure_bara is None or not point.mole_fractions:
        raise ValueError("point lacks T, P or composition")   # skipped and counted, never silently PASS
    fluid = jneqsim.thermo.system.SystemSrkEos(point.temperature_k, point.pressure_bara)
    for name, x in point.mole_fractions.items():
        fluid.addComponent(name, x)
    fluid.setMixingRule("classic")
    jneqsim.thermodynamicoperations.ThermodynamicOperations(fluid).TPflash()
    fluid.initProperties()
    return fluid.getDensity("kg/m3")

summary = compare_points(report.points(property_contains="density"), srk_density, tolerance_pct=2.0)
print(summary.status, summary.n_points, summary.n_skipped, summary.aad_pct)
results_json_block = {"benchmark": summary.to_dict(), "sources": client.provenance()}
```

A complete runnable script is `examples/compare_with_neqsim.py` (offline fixture or a DOI).

## Validation Checklist

- [ ] `n_skipped` is zero or explained (missing composition, unmapped component name, flash failure).
- [ ] Units checked: `point.unit` matches the model unit; pressure already converted to bara, temperature in K.
- [ ] Phase of the experiment matches the phase the model reports (liquid mixture vs overall).
- [ ] At least three points, preferably two articles; DOI and retrieval date recorded.
- [ ] Deviation compared with the expanded uncertainty (`fraction_within_uncertainty`).
- [ ] The model tier is not the source of the reference (experiments are independent of any EOS).

## Common Mistakes

- Reading a PASS from `n_points=1`; always read `n_points` and `n_skipped`.
- Passing ThermoML names to NeqSim unchanged; map them and fail loudly on unknown components.
- Ignoring that some datasets give composition as molality, mass fraction or solubility rather than mole fraction;
  those land in `point.other` and need conversion before the model call.
- Comparing a saturated-phase property to an overall-mixture model result.
- Treating the expanded uncertainty as a standard uncertainty (it is a coverage-factor value, usually 95 %).
- Re-hosting archive files in a repository; fetch at run time and cache locally only.

## Limitations

- Anonymous access only; no bulk crawling (the client caps requests per instance and caches XML on disk).
- The search API is intermittently down (503 observed); DOI fetch is the dependable route.
- Coverage is limited to the archive's journals and years; absence of a DOI there is not absence of data.
- Terms of reuse: the archive is public without login, but the data originate from journal publications. Cite the
  article and NIST/TRC, and check publisher terms before redistributing the files.
- Only direct values are parsed; derived or fitted-parameter presentations (`ePresentation`) are returned as values
  without further interpretation.

## References

- NIST/TRC ThermoML Archive: <https://trc.nist.gov/ThermoML/> (schema: <https://trc.nist.gov/ThermoML.xsd>).
- Frenkel M. et al., "XML-based IUPAC standard for experimental, predicted, and critically evaluated
  thermodynamic property data storage and capture (ThermoML)", Pure Appl. Chem. 78 (2006) 541-612.
- Companion skills: `neqsim-benchmark-reference-data`, `neqsim-pvt-regression-characterization-factor`,
  `neqsim-fluid-quality-check`.
