"""cmj: plate-agnostic countermovement jump force-time analysis."""
from .config import CMJConfig, FilterSpec
from .model import AnalysisResult, Trial
from .pipeline import run_pipeline
from .readers import read_csv_any

__all__ = [
    "AnalysisResult",
    "CMJConfig",
    "FilterSpec",
    "Trial",
    "read_csv_any",
    "run_pipeline",
]

__version__ = "0.1.0"
