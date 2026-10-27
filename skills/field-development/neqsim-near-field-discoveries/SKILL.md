---
name: neqsim-near-field-discoveries
calculation_basis: "screening"
version: "0.1.0"
description: "Inventory and map of the discoveries, fields, evaluation plans and hosts around a target on the NCS (Sodir) and in Brazil (ANP): common development-stage ladder, public volumes and resource class, concept text, nearest hosts, joint-development clusters, CSV/GeoJSON export. USE WHEN: a field-development, tie-back, bid or area study needs the best public knowledge of what is near the target, what is planned there, and a map of it (e.g. around a Santos or Campos discovery)."
last_verified: "2026-10-27"
requires:
  python_packages: ["matplotlib (map only)"]
  java_packages: []
  env: []
  network: ["Sodir DataService (optional; fetch is injectable)", "ANP GeoServer via neqsim-anp-open-data (optional; cached offline)"]
---

# Near-Field Discoveries

A field-development evaluation is only as good as its knowledge of the neighbourhood: which discoveries lie
near the target, which are already planned or approved, which are written off, who operates them, how big
they are, and which host could serve several of them. This skill builds that picture from open data and
draws it, for the Norwegian Continental Shelf (Sodir) and for Brazil (ANP).

It is a screening inventory. It does not hold licence, partner or reserve data that is not public, and it does
not decide a concept.

## When to Use

- A discovery, prospect or block needs "what is near me?" with status, operator, volumes and plans.
- A tie-back, stand-alone or area-development comparison needs the neighbouring discoveries that could
  share a host or change host ullage.
- A bid or concept study needs a map for a report (`neqsim-brazil-offshore-infrastructure-market`,
  `neqsim-psc-bid-economics-screening`, `neqsim-concept-longlist-shortlist-screening`).
- A task asks for a map of discoveries, fields, evaluation-plan areas, hosts and pipelines around a point.

## Inputs

- Target `(lon, lat)` in WGS84 / SIRGAS 2000 degrees, its name, and its source. A block centroid is not a
  well position: say so.
- Radius in km (default 100 to 150 for tie-back screening; up to 250 km for pre-salt hosts).
- Country: `NO` (Sodir) or `BR` (ANP). Both can be combined in one inventory for a cross-border view.
- Optional: aliases (operator names for Brazilian discovery wells), volumes from a non-ANP source,
  bathymetry grid, extra host lists, and extra records of kind `prospect` (for example GeoX prospects or a
  user-supplied prospect list) that are drawn as triangles and counted apart from discoveries.

## Outputs

- `Inventory.records`: discoveries, fields and evaluation areas inside the radius, nearest first, each with
  `stage`, `status_raw`, `hc_type`, `discovery_year`, `operator`, `distance_km`, `bearing`, volumes with basis,
  `plan_note`, `plan_flags`, nearest hosts, source URL and an explicit `gaps` list.
- `Inventory.summary()`: counts and volume roll-up per stage; `area_clusters()`: open discoveries within
  15 km of each other (joint-development candidates).
- Files from `Inventory.write(folder)`: CSV, JSON, GeoJSON (loads in QGIS, ArcGIS and Omnia Maps as an
  overlay) and a Markdown note.
- `plot_near_field(inv, "map.png", bathymetry=grid)`: map with stage colours, outlines, evaluation areas,
  hosts, pipelines, radius rings, labels and sources.

## Stage ladder

| Stage | Sodir (Norway) | ANP (Brazil) |
| --- | --- | --- |
| `producing` | Producing | Field with `etapa` Produção |
| `in_development` | Approved for production | Field with `etapa` Desenvolvimento |
| `in_clarification` | Production in clarification phase, likely but unclarified | Candidate inside a running discovery-evaluation plan (PAD, `geoanp:pad`) |
| `not_evaluated` | Production not evaluated | Hydrocarbon-bearing wells outside fields and plans |
| `unlikely` | Production is unlikely, Shut down | Field `Em Devolução`, or inside a returned block |
| `unknown` | Included in other discovery (resolved from the parent when possible) | Inside an evaluation plan that has ended: outcome not public |

## Python Usage Pattern

```python
from near_field_discoveries import (fetch_ncs_near_field, fetch_anp_layers, brazil_records,
                                    hosts_from_production_units, near_field, plot_near_field)

# Norway: discoveries (status, volumes, concept text), fields, facilities, pipelines
data = fetch_ncs_near_field((24.0, 73.3), 120)
inv = near_field((24.0, 73.3), 120, data["records"], name="Target", hosts=data["hosts"],
                 pipelines=data["pipelines"], log=data["log"])

# Brazil: wells + fields + evaluation plans + blocks + production units (cached, truncation-logged)
layers, log = fetch_anp_layers((-42.5, -25.0), 150, task / "references/anp")
recs = brazil_records(layers, aliases={"1-BRSA-1234-RJS": "Operator name"})   # name from a press release
inv = near_field((-42.5, -25.0), 150, recs, name="Target", hosts=hosts_from_production_units(layers["production_units"]),
                 layers={"blocks": layers["blocks"]}, log=log)

paths = inv.write(task / "step2_analysis")            # csv, json, geojson, md
plot_near_field(inv, task / "step2_analysis/near_field_map.png", bathymetry=etopo_grid)
```

`examples/near_field_study.py` does all of this from the command line (`--country NO|BR --lat --lon --radius --out`).
Add `--bathymetry` for ETOPO contours (needs `neqsim-anp-open-data`).

## What the sources give, and what they do not

