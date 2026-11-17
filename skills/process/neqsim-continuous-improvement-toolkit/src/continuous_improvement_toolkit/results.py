"""Source result used by adapters; the core ``neqsim_continuous`` class when it is importable."""

from dataclasses import asdict, dataclass, field
from typing import Any

try:  # use the core contract when the NeqSim devtools runner is installed
    from neqsim_continuous.contracts import SourceResult
except ImportError:  # pragma: no cover - exercised only without the runner
    SOURCE_STATUSES = ("ok", "partial", "stale", "failed", "not_installed")

    @dataclass
    class SourceResult:
        """Mirror of ``neqsim_continuous.contracts.SourceResult`` (same fields and rules)."""

        status: str
        rows: int = 0
        watermark: str | None = None
        gaps: list[str] = field(default_factory=list)
        interaction_required: bool = False
        message: str = ""
        outputs: list[str] = field(default_factory=list)
        records: list[dict[str, Any]] = field(default_factory=list)

        def __post_init__(self):
            if self.status not in SOURCE_STATUSES:
                raise ValueError(f"Unknown source status '{self.status}'")

        def to_dict(self):
            data = asdict(self)
            data.pop("records", None)
            return data
