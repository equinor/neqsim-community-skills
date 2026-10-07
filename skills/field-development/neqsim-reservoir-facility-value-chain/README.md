# Reservoir-to-Facility Value Chain

Dependency-free helpers for a gas value chain: p/z history match from shut-in
pressures, Rawlins-Schellhardt well deliverability, facility capacity from a
process-model throughput sweep, and the supply/capacity balance that picks the
separation pressure. The NeqSim Java counterparts are `RealGasMaterialBalanceDrive`,
`MaterialBalanceHistoryMatch`, `RawlinsSchellhardtFit` and `SupplyCapacityBalance`
in `neqsim.process.fielddevelopment.integrated`. See `SKILL.md` for the workflow.

```bash
cd skills/field-development/neqsim-reservoir-facility-value-chain
python -m pytest
python examples/gas_chain_demo.py
```

## License

Apache-2.0.
