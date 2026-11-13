"""Read-only investigator for synthetic Kubernetes incident cases."""

from .core import Diagnosis, Finding, investigate_case, load_case

__all__ = ["Diagnosis", "Finding", "investigate_case", "load_case"]
__version__ = "0.1.0"
