"""Google Classroom Universal Automation & Submission Suite."""

from classroom.config import (
    StudentConfig,
    load_config,
    save_config,
    get_default_config_path,
    slugify,
)

__version__ = "1.0.0"

__all__ = [
    "StudentConfig",
    "load_config",
    "save_config",
    "get_default_config_path",
    "slugify",
    "__version__",
]
