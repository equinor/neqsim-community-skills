# PSC Bid Economics Screening

Educational screening of a bid on a Production Sharing Contract (PSC) exploration block. It evaluates the expected monetary value (EMV) of the bid and solves the break-even offered profit-oil share, so a bid can be judged against value before any discovery exists.

The model mirrors the validated NeqSim Java class `neqsim.process.fielddevelopment.economics.PscBidEconomics`.

## Install

```bash
python -m pip install -e skills/field-development/neqsim-psc-bid-economics-screening
```

## Run Example

```bash
python skills/field-development/neqsim-psc-bid-economics-screening/examples/basic_psc_bid_screening.py
```

## Run Tests

```bash
python -m pytest skills/field-development/neqsim-psc-bid-economics-screening/tests
```

## Public Scope

Contains only generic public PSC mechanics and placeholder defaults. It holds no company hurdle rates, price decks, partner terms or bid-round contract data. For real decisions, use the bid-round contract terms, validated NeqSim field-economics classes and a qualified commercial review.