| Item | Norway (Sodir) | Brazil (ANP) |
| --- | --- | --- |
| Discovery names | Yes (`dscName`) | **No**: the discovery well name is used; add `aliases` from an operator source |
| Status and stage | `dscCurrentActivityStatus` | Reconstructed from wells, field polygons, PAD polygons and returned blocks |
| Volumes | Recoverable oil, gas, NGL, condensate, oe and resource class (7008) | **None public**; supply `known_volumes` with its own source |
| Concept or plan | Description text (7001), often states stand-alone or tie-back; flags are extracted | PAD polygon, dates and block `NUM_DESCOB`; no concept text |
| Outline | Polygon | Position from wells; polygons only for fields, PAD, blocks |
| Hosts | Facilities (in service or planned) | Production units with positions (`geoanp:unidade_de_producao`) |
| Pipelines | Sodir 6100 | ANP export and transport lines (`neqsim-anp-open-data`) |

- ANP's PAD status code (`IN_PL_ATIV`) is not documented in the layer; the record keeps the raw code and
  decides "running" from the end date only.
- A Brazilian candidate is a cluster of hydrocarbon-bearing exploratory wells (`DESCOBRIDOR`, `PORTADOR`,
  `PRODUTOR SUBCOMERCIAL`, `EXTENSÃO`) more than `field_buffer_km` (default 3 km) from any field outline, joined
  at `link_km` (default 5 km). The position is the median well position and is labelled approximate when it
  rests on more than one well.
- Sodir plan flags (`stand-alone`, `tie-back`, `host:<name>`, `pdo`, `joint-development`, `no-plans`) are text
  matches. Read the `plan_note` before using them.

## Engineering Method

1. State the target position, datum, source and radius. If only a block is known, say that the block centroid
   is used.
2. Read the data. Keep the log of every read; **a read that reaches its feature limit is `truncated` and must be
   repeated with a smaller radius**. Offline runs reuse cached files and say so once.
3. Build records and the inventory. Open the summary first: how many producing, approved, planned, unplanned and
   written-off objects are within the radius, and how far the nearest of each is.
4. Look at the stage `in_development` and `in_clarification` objects: they decide host ullage, shared
   infrastructure and timing for the target. Hand them to `neqsim-reservoir-facility-value-chain` or the
   host-capacity agents with their dates.
5. Look at `area_clusters`: open discoveries close to each other and to a host may justify a joint
   development or a trunk line instead of separate tie-backs. Ownership and licence boundaries are not tested:
   check them with `neqsim-ncs-ownership-equity` or the ANP concession map.
6. Draw the map. State on the figure what the marker size, hatch and colours mean (the function does this).
7. Document every gap: unpublished volumes (Brazil), missing PDO text, unknown host ullage, truncated reads.

## Validation Checklist

- [ ] Target position, datum and source stated; block centroid labelled as such.
- [ ] Every read logged with feature count and `truncated`; none reported as complete if truncated.
- [ ] Stage ladder applied from the source status, not from a name or an assumption.
- [ ] Volumes shown only where a source publishes them, with the basis; none invented for Brazil.
- [ ] Brazilian discovery names are either the well name or a user alias with its source.
- [ ] Map legend, scale (radius rings), sources and the screening note are on the figure.
- [ ] Gaps and the human-review requirement are in the report.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Producing field listed as a discovery | Included-in-field discovery counted twice | Use `kind` and stage; fields come from the field layer |
| Brazil: no discoveries returned | Radius too small or wells inside field buffers | Increase `radius`, reduce `field_buffer_km`, check `truncated` |
| Brazil: a developed field's wells appear as a new discovery | Field outline generalised or missing | Check the fields layer read and its `truncated` flag |
| Sodir distance to a polygon looks large | Centroid used instead of the outline | The inventory uses the outline distance (0 inside) |
| Evaluation plan treated as a commercial declaration | PAD means evaluation, not approval | Keep the stage `in_clarification` and cite the plan end date |

## Limitations

- Public data only: operator plans, partner agreements, unpublished volumes and host ullage are not here.
- Brazilian discovery positions and stages are reconstructed; the operator's discovery notification governs.
- The map is plain lon/lat with latitude-corrected aspect, not a survey-grade projection; no coastline is drawn.
- Not a reserves statement, not a licensing or equity statement.

## Hand-offs

- Neighbours and nearest hosts to `tie-in-screening-agent`, `subsea-layout-screening-agent`,
  `surf-layout-design-agent` and `flow-assurance-engineer-agent`.
- Host-sharing clusters to `concept-longlist-shortlist-agent` and `enterprise-area-development-agent`.
- Volumes and resource class to `neqsim-resource-classification-screening`.
- Owners to `neqsim-ncs-ownership-equity`; Brazilian block terms to `neqsim-psc-bid-economics-screening`.
- GeoJSON to company map tools; enterprise users overlay it on Omnia Maps with `enterprise-omnia-pipeline-map-agent`.

## References

- Sodir FactMaps DataService (`factmaps.sodir.no/api/rest/services/DataService/Data/MapServer`, layers 6000, 6100, 7000, 7001, 7008, 7100, 7113), NLOD 2.0.
- ANP GeoServer (`geomaps.anp.gov.br/geoserver/ows`): `sisroc:pocos_gishub_db`, `sisroc:campos_gishub_db`, `geoanp:pad`, `sisroc:block_shp_geoanp`, `geoanp:blocos_exploratorios_devolvidos`, `geoanp:unidade_de_producao`.
