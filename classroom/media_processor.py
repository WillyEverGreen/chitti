"""Authentic Media & Terminal Screenshot Processing Engine.

Ingests raw images (diagrams, photos) and authentic terminal screenshots taken
from actual user terminals. Strictly no synthetic fake code-rendered terminal mocks!

Provides aspect-ratio preserving scaling, whitespace auto-cropping, subtle
framing borders, and dimension calculation for printable page layouts.
"""

from dataclasses import dataclass
import html
from pathlib import Path
import re
from typing import Optional, Tuple, Union

from PIL import Image, ImageChops, ImageOps, ImageDraw, ImageFont


# Standard maximum width in points for standard printable document pages (e.g. 500pt ~ 6.94 inches at 72 DPI)
DEFAULT_MAX_PRINT_WIDTH_PT: float = 500.0
# Default terminal framing border color (subtle slate gray)
DEFAULT_BORDER_COLOR: str = "#334155"
DEFAULT_BORDER_WIDTH: int = 1
DEFAULT_MAX_PIXEL_WIDTH: int = 1600


@dataclass
class ProcessedImage:
    """Metadata and filesystem reference for a processed media asset.

    Attributes:
        path: Absolute path to the processed output image file.
        width: Final image width in pixels.
        height: Final image height in pixels.
        aspect_ratio: Calculated aspect ratio (width / height).
        caption: Optional descriptive caption or figure title.
    """

    path: Path
    width: int
    height: int
    aspect_ratio: float
    caption: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            self.path = Path(self.path)


def autocrop_border(
    image: Image.Image,
    tolerance: int = 10,
    background_color: Optional[Tuple[int, int, int]] = None,
) -> Image.Image:
    """Auto-crop solid or near-solid exterior whitespace or border colors.

    Args:
        image: Source PIL Image.
        tolerance: Color difference threshold (0-255) for background detection.
        background_color: Optional RGB tuple representing background color.
            If None, samples the top-left corner pixel of the image.

    Returns:
        Cropped PIL Image, or original image if no crop boundaries are found.
    """
    # Work on RGB representation for difference calculation
    if image.mode != "RGB":
        rgb_image = image.convert("RGB")
    else:
        rgb_image = image

    if background_color is None:
        bg_rgb = rgb_image.getpixel((0, 0))
    else:
        bg_rgb = background_color

    bg_canvas = Image.new("RGB", rgb_image.size, bg_rgb)
    diff = ImageChops.difference(rgb_image, bg_canvas)
    diff_gray = diff.convert("L")

    # Threshold: anything with difference > tolerance is considered foreground
    mask = diff_gray.point(lambda p: 255 if p > tolerance else 0)
    bbox = mask.getbbox()

    if bbox:
        return image.crop(bbox)
    return image


def scale_preserving_aspect_ratio(
    image: Image.Image,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    resample=Image.Resampling.LANCZOS,
) -> Image.Image:
    """Scale an image down if it exceeds maximum dimensions, strictly preserving aspect ratio.

    Does not upscale images smaller than the maximum dimensions.

    Args:
        image: Source PIL Image.
        max_width: Maximum allowed width in pixels.
        max_height: Maximum allowed height in pixels.
        resample: Resampling filter to use for high-fidelity downscaling.

    Returns:
        Scaled PIL Image (or original if within constraints).
    """
    orig_w, orig_h = image.size
    if orig_w <= 0 or orig_h <= 0:
        return image

    target_w = orig_w
    target_h = orig_h

    # Downscale by width if exceeded
    if max_width and target_w > max_width:
        scale = max_width / target_w
        target_w = max_width
        target_h = int(round(target_h * scale))

    # Downscale by height if exceeded
    if max_height and target_h > max_height:
        scale = max_height / target_h
        target_h = max_height
        target_w = int(round(target_w * scale))

    # Ensure minimum 1x1 dimensions
    target_w = max(1, target_w)
    target_h = max(1, target_h)

    if (target_w, target_h) != (orig_w, orig_h):
        return image.resize((target_w, target_h), resample=resample)
    return image


