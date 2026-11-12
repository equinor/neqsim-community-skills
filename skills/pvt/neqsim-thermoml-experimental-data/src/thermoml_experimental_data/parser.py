"""Parse a ThermoML document into compounds, datasets and flat state points."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from .units import pressure_to_bara, split_name_unit


@dataclass(frozen=True)
class Compound:
    """One compound of the report, keyed by its ``nOrgNum``."""

    org_num: int
    names: Tuple[str, ...]
    inchikey: str = ""
    formula: str = ""

    @property
    def name(self) -> str:
        """Primary (first listed) common name."""
        return self.names[0] if self.names else f"compound-{self.org_num}"


@dataclass(frozen=True)
class Quantity:
    """A named variable or constraint with its unit and optional component."""

    name: str
    unit: str
    component: Optional[int] = None
    number: int = 0


@dataclass(frozen=True)
class PropertyDef:
    """A measured property of one dataset."""

    number: int
    name: str
    unit: str
    phase: str = ""
    component: Optional[int] = None


@dataclass
class Dataset:
    """One ``PureOrMixtureData`` block: fixed constraints plus a table of rows."""

    number: int
    components: List[int]
    properties: List[PropertyDef]
    constraints: List[Tuple[Quantity, float]]
    variables: List[Quantity]
    rows: List[Tuple[Dict[int, float], Dict[int, Tuple[float, Optional[float]]]]] = field(default_factory=list)


@dataclass(frozen=True)
class DataPoint:
    """One measured value with the thermodynamic state it was measured at."""

    doi: str
    dataset: int
    components: Tuple[str, ...]
    property_name: str
    unit: str
    phase: str
    value: float
    uncertainty: Optional[float]
    temperature_k: Optional[float]
    pressure_bara: Optional[float]
    mole_fractions: Dict[str, float]
    other: Dict[str, float]


@dataclass
class ThermomlReport:
    """Parsed ThermoML document."""

    citation: Dict[str, str]
    compounds: Dict[int, Compound]
    datasets: List[Dataset]

    @property
    def doi(self) -> str:
        """DOI of the source article (empty when absent)."""
        return self.citation.get("doi", "")

    def points(
        self,
        property_contains: Optional[str] = None,
        phase_contains: Optional[str] = None,
        component: Optional[str] = None,
    ) -> Iterator[DataPoint]:
        """Yield flat data points, optionally filtered by property, phase or component name (case-insensitive)."""
        for dataset in self.datasets:
            names = tuple(self.compounds[c].name if c in self.compounds else f"compound-{c}" for c in dataset.components)
            if component and not any(component.lower() in self._all_names(c) for c in dataset.components):
                continue
            for var_values, prop_values in dataset.rows:
                state = self._state(dataset, var_values, names)
                for prop in dataset.properties:
                    if prop.number not in prop_values:
                        continue
                    if property_contains and property_contains.lower() not in prop.name.lower():
                        continue
                    if phase_contains and phase_contains.lower() not in prop.phase.lower():
                        continue
                    value, uncertainty = prop_values[prop.number]
                    yield DataPoint(
                        self.doi, dataset.number, names, prop.name, prop.unit, prop.phase, value, uncertainty,
                        state["T"], state["P"], state["x"], state["other"],
                    )

    def _all_names(self, org_num: int) -> str:
        compound = self.compounds.get(org_num)
        return " | ".join(compound.names).lower() if compound else ""

    def _state(self, dataset: Dataset, var_values: Dict[int, float], names: Tuple[str, ...]) -> dict:
        temperature: Optional[float] = None
        pressure: Optional[float] = None
        fractions: Dict[str, float] = {}
        other: Dict[str, float] = {}
        quantities = list(dataset.constraints) + [(v, var_values[v.number]) for v in dataset.variables if v.number in var_values]
        for quantity, value in quantities:
            lowered = quantity.name.lower()
            if lowered.startswith("temperature") and quantity.unit == "K":
                temperature = value
            elif lowered.startswith("pressure"):
                converted = pressure_to_bara(value, quantity.unit)
                if converted is not None:
                    pressure = converted
            elif lowered == "mole fraction" and quantity.component is not None:
                compound = self.compounds.get(quantity.component)
                fractions[compound.name if compound else f"compound-{quantity.component}"] = value
            else:
                other[f"{quantity.name}, {quantity.unit}".rstrip(", ")] = value
        if len(names) == 1:
            fractions = {names[0]: 1.0}
        elif fractions and len(fractions) == len(names) - 1:
            missing = [n for n in names if n not in fractions]
            fractions[missing[0]] = 1.0 - sum(fractions.values())
        return {"T": temperature, "P": pressure, "x": fractions, "other": other}


def _strip_namespaces(root: ET.Element) -> None:
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]


def _text(element: Optional[ET.Element], path: str) -> str:
    found = element.find(path) if element is not None else None
    return (found.text or "").strip() if found is not None else ""


def _float(text: str) -> Optional[float]:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _int(element: Optional[ET.Element], path: str) -> Optional[int]:
    value = _float(_text(element, path))
    return None if value is None else int(value)


def _type_label(holder: Optional[ET.Element]) -> str:
    """Return the text of the single ``e...`` child (for example ``eTemperature``) of a ``*Type`` element."""
    if holder is None:
        return ""
    for child in holder:
        if child.text and child.text.strip():
            return child.text.strip()
    return ""


def _compound(element: ET.Element) -> Compound:
    return Compound(
        org_num=_int(element, "RegNum/nOrgNum") or 0,
        names=tuple((n.text or "").strip() for n in element.findall("sCommonName") if (n.text or "").strip()),
        inchikey=_text(element, "sStandardInChIKey"),
        formula=_text(element, "sFormulaMolec"),
    )


def _property(element: ET.Element) -> PropertyDef:
    group = element.find("Property-MethodID/PropertyGroup")
    group_child = group[0] if group is not None and len(group) else None
    name, unit = split_name_unit(_text(group_child, "ePropName"))
    return PropertyDef(
        number=_int(element, "nPropNumber") or 0,
        name=name,
        unit=unit,
        phase=_text(element, "PropPhaseID/ePropPhase"),
        component=_int(element, "Property-MethodID/RegNum/nOrgNum"),
    )


def _quantity(element: ET.Element, id_tag: str, type_tag: str, number_tag: str) -> Quantity:
    name, unit = split_name_unit(_type_label(element.find(f"{id_tag}/{type_tag}")))
    return Quantity(name, unit, _int(element, f"{id_tag}/RegNum/nOrgNum"), _int(element, number_tag) or 0)


def _dataset(element: ET.Element) -> Dataset:
    constraints: List[Tuple[Quantity, float]] = []
    for item in element.findall("Constraint"):
        value = _float(_text(item, "nConstraintValue"))
        if value is not None:
            constraints.append((_quantity(item, "ConstraintID", "ConstraintType", "nConstraintNumber"), value))
    dataset = Dataset(
        number=_int(element, "nPureOrMixtureDataNumber") or 0,
        components=[_int(c, "RegNum/nOrgNum") or 0 for c in element.findall("Component")],
        properties=[_property(p) for p in element.findall("Property")],
        constraints=constraints,
        variables=[_quantity(v, "VariableID", "VariableType", "nVarNumber") for v in element.findall("Variable")],
    )
    for block in element.findall("NumValues"):
        variables = {_int(v, "nVarNumber") or 0: _float(_text(v, "nVarValue")) for v in block.findall("VariableValue")}
        properties: Dict[int, Tuple[float, Optional[float]]] = {}
        for p in block.findall("PropertyValue"):
            value = _float(_text(p, "nPropValue"))
            if value is not None:
                properties[_int(p, "nPropNumber") or 0] = (value, _float(_text(p, "CombinedUncertainty/nCombExpandUncertValue")))
        dataset.rows.append(({k: v for k, v in variables.items() if v is not None}, properties))
    return dataset


def parse_thermoml(xml: bytes | str) -> ThermomlReport:
    """Parse ThermoML XML text or bytes. Raises ``ValueError`` when the root is not a ThermoML ``DataReport``."""
    root = ET.fromstring(xml)
    _strip_namespaces(root)
    if root.tag != "DataReport":
        raise ValueError(f"not a ThermoML document (root element {root.tag!r})")
    citation = root.find("Citation")
    meta = {
        "doi": _text(citation, "sDOI"),
        "title": _text(citation, "sTitle"),
        "journal": _text(citation, "sPubName"),
        "year": _text(citation, "yrPubYr"),
        "authors": "; ".join((a.text or "").strip() for a in citation.findall("sAuthor")) if citation is not None else "",
    }
    compounds = {c.org_num: c for c in (_compound(e) for e in root.findall("Compound"))}
    return ThermomlReport(meta, compounds, [_dataset(e) for e in root.findall("PureOrMixtureData")])
