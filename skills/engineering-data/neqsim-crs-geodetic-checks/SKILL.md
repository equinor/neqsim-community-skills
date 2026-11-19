---
name: neqsim-crs-geodetic-checks
calculation_basis: "screening"
version: "1.0.0"
description: "CRS and datum checks for map, survey and layout data: explicit, provenance-recorded transforms (equinor/geodetic-engine, else pyproj with the same rules); named operations checked against their area of use; swapped lat/lon, degrees-as-metres and non-RFC 7946 GeoJSON; datum-ambiguity shift; grid convergence, scale factor and grid against geodesic route length. USE WHEN: positions, routes or distances come from maps, surveys or GIS."
last_verified: "2026-11-15"
requires:
  python_packages: [pyproj]
  java_packages: []
  env: []
  network: []
---

# CRS and Datum Checks

Use this skill whenever coordinates move between systems: map layers, survey files, well headers, seismic grids, GeoJSON exports and layout drawings. On the Norwegian shelf, the same UTM 31N numbers read as ED50 or as WGS 84 land about 230 m apart, and grid lengths differ from true lengths by up to about 400 ppm. Both errors pass silently through a calculation unless something checks them.

The engine is [equinor/geodetic-engine](https://github.com/equinor/geodetic-engine) (Apache-2.0, PROJ 9.9) when it is installed, otherwise pyproj under the same rules:
- A datum change must name its operation when the candidates disagree by more than 1 cm.
- Ballpark transformations are refused.
- A missing grid is reported.
- The PROJ pipeline that ran is recorded.

On both engines this skill also refuses a named operation whose EPSG area of use does not contain the points.

## When to Use

- Positions from a GIS service, map viewer, GeoJSON, survey or well-header table feed a calculation (SURF layout, step-out distance, clearance to existing lines, well placement, seismic fence).
- The datum or CRS of a source is not stated or is ambiguous ("UTM 31", "ED50?").
- A pipeline, flowline or umbilical length comes from a map, and grid against true length matters.
- Data must go to WGS 84 or ETRS89 with an auditable operation, for example an OSDU record or a regulator submission.

## Inputs

Config for `<python> -m crs_checks check config.json`:

- `points`: `[{name, x, y}]` in `crs`. x is the easting or longitude and y the northing or latitude, always in that order.
- `crs`: the stated CRS (`EPSG:23031`, a WKT string, ...). If it is not stated, leave it out and give `datum_candidates`. The run is then blocked until a person confirms the CRS.
- `target_crs` and `operation`: a named datum transformation (`EPSG:1613`), or `best` (most accurate available, recorded as an automatic choice).
- `datum_candidates` with optional `operations` per candidate: readings of the same numbers to compare. `shift_tolerance_m` defaults to 5.
- `route`: `{crs, points}` for grid against geodesic length.
- `geojson`: files to check against RFC 7946.
- `out_dir`.

One-off: `<python> -m crs_checks transform SRC DST X Y --operation EPSG:n` prints the coordinates with provenance, or exits with 2 and the reason.

## Outputs

`crs_check_evidence.v1` (`crs_check_evidence.json`), always `unverified`:
- `status`: `ok`, `attention` (findings to resolve before use) or `blocked`.
- `engine`, `findings`, `missing`.
- `results`:
  - `area_of_use`: CRS area, points outside it, lon/lat on the CRS datum;
  - `transform`: points, operation, accuracy in metres, PROJ pipeline, candidates, warnings;
  - `projection_factors`: meridian convergence and scale factors at the first point;
  - `datum_sensitivity`: per-candidate operation and the pairwise shift in metres;
  - `route_lengths`: grid, geodesic, difference in metres and ppm.

## Engineering Method

1. **Area of interest.** The points' extent on their own datum (a conversion, no datum change) limits the candidate operations to those valid there, as PROJ intends.
2. **Operation choice.** All exact candidates are evaluated. If they disagree by more than 1 cm, the call fails with the list (name and accuracy) until one is named. A named operation is matched by EPSG code and checked against its area of use. `best` takes the most accurate available operation and says so.
3. **Plausibility.**
   - Points are checked against the CRS area of use.
   - Geographic values that fit only when swapped are flagged as reversed lat/lon.
   - Degree-sized values in a projected CRS are flagged.
   - UTM eastings outside 160–840 km and negative northings are flagged.
   - GeoJSON with a `crs` member or values outside lon/lat ranges is flagged.
4. **Datum sensitivity.** The same numbers are read in each candidate CRS and taken to WGS 84. The pairwise geodesic shift is how much the unconfirmed datum can move a position.
5. **Projection factors and lengths.** `Proj.get_factors` gives meridian convergence and scale. A route's grid length is compared with its geodesic length on the CRS ellipsoid. In UTM the difference is about −400 ppm near the central meridian and positive near the zone edge.

## Python Usage Pattern

```python
from crs_checks import transform, datum_sensitivity, route_lengths

wgs = transform([(2.610422, 60.290422)], "EPSG:4230", "EPSG:4326", operation="EPSG:1613")
print(wgs.coordinates, wgs.operation, wgs.accuracy_m)        # ED50 to WGS 84 (24), 1 m
print(datum_sensitivity([(478460, 6683976)], ["EPSG:23031", "EPSG:32631"])["max_shift_m"])   # about 230 m
print(route_lengths([(481000, 6683000), (497000, 6697000)], "EPSG:32631")["difference_m"])
```

## Validation Checklist

- [ ] Every transformed position records operation, accuracy and pipeline; no unnamed datum change.
- [ ] `datum_sensitivity` was run for any source whose datum is not stated, and the datum was confirmed when the shift exceeds the tolerance of the use (clearances, slots, crossings).
- [ ] No point outside the CRS area of use, and no swapped-axis finding left unresolved.
- [ ] Route lengths state grid or geodesic.
- [ ] Depth sign and vertical datum (MSL, LAT, TVDSS) are handled separately; this skill is horizontal only.

## Common Mistakes

- Reading `[lat, lon]` pairs (common in JSON and spreadsheets) as `[x, y]`.
- Treating "UTM zone 31N" as a CRS: it is a projection; the datum (ED50, WGS 84, ETRS89) decides where the point is.
- Using the ED50 to WGS 84 operation for northern Norwegian waters (EPSG:1612, north of 62° N) on southern fields (EPSG:1613), or the reverse.
- Using map-grid lengths for pipeline quantities without the scale factor.

## Limitations

- Horizontal CRS only; vertical datums, epochs of dynamic datums and grid downloads are reported, not handled.
- With pyproj the EPSG dataset is that of the installed PROJ. geodetic-engine pins PROJ 9.9 and needs Python 3.13; install it on purpose in an environment that can take its pyproj pin.
- Results are screening checks; positions used for construction need a surveyor's confirmation.

## References

- equinor/geodetic-engine (Apache-2.0): https://github.com/equinor/geodetic-engine and https://equinor.github.io/geodetic-engine/
- PROJ and pyproj: https://proj.org, https://pyproj4.github.io/pyproj/
- EPSG Geodetic Parameter Dataset (operations 1612 and 1613, ED50 to WGS 84 for Norwegian waters north and south of 62° N): https://epsg.org
- IETF RFC 7946, GeoJSON.
- Related skills: `neqsim-seismic-segy-reading` and `neqsim-seismic-structure-to-reservoir` (CRS hints of seismic and surfaces), `neqsim-subsea-equipment-placement` and `neqsim-surf-design-study` (positions and routes), `neqsim-well-trajectory-anticollision` (slot and offset positions).