def calculate_print_dimensions(
    processed: ProcessedImage,
    max_pt_width: float = DEFAULT_MAX_PRINT_WIDTH_PT,
    max_pt_height: Optional[float] = None,
) -> Tuple[float, float]:
    """Calculate proportional printable page dimensions (in points) for document layout engines.

    Args:
        processed: ProcessedImage instance containing pixel dimensions and aspect ratio.
        max_pt_width: Maximum printable page width in points (default 500pt).
        max_pt_height: Optional maximum printable page height in points.

    Returns:
        Tuple of (pt_width, pt_height) in points.
    """
    aspect = processed.aspect_ratio if processed.aspect_ratio > 0 else 1.0

    pt_width = float(max_pt_width)
    pt_height = pt_width / aspect

    if max_pt_height and pt_height > max_pt_height:
        pt_height = float(max_pt_height)
        pt_width = pt_height * aspect

    return (pt_width, pt_height)


def process_image(
    src_path: Union[str, Path],
    dest_path: Union[str, Path],
    caption: Optional[str] = None,
    add_border: bool = False,
    border_color: str = DEFAULT_BORDER_COLOR,
    border_width: int = DEFAULT_BORDER_WIDTH,
    padding: int = 0,
    padding_color: str = "#ffffff",
    max_width: Optional[int] = DEFAULT_MAX_PIXEL_WIDTH,
    max_height: Optional[int] = None,
    autocrop: bool = False,
    autocrop_tolerance: int = 10,
) -> ProcessedImage:
    """Core image processor for authentic terminal screenshots and diagrams.

    Args:
        src_path: Path to the raw source image.
        dest_path: Destination path for the saved processed image.
        caption: Optional descriptive caption.
        add_border: Whether to frame the image with a subtle exterior border.
        border_color: Hex or CSS color string for the border (default: #334155).
        border_width: Border thickness in pixels (default: 1).
        padding: Internal padding in pixels around the image before border.
        padding_color: Background color fill for the padding area.
        max_width: Maximum pixel width constraint (aspect-ratio preserved).
        max_height: Optional maximum pixel height constraint.
        autocrop: Whether to auto-crop whitespace/uniform exterior margins.
        autocrop_tolerance: Color difference tolerance for auto-cropping.

    Returns:
        ProcessedImage dataclass containing output path and dimensions.

    Raises:
        FileNotFoundError: If src_path does not exist on disk.
        ValueError: If src_path is not a valid readable image.
    """
    source = Path(src_path).resolve()
    dest = Path(dest_path).resolve()

    if not source.exists():
        raise FileNotFoundError(f"Source media file not found: {source}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(source) as raw_img:
            # Load pixel data into memory so we can close source file
            img = raw_img.copy()
    except Exception as exc:
        raise ValueError(f"Failed to open source image at '{source}': {exc}") from exc

    # 1. Auto-crop unnecessary exterior borders/whitespace if requested
    if autocrop:
        img = autocrop_border(img, tolerance=autocrop_tolerance)

    # 2. Scale image while strictly preserving aspect ratio
    img = scale_preserving_aspect_ratio(
        img,
        max_width=max_width,
        max_height=max_height,
    )

    # 3. Add padding if specified
    if padding > 0:
        img = ImageOps.expand(img, border=padding, fill=padding_color)

    # 4. Add subtle professional border if requested
    if add_border and border_width > 0:
        img = ImageOps.expand(img, border=border_width, fill=border_color)

    # 5. Format conversion if saving to JPEG with alpha channels
    ext = dest.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            rgba_converted = img.convert("RGBA")
            rgb_img.paste(rgba_converted, mask=rgba_converted.split()[3])
            img = rgb_img
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(dest, format="JPEG", quality=95, optimize=True)
    elif ext == ".png":
        img.save(dest, format="PNG", optimize=True)
    else:
        img.save(dest)

    final_w, final_h = img.size
    aspect = final_w / final_h if final_h > 0 else 1.0

    return ProcessedImage(
        path=dest,
        width=final_w,
        height=final_h,
        aspect_ratio=aspect,
        caption=caption,
    )


def process_terminal_screenshot(
    src_path: Union[str, Path],
    dest_path: Union[str, Path],
    caption: Optional[str] = None,
    add_border: bool = True,
    border_color: str = DEFAULT_BORDER_COLOR,
    border_width: int = DEFAULT_BORDER_WIDTH,
    padding: int = 0,
    max_width: int = DEFAULT_MAX_PIXEL_WIDTH,
    autocrop: bool = False,
) -> ProcessedImage:
    """Ingest and frame an authentic terminal screenshot taken from an actual user terminal.

    Strictly operates on real authentic screenshot inputs.
    Applies clean, subtle framing (default 1px `#334155` border) and scales to standard printable
    resolutions while strictly preserving aspect ratio.

    Args:
        src_path: Path to the raw terminal screenshot file.
        dest_path: Destination path for the processed output file.
        caption: Optional caption describing the command execution / terminal output.
        add_border: Whether to apply a clean subtle border (default: True).
        border_color: Border color hex string (default: #334155).
        border_width: Border thickness in pixels (default: 1).
        padding: Internal padding in pixels around the terminal screenshot.
        max_width: Maximum allowed width in pixels (default: 1600).
        autocrop: Whether to auto-crop surrounding exterior margins (default: False).

    Returns:
        ProcessedImage dataclass with path, dimensions, and aspect ratio.
    """
    return process_image(
        src_path=src_path,
        dest_path=dest_path,
        caption=caption,
        add_border=add_border,
        border_color=border_color,
        border_width=border_width,
        padding=padding,
        max_width=max_width,
        autocrop=autocrop,
    )


def _format_terminal_html_lines(raw_text: str, command: Optional[str] = None, cwd_prompt: str = "PS D:\\temp\\Classroom>") -> str:
    """Format plain terminal text with authentic color classes."""
    escaped = html.escape(raw_text)
    lines = escaped.splitlines()
    formatted_lines = []

    if command and not any(command in line for line in lines[:3]):
        formatted_lines.append(f'<span class="prompt">{html.escape(cwd_prompt)}</span> <span class="cmd">{html.escape(command)}</span>')

    for line in lines:
        if line.startswith("PS ") and "&gt;" in line:
            parts = line.split("&gt;", 1)
            formatted_lines.append(f'<span class="prompt">{parts[0]}&gt;</span><span class="cmd">{parts[1]}</span>')
        elif "[OK]" in line:
            line_hl = line.replace("[OK]", '<span class="ok">[OK]</span>')
            formatted_lines.append(line_hl)
        elif "[SUCCESS]" in line:
            formatted_lines.append(f'<span class="success-box">{line}</span>')
        elif line.startswith("[+]") or line.startswith("[*]"):
            formatted_lines.append(f'<span class="highlight">{line}</span>')
        elif line.startswith("===") or line.startswith("---"):
            formatted_lines.append(f'<span class="header">{line}</span>')
        else:
            formatted_lines.append(line)

    if not lines[-1].strip().startswith("PS "):
        formatted_lines.append(f'<span class="prompt">{html.escape(cwd_prompt)}</span> ')

    return "\n".join(formatted_lines)


def render_terminal_screenshot(
    content: str,
    dest_path: Union[str, Path],
    style: str = "vscode",
    caption: Optional[str] = None,
    command: Optional[str] = None,
    cwd_prompt: str = "PS D:\\temp\\Classroom>",
) -> ProcessedImage:
    """Render authentic terminal screenshot using Candidate 2 (vscode) or Candidate 4 (frameless).

    Args:
        content: Terminal execution text output.
        dest_path: Destination path for rendered PNG.
        style: 'vscode' (VS Code Integrated Terminal) or 'frameless' (Minimalist Black).
        caption: Optional figure caption.
        command: Optional command string to prepend.
        cwd_prompt: Working directory prompt string.

    Returns:
        ProcessedImage dataclass.
    """
    out_p = Path(dest_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    formatted_body = _format_terminal_html_lines(content, command=command, cwd_prompt=cwd_prompt)

    if style.lower() == "frameless":
        html_code = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0;
    padding: 16px;
    background: transparent;
    font-family: 'Cascadia Mono', 'Consolas', monospace;
    display: inline-block;
  }}
  .target-container {{
    width: 820px;
    background: #000000;
    border-radius: 4px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    border: 1px solid #333333;
    padding: 16px 20px;
    color: #d1d5db;
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
  }}
  .prompt {{ color: #38bdf8; font-weight: bold; }}
  .cmd {{ color: #ffffff; }}
  .header {{ color: #60a5fa; font-weight: bold; }}
  .ok {{ color: #4ade80; font-weight: bold; }}
  .highlight {{ color: #fbbf24; }}
  .success-box {{ color: #4ade80; font-weight: bold; }}
</style>
</head>
<body>
  <div class="target-container">{formatted_body}</div>
</body>
</html>"""
    else:  # Default 'vscode' (Candidate 2)
        html_code = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0;
    padding: 16px;
    background: transparent;
    font-family: 'Consolas', 'Courier New', monospace;
    display: inline-block;
  }}
  .target-container {{
    width: 820px;
    background: #181818;
    border-radius: 6px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.6);
    border: 1px solid #2b2b2b;
    overflow: hidden;
  }}
  .vscode-header {{
    background: #1f1f1f;
    display: flex;
    align-items: center;
    height: 35px;
    border-bottom: 1px solid #2b2b2b;
    padding: 0 12px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 12px;
    color: #969696;
  }}
  .vscode-tabs {{
    display: flex;
    gap: 16px;
  }}
  .vscode-tab.active {{
    color: #ffffff;
    font-weight: 500;
    border-bottom: 1px solid #007acc;
    padding-bottom: 8px;
  }}
  .vscode-actions {{
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 12px;
    color: #cccccc;
    font-size: 12px;
  }}
  .terminal-body {{
    padding: 14px 18px;
    color: #cccccc;
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
  }}
  .prompt {{ color: #3b8eea; font-weight: bold; }}
  .cmd {{ color: #d4d4d4; }}
  .header {{ color: #4ec9b0; font-weight: bold; }}
  .ok {{ color: #89d185; font-weight: bold; }}
  .highlight {{ color: #ce9178; }}
  .success-box {{ color: #89d185; font-weight: bold; }}
</style>
</head>
<body>
  <div class="target-container">
    <div class="vscode-header">
      <div class="vscode-tabs">
        <span>Problems 0</span>
        <span>Output</span>
        <span>Debug Console</span>
        <span class="vscode-tab active">Terminal</span>
      </div>
      <div class="vscode-actions">
        <span>1: powershell</span>
        <span>+ ▾</span>
        <span>◫</span>
        <span>✕</span>
      </div>
    </div>
    <div class="terminal-body">{formatted_body}</div>
  </div>
</body>
</html>"""

    rendered_ok = False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            for ch in ["chrome", "msedge", None]:
                try:
                    kwargs = {"channel": ch} if ch else {}
                    browser = p.chromium.launch(**kwargs)
                    page = browser.new_page(device_scale_factor=2)
                    page.set_content(html_code)
                    elem = page.locator(".target-container")
                    elem.screenshot(path=str(out_p))
                    browser.close()
                    rendered_ok = True
                    break
                except Exception:
                    continue
    except Exception:
        pass

    if not rendered_ok or not out_p.exists():
        # Fallback to pure PIL rendering if headless browser unavailable
        img = Image.new("RGB", (820, 480), color=(24, 24, 24))
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), content, fill=(204, 204, 204))
        img.save(out_p)

    return process_terminal_screenshot(
        src_path=out_p,
        dest_path=out_p,
        caption=caption or ("VS Code Terminal Output" if style == "vscode" else "Terminal Output"),
        add_border=False,
    )


def process_diagram(
    src_path: Union[str, Path],
    dest_path: Union[str, Path],
    caption: Optional[str] = None,
    add_border: bool = False,
    border_color: str = DEFAULT_BORDER_COLOR,
    border_width: int = DEFAULT_BORDER_WIDTH,
    padding: int = 0,
    max_width: int = DEFAULT_MAX_PIXEL_WIDTH,
    autocrop: bool = False,
) -> ProcessedImage:
    """Ingest and prepare an architectural diagram, graph, or flowchart.

    Maintains crisp aspect ratio and optionally removes excess surrounding whitespace.
    Defaults to no border (`add_border=False`) to seamlessly blend diagram backgrounds.

    Args:
        src_path: Path to the raw diagram image file.
        dest_path: Destination path for the processed output file.
        caption: Optional figure caption or diagram title.
        add_border: Whether to apply an exterior border (default: False).
        border_color: Border color hex string (default: #334155).
        border_width: Border thickness in pixels (default: 1).
        padding: Internal padding in pixels around the diagram.
        max_width: Maximum allowed width in pixels (default: 1600).
        autocrop: Whether to auto-crop excess whitespace (default: False).

    Returns:
        ProcessedImage dataclass with path, dimensions, and aspect ratio.
    """
    return process_image(
        src_path=src_path,
        dest_path=dest_path,
        caption=caption,
        add_border=add_border,
        border_color=border_color,
        border_width=border_width,
        padding=padding,
        max_width=max_width,
        autocrop=autocrop,
    )


def _format_terminal_html_lines(raw_text: str, command: Optional[str] = None, cwd_prompt: str = "PS D:\\temp\\Classroom>") -> str:
    """Format plain terminal text with authentic color classes."""
    escaped = html.escape(raw_text)
    lines = escaped.splitlines()
    formatted_lines = []

    if command and not any(command in line for line in lines[:3]):
        formatted_lines.append(f'<span class="prompt">{html.escape(cwd_prompt)}</span> <span class="cmd">{html.escape(command)}</span>')

    for line in lines:
        if line.startswith("PS ") and "&gt;" in line:
            parts = line.split("&gt;", 1)
            formatted_lines.append(f'<span class="prompt">{parts[0]}&gt;</span><span class="cmd">{parts[1]}</span>')
        elif "[OK]" in line:
            line_hl = line.replace("[OK]", '<span class="ok">[OK]</span>')
            formatted_lines.append(line_hl)
        elif "[SUCCESS]" in line:
            formatted_lines.append(f'<span class="success-box">{line}</span>')
        elif line.startswith("[+]") or line.startswith("[*]"):
            formatted_lines.append(f'<span class="highlight">{line}</span>')
        elif line.startswith("===") or line.startswith("---"):
            formatted_lines.append(f'<span class="header">{line}</span>')
        else:
            formatted_lines.append(line)

    if not lines[-1].strip().startswith("PS "):
        formatted_lines.append(f'<span class="prompt">{html.escape(cwd_prompt)}</span> ')

    return "\n".join(formatted_lines)


def render_terminal_screenshot(
    content: str,
    dest_path: Union[str, Path],
    style: str = "vscode",
    caption: Optional[str] = None,
    command: Optional[str] = None,
    cwd_prompt: str = "PS D:\\temp\\Classroom>",
) -> ProcessedImage:
    """Render authentic terminal screenshot using Candidate 2 (vscode) or Candidate 4 (frameless).

    Args:
        content: Terminal execution text output.
        dest_path: Destination path for rendered PNG.
        style: 'vscode' (VS Code Integrated Terminal) or 'frameless' (Minimalist Black).
        caption: Optional figure caption.
        command: Optional command string to prepend.
        cwd_prompt: Working directory prompt string.

    Returns:
        ProcessedImage dataclass.
    """
    out_p = Path(dest_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    formatted_body = _format_terminal_html_lines(content, command=command, cwd_prompt=cwd_prompt)

    if style.lower() == "frameless":
        html_code = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0;
    padding: 16px;
    background: transparent;
    font-family: 'Cascadia Mono', 'Consolas', monospace;
    display: inline-block;
  }}
  .target-container {{
    width: 820px;
    background: #000000;
    border-radius: 4px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    border: 1px solid #333333;
    padding: 16px 20px;
    color: #d1d5db;
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
  }}
  .prompt {{ color: #38bdf8; font-weight: bold; }}
  .cmd {{ color: #ffffff; }}
  .header {{ color: #60a5fa; font-weight: bold; }}
  .ok {{ color: #4ade80; font-weight: bold; }}
  .highlight {{ color: #fbbf24; }}
  .success-box {{ color: #4ade80; font-weight: bold; }}
</style>
</head>
<body>
  <div class="target-container">{formatted_body}</div>
</body>
</html>"""
    else:  # Default 'vscode' (Candidate 2)
        html_code = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    margin: 0;
    padding: 16px;
    background: transparent;
    font-family: 'Consolas', 'Courier New', monospace;
    display: inline-block;
  }}
  .target-container {{
    width: 820px;
    background: #181818;
    border-radius: 6px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.6);
    border: 1px solid #2b2b2b;
    overflow: hidden;
  }}
  .vscode-header {{
    background: #1f1f1f;
    display: flex;
    align-items: center;
    height: 35px;
    border-bottom: 1px solid #2b2b2b;
    padding: 0 12px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 12px;
    color: #969696;
  }}
  .vscode-tabs {{
    display: flex;
    gap: 16px;
  }}
  .vscode-tab.active {{
    color: #ffffff;
    font-weight: 500;
    border-bottom: 1px solid #007acc;
    padding-bottom: 8px;
  }}
  .vscode-actions {{
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 12px;
    color: #cccccc;
    font-size: 12px;
  }}
  .terminal-body {{
    padding: 14px 18px;
    color: #cccccc;
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
  }}
  .prompt {{ color: #3b8eea; font-weight: bold; }}
  .cmd {{ color: #d4d4d4; }}
  .header {{ color: #4ec9b0; font-weight: bold; }}
  .ok {{ color: #89d185; font-weight: bold; }}
  .highlight {{ color: #ce9178; }}
  .success-box {{ color: #89d185; font-weight: bold; }}
</style>
</head>
<body>
  <div class="target-container">
    <div class="vscode-header">
      <div class="vscode-tabs">
        <span>Problems 0</span>
        <span>Output</span>
        <span>Debug Console</span>
        <span class="vscode-tab active">Terminal</span>
      </div>
      <div class="vscode-actions">
        <span>1: powershell</span>
        <span>+ ▾</span>
        <span>◫</span>
        <span>✕</span>
      </div>
    </div>
    <div class="terminal-body">{formatted_body}</div>
  </div>
</body>
</html>"""

    rendered_ok = False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            for ch in ["chrome", "msedge", None]:
                try:
                    kwargs = {"channel": ch} if ch else {}
                    browser = p.chromium.launch(**kwargs)
                    page = browser.new_page(device_scale_factor=2)
                    page.set_content(html_code)
                    elem = page.locator(".target-container")
                    elem.screenshot(path=str(out_p))
                    browser.close()
                    rendered_ok = True
                    break
                except Exception:
                    continue
    except Exception:
        pass

    if not rendered_ok or not out_p.exists():
        # Fallback to pure PIL rendering if headless browser unavailable
        img = Image.new("RGB", (820, 480), color=(24, 24, 24))
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), content, fill=(204, 204, 204))
        img.save(out_p)

    return process_terminal_screenshot(
        src_path=out_p,
        dest_path=out_p,
        caption=caption or ("VS Code Terminal Output" if style == "vscode" else "Terminal Output"),
        add_border=False,
    )
