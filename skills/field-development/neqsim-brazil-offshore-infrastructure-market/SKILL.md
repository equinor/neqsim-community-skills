---
name: neqsim-brazil-offshore-infrastructure-market
calculation_basis: "screening"
version: "0.1.0"
description: "Public data and helpers for Brazilian offshore (Santos and Campos pre-salt) gas export routes, processing plants, tariff status, third-party access, gas spec, oil marketing and host capacity, with explicit UNKNOWNs and source ids. USE WHEN: a Brazilian block or tie-back evaluation needs gas export, CO2 removal, wellhead net-back, host ullage or market context, and no numeric offshore tariff is public."
last_verified: "2026-10-14"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Brazil Offshore Infrastructure and Market

Use this skill to state what is public, what is UNKNOWN and how big the gas and host effects are, before they enter a Brazilian block evaluation. The packaged data is a snapshot of 2026-10-14 and goes stale.

## When to Use

- A Brazilian pre-salt block or tie-back needs gas export routes, plants, tariffs, gas quality or market context.
- A report must separate public facts from declared assumptions and list every UNKNOWN.
- A host FPSO's capacity must be checked for a tie-back, including a gas-handling limit.

## Inputs

- Declared gas CO2 (mol %), GOR (Sm3/Sm3), recoverable oil volume (MMbbl), export fraction, city-gate price.
- Host nameplate, host demand and, if known, the oil rate at which host compression limits (kbbl/d).
- Entry name for dataset lookups (for example `Rota 3`, `Bacalhau`).

## Outputs

- Dataset entries with value, unit, `source_id`, confidence (`official`, `company`, `press`, `estimate`, `declared`, `UNKNOWN`) and `as_of`.
- CO2 removal fraction, wellhead net-back, gas export revenue and share of oil revenue, host ullage and binding constraint.
- The explicit list of UNKNOWN entries to quote in the report.

## Engineering Method

Source-id convention: `INF-S<n>` for the infrastructure file and `MKT-S<n>` for the market file; `sources()` resolves each id to a URL. `null` value or confidence `UNKNOWN` is a gap, never zero.

### Routes and plants

- Rota 1 (Tupi to Mexilhao to UTGCA Caraguatatuba): 10 MMm3/d, about 359 km, since 2011. Rota 2 (to UTGCAB Cabiunas): 20 MMm3/d, 401 km, 24 in, since 2016 (official). Rota 3 (to Boaventura/GASLUB Itaborai): 18 MMm3/d, 355 km, commercial from Sep-Nov 2024.
- Rota 4A/4B (Cosan/Compass, about 21 MMm3/d): proposed, start year UNKNOWN, outside the EPE PDE 2035 base case. Planned export pipelines in EPE: Raia (16 MMm3/d, 2028; about 200 km to Cabiunas per the Equinor record) and SEAP (18 MMm3/d, 2030-32). Rota 5/6/SPA: UNKNOWN.
- Plants: UTGCAB Cabiunas 25.2 MMm3/d, Boaventura 21 MMm3/d (two modules), UTGCA capacity UNKNOWN, national fleet 120.1 MMm3/d (about 90 % Petrobras). Spare capacity per route and plant: UNKNOWN.
- Bacalhau FPSO: 220 kbopd, 530 MMscfd (about 15 MMm3/d) gas handling, no export pipeline in Phase 1 (associated gas re-injected); Phase 2 pipeline route UNKNOWN.

### Tariff status

- No numeric offshore escoamento, processing or transport tariff (Rota 1/2/3, UTG, NTS, TAG, TBG) is public; they are negotiated bilaterally or published on dynamic pages.
- The only number is the MME estimate that escoamento plus processing is 46 % of the delivered gas price (INF-S20, press). `wellhead_netback` applies it; it is not a tariff.
- City gate: EPE PDE 2035 shows 10.4-11.8 and 15.0-16.5 USD/MMBtu series (labelling ambiguous). Contracts are mostly indexed to Brent and/or Henry Hub.

### Third-party access

ANP approved a 45-day consultation on 2026-07-10 for a draft resolution on negotiated, non-discriminatory access to escoamento pipelines and processing plants; owner preference right ends 30 years after start-up. It covers pipelines and plants, not FPSO topsides. A tie-back to an FPSO is a commercial deal with the host, not regulated access.

### Gas specification

ANP Res 16/2008: CO2 max 3.0 mol %, total sulphur 70 mg/m3, H2S 10 mg/m3 (SE/S/CO), water dew point -45 C (SE/S/CO), Wobbe 46,500-53,500 kJ/m3. Res 982/2025 adds methane and ethane limits with a pre-salt waiver; ANP refused Petrobras's Itaborai waiver on 2026-10-02. Declared pre-salt gas CO2 is 6-34 mol %, so export needs membranes or similar and the base case re-injects. Use `co2_removal_fraction`.

### Oil marketing

No oil pipelines: oil leaves by FPSO and shuttle tanker. PPSA markets the Union profit oil; the contractor owns cost oil and its profit-oil share. ANP reference prices (Aug 2026, about 63-85 USD/bbl by field) and PPSA spot differentials (-7.4 to +4.7 USD/bbl to Dated Brent) are in the market file. Crude differential for a new block and shuttle-tanker cost: UNKNOWN.

