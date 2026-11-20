"""Synthetic release cases shared by the flare helideck dispersion tests."""

from flare_helideck_dispersion import ReleaseCase


def release_cases():
    """A warm, a cold dense and a small case."""
    return [
        ReleaseCase("warm", 150.0, 0.0215, 1.25, 273.15, 0.04, 0.96, 0.6),
        ReleaseCase("cold", 150.0, 0.0215, 1.25, 190.0, 0.04, 0.96, 0.6),
        ReleaseCase("small", 20.0, 0.0215, 1.25, 323.15, 0.04, 0.96, 0.6),
    ]
