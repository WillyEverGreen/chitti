"""Student configuration management and filesystem path utilities."""

from dataclasses import dataclass, asdict, fields
import json
import os
from pathlib import Path
import re
from typing import Optional, Union, Dict, Any
import unicodedata


@dataclass
class StudentConfig:
    """Configuration profile for a student using the Classroom automation suite."""

    student_name: str = ""
    roll_number: str = ""
    department: str = ""
    institution: str = ""
    output_dir: str = "output"
    credentials_path: str = "credentials.json"
    token_path: str = "token.json"
    chrome_debug_port: int = 9444

    def is_configured(self) -> bool:
        """Check if minimum identifying information has been populated."""
        return bool(self.student_name.strip() and self.roll_number.strip())

    @property
    def resolved_output_dir(self) -> Path:
        """Return absolute resolved output directory path."""
        return Path(self.output_dir).expanduser().resolve()

    @property
    def resolved_credentials_path(self) -> Path:
        """Return absolute resolved Google credentials path."""
        return Path(self.credentials_path).expanduser().resolve()

    @property
    def resolved_token_path(self) -> Path:
        """Return absolute resolved Google OAuth token path."""
        return Path(self.token_path).expanduser().resolve()

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudentConfig":
        """Create a StudentConfig instance from a dictionary, ignoring unexpected keys."""
        known_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_keys}
        return cls(**filtered)


def get_default_config_path() -> Path:
    """Return the default configuration file path.

    Honors the CLASSROOM_CONFIG environment variable if set;
    otherwise defaults to `student_config.json` in the current working directory.
    """
    env_path = os.environ.get("CLASSROOM_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (Path.cwd() / "student_config.json").resolve()


def load_config(config_path: Optional[Union[str, Path]] = None) -> StudentConfig:
    """Load StudentConfig from a JSON file.

    Args:
        config_path: Path to the JSON configuration file. If None, uses get_default_config_path().

    Returns:
        StudentConfig populated from the file.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the file contains invalid JSON or is not a JSON object.
    """
    path = Path(config_path).expanduser().resolve() if config_path else get_default_config_path()
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse configuration file '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Configuration file '{path}' must contain a JSON object.")

    return StudentConfig.from_dict(data)


def save_config(config: StudentConfig, config_path: Optional[Union[str, Path]] = None) -> Path:
    """Save StudentConfig to a JSON file, creating parent directories if needed.

    Args:
        config: The StudentConfig instance to save.
        config_path: Destination path. If None, uses get_default_config_path().

    Returns:
        The Path where the configuration was written.
    """
    path = Path(config_path).expanduser().resolve() if config_path else get_default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


def slugify(text: str, lowercase: bool = True) -> str:
    """Sanitizes strings for safe use across Windows and POSIX filesystems.

    Strips reserved characters (<>:"/\\|?*), normalizes spaces and hyphens into
    clean underscores, and collapses multiple underscores.

    Args:
        text: String to sanitize (e.g. course title or assignment name).
        lowercase: Whether to convert the output to lowercase (default: True).

    Returns:
        Cleaned, filesystem-safe string.
    """
    if not text:
        return ""

    # Normalize unicode accents/diacritics to ASCII where feasible
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

    if lowercase:
        ascii_text = ascii_text.lower()

    # Replace all non-alphanumeric/non-word characters with spaces
    cleaned = re.sub(r"[^\w\s-]", " ", ascii_text)
    # Collapse sequences of whitespace, hyphens, and underscores into single underscore
    slug = re.sub(r"[\s\-_]+", "_", cleaned)
    # Strip any leading or trailing underscores
    return slug.strip("_")
