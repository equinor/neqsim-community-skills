# Subsea slot, tee and reusable-line inventory

Builds a per-item inventory of tie-in capacity in existing subsea infrastructure (free template and manifold slots,
spare tees and hubs, J-tube/riser slots, spare or reusable flowlines, gas-lift, injection and MEG lines, umbilical
cores), keeps status, service, size, remaining life, source and verification level visible, and ranks reuse options
against a new-build tie-back for one discovery. Pure Python, no JVM. Screening only.

## Install and test

```bash
python -m pip install -e skills/subsea/neqsim-subsea-slot-tee-reuse-inventory
python -m pytest skills/subsea/neqsim-subsea-slot-tee-reuse-inventory/tests
python -m subsea_slot_tee_reuse skills/subsea/neqsim-subsea-slot-tee-reuse-inventory/examples/example_inventory.json \
    skills/subsea/neqsim-subsea-slot-tee-reuse-inventory/examples/example_target.json --consumer area-development
```

## Public scope

Generic method and open data only: Sodir facilities/pipelines/wells (`items_from_sodir`) never produce a "spare" item,
free slots from open data are `estimated`. Company slot registers, P&IDs, lifetime cases and restricted map layers belong
to the enterprise skill `enterprise-infrastructure-slot-capacity`. The bundled example inventory is synthetic.
