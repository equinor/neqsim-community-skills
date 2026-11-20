# Marine Operations Weather-Window Planning

Educational weather-window planning for offshore marine campaigns (survey,
flowline and umbilical lay, structure installation, intervention). A sequence of
weather-restricted operations is simulated over every start date in a hindcast to
give P10/P50/P90 campaign duration including waiting on weather, a monthly view,
and a cost ranking of vessel options.

This skill supports screening only. Operational limits, forecast (alpha) factors
and vessel sea-keeping must come from the governing standard and the marine
contractor. A qualified marine engineer must review the result.

## Install

```bash
pip install -e .[test]
```

## Run the tests

```bash
python -m pytest
```

See `SKILL.md` for inputs, outputs, engineering method, validation checklist and
limitations.
