---
name: neqsim-ncs-ownership-equity
calculation_basis: "screening"
version: "0.1.0"
description: "Reads who owns Norwegian Continental Shelf fields, discoveries and licences from Sodir (partners, equity %, operator, history, company portfolio) and turns it into net-equity inputs for field evaluation and economics. Prospect equity is not public: user-supplied or a labelled licence proxy. USE WHEN: an evaluation needs partners and working interests, a net-to-company view of volumes, capex, opex or cash flow, a portfolio roll-up, or a check of an equity assumption."
last_verified: "2026-10-07"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# NCS Ownership and Equity

This skill answers "who owns what share of this asset?" for the Norwegian
Continental Shelf and hands the answer to field evaluation and economics. It
reads the Sodir DataService, which publishes ownership openly (NLOD 2.0), and
needs no key.

| Asset | Public? | How it is read |
|-------|---------|----------------|
| Field | Yes | Sodir `field_licensee_hst` (layer 7108): company, share %, owner (licence or unit), valid dates |
| Discovery | Yes, via its owner | Sodir `discovery_owner_hst` (7007) gives the owning licence or unit; that owner's licensees (3007 licence, 3304 unit) give the shares |
| Production licence | Yes | Sodir `licence_licensee_hst` (3007); operator flagged by `prlOperDateValid*` |
| Prospect | **No** | Not published at prospect level. Use the user's own figures, or the licence it sits in as a labelled proxy |

It is a lookup and arithmetic skill. It does not compute volumes, prices, fiscal
terms or NPV; it supplies the equity fractions those steps multiply by.

## When to Use

- A field or discovery evaluation needs the partners and their working interests.
- A company wants its net share of gross volumes, revenue, capex, opex or cash flow.
- A portfolio view is needed: every field and discovery in which one company holds an interest.
- An equity assumption in a model must be checked against the public record.
- A prospect needs an equity table. The skill validates user figures or shows the licence proxy.
- Ownership changed (sale, merger, unitisation) and the history matters for a back-cast.

## Inputs

- `OwnershipReader()` reads live Sodir. Pass `fetch=` to run offline.
- Names resolve loosely and case-insensitively: `"Troll"`, `"Wisting"`,
  `"7324/8-1 (Wisting)"`. Several matches raise `OwnershipError` listing the candidates.
- `as_of` is a date (default today). Interests are valid from the start date to the
  inclusive end date; an empty end is open.
- Companies for `portfolio()` are a name or a Sodir company id. An ambiguous name
  (for example two Equinor entities) raises with the ids to choose from.

## Outputs

`OwnershipRecord` with `kind`, `name`, `as_of`, `basis`, `stakes` (company, id,
interest %, operator flag, valid dates), `owner_kind`, `owner_name`, `operator`,
`included_in_field`, `last_updated`, `total_pct`, `is_complete` and `warnings`.

- `fractions()`, `fraction_of(company)`, `find(company)`
- `allocate(gross)` for every partner, `net(gross, company)` for one; lists or
  `{year: value}` mappings both work
- `to_economics_handoff(company)`: equity fractions, caveats and a scaling note
- `portfolio_net([(record, gross), ...], company)`: sums a company's net over assets
- `OwnershipReader.history("field" | "licence", name)`: ownership periods, oldest first
- `portfolio(company, as_of)`: every field and discovery held, with interest %

`basis` is `sodir_public`, `licence_proxy` or `user_provided`. Carry it into any
report so the reader knows how firm the equity is.

## Engineering Method

1. **Resolve the name** against the field or discovery layer (exact match first,
   then substring); stop on ambiguity.
2. **Fields:** read the licensee history, keep the rows valid on `as_of`, take the
   operator from the field operator history.
3. **Discoveries:** read the owner history, keep the owner valid on `as_of`, read
   the owner id from its Sodir URL, then read that licence's or unit's licensees.
   The operator comes from the discovery operator history.
4. **Check** that the interests add up to 100 %. A shortfall is a warning, not a
   silent fix.
