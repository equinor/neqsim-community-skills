# Pipe Route Profile

Educational pipe-route length and elevation-profile screening skill for public examples and agent guidance.

This skill provides a simple Python `PipeRouteModel` that converts an ordered list of waypoints with seabed depths into segment lengths, a cumulative KP profile, total route length, and an elevation profile. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/subsea/pipe-route-profile
```

## Run Example

```bash
python skills/subsea/pipe-route-profile/examples/basic_pipe_route_profile.py
```

## Run Tests

```bash
python -m pytest skills/subsea/pipe-route-profile/tests
```

## Public Scope

The model does not contain proprietary route corridors, confidential bathymetry, span analysis, or company-specific pipeline rules. Coordinates and depths must be public or synthetic. Route lengths and profiles are screening indicators only. For real work, use validated NeqSim hydraulic and flow assurance workflows and qualified subsea engineering review.
