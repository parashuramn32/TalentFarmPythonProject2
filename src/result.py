"""Structured validation result and the check registry.

Every validation returns a ValidationResult with the fields required by the
Submission 2 guideline: validation ID, layer, name, source and target object,
expected value, actual value, status, variance and remarks.
"""
from dataclasses import dataclass, field

PASS, FAIL, ERROR, SKIPPED = "PASS", "FAIL", "ERROR", "SKIPPED"

LAYERS = [
    "Source-to-Staging",
    "Data Quality",
    "Staging-to-Data Mart",
    "Aggregate Model",
    "Data Mart-to-Reporting",
]


@dataclass
class ValidationResult:
    validation_id: str
    layer: str
    validation_name: str
    source_object: str = ""
    target_object: str = ""
    expected_value: object = None
    actual_value: object = None
    status: str = "NOT RUN"
    variance: object = None
    remarks: str = ""
    severity: str = "Medium"
    risk_ref: str = ""
    mismatches: list = field(default_factory=list, repr=False)

    def as_row(self):
        return {
            "Validation ID": self.validation_id,
            "Layer": self.layer,
            "Validation Name": self.validation_name,
            "Source Object": self.source_object,
            "Target Object": self.target_object,
            "Expected Value": self.expected_value,
            "Actual Value": self.actual_value,
            "Status": self.status,
            "Variance": self.variance,
            "Remarks": self.remarks,
            "Severity": self.severity,
            "Risk Ref": self.risk_ref,
        }


@dataclass
class Check:
    validation_id: str
    layer: str
    name: str
    source: str
    target: str
    severity: str
    risk_ref: str
    func: object


REGISTRY = []


def check(validation_id, layer, name, source, target, severity="Medium", risk_ref=""):
    """Register a validation. The decorated function receives the run context
    and returns a dict with expected, actual, status and optional variance,
    remarks and mismatches."""
    if layer not in LAYERS:
        raise ValueError(f"Unknown layer {layer}")

    def deco(func):
        if any(c.validation_id == validation_id for c in REGISTRY):
            raise ValueError(f"Duplicate validation id {validation_id}")
        REGISTRY.append(Check(validation_id, layer, name, source, target, severity, risk_ref, func))
        return func
    return deco


def outcome(expected, actual, passed, variance=None, remarks="", mismatches=None, status=None):
    """Build the dict a check returns."""
    return {
        "expected": expected,
        "actual": actual,
        "status": status or (PASS if passed else FAIL),
        "variance": variance,
        "remarks": remarks,
        "mismatches": mismatches or [],
    }


def skipped(reason):
    return {"expected": None, "actual": None, "status": SKIPPED, "variance": None,
            "remarks": reason, "mismatches": []}


def pct(part, whole):
    return f"{100.0 * part / whole:.1f}%" if whole else "n/a"
