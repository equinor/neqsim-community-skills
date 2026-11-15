# neqsim-crs-geodetic-checks

Package `crs_checks`. It provides CRS and datum checks with explicit, provenance-recorded transformations. It uses [equinor/geodetic-engine](https://github.com/equinor/geodetic-engine) when installed, otherwise pyproj under the same rules.

```text
<python> -m crs_checks check config.json
<python> -m crs_checks transform EPSG:4230 EPSG:4326 2.6104 60.2904 --operation EPSG:1613
```

The evidence record is `crs_check_evidence.json` (`crs_check_evidence.v1`). See [SKILL.md](SKILL.md).