### Market

Brazil produced 4.50 MMbbl/d oil and 215 MMSm3/d gas in Jul 2026 (pre-salt 82 % of boe). EPE PDE 2035: potential integrated-grid gas supply 128 to 169 MMm3/d, gross gas 299 MMSm3/d in 2035, net/gross about 42 % (derived). Gas export was about 8 % of oil revenue in the 2026-10-14 evaluation (5.9 USD/MMBtu net-back, 50 % exportable): a small upside next to oil.

### Regulation

Gas Law 14.134/2021 (entry-exit, ANP-approved tariffs), Lei 12.351/2010 (unitisation via AIP; Rodocrosita is flagged non-unitisable in the edital while Bacalhau is a shared deposit under an AIP), Repetro-Sped (Lei 13.586/2017), SBCE carbon market (Lei 15.042/2024, caps and price UNKNOWN), corporate tax 34 % (estimate, not verified).

### Host capacity

A host's oil nameplate is not its ullage. Gas handling or compression can bind first, so a tie-back competes for gas capacity. Pass the host-owner or process-model limit to `host_capacity_check`; without it the result is nameplate-only and says so. Public Bacalhau facts: 220 kbopd nameplate, 102.5 kbd in Jul 2026 (ANP bulletin, about 34 kbd per producer on the three producing wells reported).

## Python Usage Pattern

```python
import brazil_offshore_infrastructure_market as bim

bim.co2_removal_fraction(19.5)                      # 0.17 of gas moles to reach 3 mol %
nb = bim.wellhead_netback(11.0)                     # 5.94 USD/MMBtu (MME 46 % share)
up = bim.gas_export_upside(350, 325, 0.5, nb, oil_net_price_usd_bbl=65)   # about 8.5 % of oil revenue
chk = bim.host_capacity_check(220, 102.5, compression_limit_kbd=123, additional_demand_kbd=30)
bim.find("Rota 3", section="pipelines")             # entries with source ids
bim.unknown_entries()                               # quote these as UNKNOWN
bim.dataset_age_days()                              # warn when the snapshot is old
```

## Neighbouring discoveries

Host capacity and gas-export routes only matter next to the discoveries that compete for them. For a Brazilian
target list the nearby fields, evaluation-plan areas and discovery candidates with
`neqsim-near-field-discoveries` (`brazil_records`, `near_field`, `plot_near_field`) before ranking hosts, and
carry the in-development and in-evaluation neighbours into `host_capacity_check` as demand on the same host or
export line. ANP gives no discovery volumes: take them from the operator and record the source.

## Validation Checklist

- [ ] Every number quoted from the dataset carries its `source_id` and `as_of`; UNKNOWN is written as UNKNOWN.
- [ ] No tariff was invented; the net-back states it uses the MME 46 % share.
- [ ] Dataset age was checked with `dataset_age_days()` and stale values re-read from the source.
- [ ] Host ullage uses a gas-handling limit when one exists, or states that only nameplate was used.
- [ ] The gas CO2 case (low, base, high) carried into `co2_removal_fraction` matches the fluid basis.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Gas export treated as a large upside | Tariff-free gas price used at the wellhead | Apply the MME net-back; gas is about 8 % of oil revenue |
| Tie-back fits on paper | Oil nameplate used as ullage | Check the compression or gas-handling limit |
| Third-party access cited for an FPSO tie-back | Draft resolution covers pipelines and plants only | Treat as a commercial negotiation |
| UNKNOWN shown as 0 | `value` null read as a number | Use `is_unknown` and print UNKNOWN |
| Pre-salt gas assumed export-ready | CO2 6-34 mol % against a 3 mol % spec | Include CO2 removal or re-injection |

## Limitations

- Snapshot of public sources read on 2026-10-14; confidence ranges from official to press and estimate. Re-check before use.
- No numeric offshore tariff, spare route capacity, TPA terms or crude differential is available.
- Screening arithmetic only; not a gas commercialisation or regulatory opinion.

## Related NeqSim Functionality

- `neqsim.thermo.system.SystemPrEos` or `SystemSrkEos` for gas CO2 and dew points behind the declared fluid; `neqsim.process.equipment.pipeline.PipeBeggsAndBrills` for tie-back hydraulics.
- `neqsim.process.fielddevelopment.tieback.HostSynergyScreening` for host ullage cover; this skill supplies public inputs and the gas-handling check.
- Tuned fluid recipe: nested bisection on the C7+ amount and a common density offset on the TBP cuts (never molar masses); feed CO2 0.04/0.14/0.30 gave gas CO2 6.5/19.5/34.1 mol % at GOR 325 Sm3/Sm3, 31.5 API.
- Chain with `neqsim-psc-bid-economics-screening`, `neqsim-anp-open-data`, `neqsim-brazil-presalt-analogue-basis`, `neqsim-production-optimization` and `neqsim-reservoir-facility-value-chain`.

## References

- ANP Res 16/2008, Res 982/2025; Lei 14.134/2021, 12.351/2010, 13.586/2017, 15.042/2024.
- EPE PDE 2035 (gas, production, international prices), Petrobras route pages, Equinor and MODEC Bacalhau pages, ANP bulletin Jul 2026 and PPSA spot sales; URLs in `sources()`.
