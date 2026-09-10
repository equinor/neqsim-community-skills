# Ageing and Life-Extension Screening

Educational ageing-trend and remaining-life screening skill for public examples and agent guidance.

This skill provides `AgeingLifeExtensionModel`, which turns a corrective-failure history for a repairable equipment population into a trend verdict (Laplace centroid test), a fitted failure-intensity model (Crow-AMSAA / NHPP power law), a projection of expected failures to a required end-of-life year, and a maintain-versus-replace economic crossover.

It exists to prevent a common modelling error: fitting a Weibull lifetime distribution to the inter-arrival times of a *repaired* system and reading its shape parameter as an ageing indicator. For a repairable population the correct statistic is the trend in the rate of occurrence of failures.

## Install

```bash
python -m pip install -e skills/process/ageing-life-extension-screening
```

## Run Example

```bash
python skills/process/ageing-life-extension-screening/examples/basic_ageing_life_extension_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/ageing-life-extension-screening/tests
```

## Public Scope

The model contains no proprietary reliability datasets and no operator acceptance criteria. Thresholds are open reliability-engineering defaults and are configurable. For a real life-extension decision, use a qualified technical-condition assessment, the applicable regulatory framework, and a validated reliability dataset (ISO 14224, OREDA).
