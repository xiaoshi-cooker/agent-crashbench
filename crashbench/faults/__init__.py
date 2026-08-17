"""Declarative fault injection (docs/design/faults.md)."""

from crashbench.faults.injector import (
    ApiThrottleError,
    FaultPlan,
    InjectedBackend,
    InjectedToolRegistry,
)

__all__ = ["FaultPlan", "InjectedToolRegistry", "InjectedBackend", "ApiThrottleError"]
