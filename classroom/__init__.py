"""Google Classroom Universal Automation & Submission Suite."""

from classroom.config import (
    StudentConfig,
    load_config,
    save_config,
    get_default_config_path,
    slugify,
)
from classroom.media_processor import (
    ProcessedImage,
    process_image,
    process_terminal_screenshot,
    process_diagram,
    calculate_print_dimensions,
    autocrop_border,
)
from classroom.pdf_engine import (
    PDFBuildResult,
    NumberedCanvas,
    build_report_pdf,
    augment_teacher_template,
    overlay_on_template_page,
)

__version__ = "1.0.0"

__all__ = [
    "StudentConfig",
    "load_config",
    "save_config",
    "get_default_config_path",
    "slugify",
    "ProcessedImage",
    "process_image",
    "process_terminal_screenshot",
    "process_diagram",
    "calculate_print_dimensions",
    "autocrop_border",
    "PDFBuildResult",
    "NumberedCanvas",
    "build_report_pdf",
    "augment_teacher_template",
    "overlay_on_template_page",
    "__version__",
]
