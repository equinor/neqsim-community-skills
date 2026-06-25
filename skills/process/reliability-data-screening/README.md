# Reliability Data Screening

Educational reliability and availability screening skill for public examples and agent guidance.

This skill provides a simple Python `ReliabilityDataModel` with placeholder indicators for MTBF, steady-state availability with parallel redundancy, mission reliability, and expected failures using open ISO 14224 / OREDA style relations. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/reliability-data-screening
```

## Run Example

```bash
python skills/process/reliability-data-screening/examples/basic_reliability_data_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/reliability-data-screening/tests
```

## Public Scope

The model contains no proprietary OREDA datasets or vendor reliability data. For real calculations, use validated RAM analysis, validated NeqSim resources, and a qualified reliability dataset (ISO 14224, OREDA).
