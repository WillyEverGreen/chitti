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
    render_terminal_screenshot,
    process_diagram,
    calculate_print_dimensions,
    autocrop_border,
)
from classroom.pdf_engine import (
    PDFBuildResult,
    NumberedCanvas,
    build_report_pdf,
    augment_teacher_template,
    smart_fill_rubric_fields,
    fill_lab_manual_questions,
    fill_lab_manual_questions_doc,
    overlay_on_template_page,
    personalize_reference_pdf,
)
from classroom.deliverables import (
    RequirementItem,
    RequirementAudit,
    StagedDeliverable,
    audit_assignment_requirements,
    stage_deliverable,
    print_completion_card,
    compute_sha256,
)

from classroom.workspace import (
    CourseWorkspace,
    get_course_workspace,
    extract_pdf_text,
    save_study_notes,
    download_drive_file,
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
    "render_terminal_screenshot",
    "process_diagram",
    "calculate_print_dimensions",
    "autocrop_border",
    "PDFBuildResult",
    "NumberedCanvas",
    "build_report_pdf",
    "augment_teacher_template",
    "smart_fill_rubric_fields",
    "fill_lab_manual_questions",
    "fill_lab_manual_questions_doc",
    "overlay_on_template_page",
    "personalize_reference_pdf",
    "RequirementItem",
    "RequirementAudit",
    "StagedDeliverable",
    "audit_assignment_requirements",
    "stage_deliverable",
    "print_completion_card",
    "compute_sha256",
    "CourseWorkspace",
    "get_course_workspace",
    "extract_pdf_text",
    "save_study_notes",
    "download_drive_file",
    "__version__",
]