5. **Apply equity** by multiplying gross volumes, revenue, capex and opex by the
   fraction. Tax is a per-company calculation on the net cash flow: do not scale a
   gross tax figure.

## Python Usage Pattern

```python
from datetime import date
from ncs_ownership_equity import OwnershipReader, portfolio_net

reader = OwnershipReader()
alvheim = reader.field("Alvheim")                       # equity today
alvheim.fractions()                                     # {'Aker BP ASA': 0.8, 'ConocoPhillips ...': 0.2}
wisting = reader.discovery("Wisting")                   # via licence 537
wisting.operator, wisting.is_complete

gross_capex = {2028: 12000.0, 2029: 18000.0}            # MNOK, gross
wisting.net(gross_capex, "Aker BP")                     # Aker BP's share

# Prospect: Sodir has no prospect equity. Enter your own, or show the licence proxy.
prospect = OwnershipReader.prospect("Delta", {"Opco AS": 60, "Partner AS": 40}, operator="Opco AS",
                                    source="licence group agreement 2026-05")
proxy = reader.prospect_from_licence("Delta", "537")    # basis = licence_proxy, with a warning

# Company view: portfolio and a net cash-flow roll-up
reader.portfolio("Aker BP ASA")["items"][:5]
portfolio_net([(alvheim, alvheim_cash), (wisting, wisting_cash)], "Aker BP")

# Back-cast an earlier equity
reader.field("Alvheim", date(2019, 1, 1)).fractions()
```

## Hand-offs

- **Gross volumes and reserves:** `neqsim-norwegian-continental-shelf-data` and
  `neqsim-resource-classification-screening`.
- **Economics:** pass `to_economics_handoff()` or the net series to
  `neqsim-asset-value-npv-screening`, `neqsim-field-economics` and
  `neqsim-capex-opex-screening`.
- **Tie-in and host studies:** `neqsim-ncs-infrastructure-network` for hosts and
  routes; equity decides who carries the tariff and host costs.
- **Governed internal sources** (portfolio registers, signed agreements) belong to
  the enterprise layer and override the public record where they differ.

## Validation Checklist

- [ ] `basis` and `as_of` are stated in the report.
- [ ] `is_complete` is true, or the shortfall is explained.
- [ ] A discovery with `included_in_field` was evaluated through the field's equity.
- [ ] Unit (business arrangement area) equity was used, not the pre-unit licence equity.
- [ ] Prospect equity is labelled user-provided or licence proxy, never public.
- [ ] `last_updated` is recent; any known pending transfer is noted separately.
- [ ] Net figures sum back to the gross figure across all partners.

## Common Mistakes

- Using the licence equity for a field that has been unitised: the unit equity differs
  after redetermination. Read the field, not the licence.
- Reading a discovery that is already part of a field as a standalone asset.
- Treating `sdfi_pct` as extra: it sits inside a partner's share and is informational.
- Scaling a gross tax number by equity instead of taxing each company's net flow.
- Using a company name that matches two legal entities; pass the company id.
- Assuming a pending sale is in the data. Sodir shows approved transfers only.
- Presenting the licence proxy as prospect equity.

## Limitations

- Sodir publishes approved ownership; announced or pending transfers, farm-in
  carries, back-in rights and private side agreements are not in it.
- Prospect-level equity and cost-sharing are not public.
- Norwegian shelf only. Other provinces need their own source.
- Data currency follows Sodir's update date (`last_updated`).
- Screening only: a qualified commercial review is required before any investment use.

## Related NeqSim Functionality

`neqsim.process.fielddevelopment.economics` classes (cash flow, fiscal regime) accept the
net series; equity itself is bookkeeping and has no Java counterpart.

## References

- Sodir DataService (ArcGIS REST), layers 3003, 3007, 3304, 7000, 7006, 7007, 7100, 7108, 7110;
  FactPages tables `field_licensee_hst`, `licence_licensee_hst`. NLOD 2.0.
- Sodir FactPages sections: application, wellbore, storage, licence, bsns_arr_area,
  field, discovery, company, survey, facility, tuf, strat (no prospect section).
