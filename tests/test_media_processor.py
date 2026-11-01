"""Unit tests for the authentic media and terminal screenshot processor."""

from pathlib import Path
import pytest
from PIL import Image, ImageDraw

from classroom.media_processor import (
    ProcessedImage,
    autocrop_border,
    calculate_print_dimensions,
    process_diagram,
    process_image,
    process_terminal_screenshot,
    render_terminal_screenshot,
)


@pytest.fixture
def temp_media_dir(tmp_path: Path) -> Path:
    """Fixture providing a temporary directory for test media."""
    media_dir = tmp_path / "media_test"
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir


@pytest.fixture
def sample_terminal_screenshot(temp_media_dir: Path) -> Path:
    """Create an authentic-looking terminal screenshot (dark background with text-like colored blocks)."""
    img_path = temp_media_dir / "authentic_terminal.png"
    # Dark terminal theme (#1e1e2e)
    width, height = 1920, 1080
    img = Image.new("RGB", (width, height), color="#1e1e2e")
    draw = ImageDraw.Draw(img)
    # Draw terminal prompt and command-like pixels
    draw.rectangle([50, 50, 200, 70], fill="#89b4fa")  # user@host
    draw.rectangle([210, 50, 400, 70], fill="#a6e3a1")  # command
    draw.rectangle([50, 90, 800, 110], fill="#cdd6f4")  # output
    img.save(img_path)
    return img_path


@pytest.fixture
def sample_diagram_image(temp_media_dir: Path) -> Path:
    """Create a sample diagram with white background and colored geometric shapes."""
    img_path = temp_media_dir / "system_diagram.png"
    width, height = 1200, 800
    img = Image.new("RGB", (width, height), color="#ffffff")
    draw = ImageDraw.Draw(img)
    # Draw diagram elements
    draw.rectangle([100, 100, 400, 300], fill="#3b82f6", outline="#1d4ed8", width=3)
    draw.rectangle([700, 100, 1000, 300], fill="#10b981", outline="#047857", width=3)
    draw.line([400, 200, 700, 200], fill="#64748b", width=4)
    img.save(img_path)
    return img_path


@pytest.fixture
def image_with_whitespace_borders(temp_media_dir: Path) -> Path:
    """Create an image with wide white exterior margins around a central graphic."""
    img_path = temp_media_dir / "padded_graphic.png"
    total_w, total_h = 1000, 1000
    img = Image.new("RGB", (total_w, total_h), color="#ffffff")
    draw = ImageDraw.Draw(img)
    # Graphic in center: (300, 300) to (700, 700) -> 400x400
    draw.rectangle([300, 300, 700, 700], fill="#ef4444")
    img.save(img_path)
    return img_path


class TestProcessedImageDataclass:
    """Tests for ProcessedImage dataclass structure and properties."""

    def test_instantiation(self, tmp_path: Path):
        p = tmp_path / "img.png"
        proc = ProcessedImage(
            path=p,
            width=1600,
            height=900,
            aspect_ratio=1600 / 900,
            caption="Test Caption",
        )
        assert proc.path == p
        assert proc.width == 1600
        assert proc.height == 900
        assert pytest.approx(proc.aspect_ratio, rel=1e-3) == 1.7777
        assert proc.caption == "Test Caption"

    def test_caption_optional(self, tmp_path: Path):
        p = tmp_path / "img.png"
        proc = ProcessedImage(
            path=p,
            width=800,
            height=600,
            aspect_ratio=800 / 600,
        )
        assert proc.caption is None


class TestAutocrop:
    """Tests for exterior margin and whitespace auto-cropping."""

    def test_autocrop_removes_white_border(self, image_with_whitespace_borders: Path):
        img = Image.open(image_with_whitespace_borders)
        cropped = autocrop_border(img, tolerance=10)
        # Content was 400x400 centered in 1000x1000
        # The cropped image should match the content bounding box (401x401 due to inclusive borders)
        assert cropped.width < 500
        assert cropped.height < 500
        assert cropped.width >= 400
        assert cropped.height >= 400

    def test_autocrop_uniform_image(self, temp_media_dir: Path):
        """Autocropping an image with no variation returns the original image or minimal canvas."""
        blank_path = temp_media_dir / "solid.png"
        img = Image.new("RGB", (200, 200), color="#ffffff")
        img.save(blank_path)
        cropped = autocrop_border(img)
        assert cropped.width == 200
        assert cropped.height == 200


class TestProcessTerminalScreenshot:
    """Tests for authentic terminal screenshot processing."""

    def test_terminal_screenshot_default_border_and_scaling(
        self, sample_terminal_screenshot: Path, temp_media_dir: Path
    ):
        dest = temp_media_dir / "out" / "terminal_processed.png"
        result = process_terminal_screenshot(
            sample_terminal_screenshot,
            dest,
            caption="Terminal executing git status",
            max_width=1600,
        )

        assert dest.exists()
        assert result.path == dest
        assert result.caption == "Terminal executing git status"
        # Original was 1920x1080 -> aspect ratio 16:9
        # Scaled to max_width 1600: 1600 x 900
        # Plus 1px border on all sides (+2 width, +2 height) -> 1602 x 902
        assert result.width == 1602
        assert result.height == 902
        assert pytest.approx(result.aspect_ratio, rel=1e-2) == 1602 / 902

        # Verify border color on edge pixel
        with Image.open(dest) as out_img:
            # Border is #334155 -> RGB (51, 65, 85)
            pixel = out_img.getpixel((0, 0))
            assert pixel[:3] == (51, 65, 85)

    def test_terminal_screenshot_without_border(
        self, sample_terminal_screenshot: Path, temp_media_dir: Path
    ):
        dest = temp_media_dir / "out" / "terminal_no_border.png"
        result = process_terminal_screenshot(
            sample_terminal_screenshot,
            dest,
            add_border=False,
            max_width=1600,
        )

        assert result.width == 1600
        assert result.height == 900
        assert pytest.approx(result.aspect_ratio, rel=1e-3) == 1.7777

    def test_terminal_screenshot_custom_border_styling(
        self, sample_terminal_screenshot: Path, temp_media_dir: Path
    ):
        dest = temp_media_dir / "out" / "terminal_custom_border.png"
        result = process_terminal_screenshot(
            sample_terminal_screenshot,
            dest,
            add_border=True,
            border_color="#ff0000",
            border_width=3,
            max_width=800,
        )
        # Scaled to 800 x 450 + 6px border -> 806 x 456
        assert result.width == 806
        assert result.height == 456
        with Image.open(dest) as out_img:
            pixel = out_img.getpixel((0, 0))
            assert pixel[:3] == (255, 0, 0)


class TestProcessDiagram:
    """Tests for architectural diagram processing."""

    def test_diagram_processing_defaults(
        self, sample_diagram_image: Path, temp_media_dir: Path
    ):
        dest = temp_media_dir / "out" / "diagram_processed.png"
        result = process_diagram(
            sample_diagram_image,
            dest,
            caption="High-level architecture",
            max_width=1600,
        )

        assert dest.exists()
        assert result.caption == "High-level architecture"
        # Diagram was 1200x800 -> fits within 1600 max width, so width preserved
        assert result.width == 1200
        assert result.height == 800
        assert pytest.approx(result.aspect_ratio, rel=1e-3) == 1.5

    def test_diagram_autocrop_whitespace(
        self, image_with_whitespace_borders: Path, temp_media_dir: Path
    ):
        dest = temp_media_dir / "out" / "diagram_autocropped.png"
        result = process_diagram(
            image_with_whitespace_borders,
            dest,
            autocrop=True,
            caption="Cropped diagram",
        )
        assert result.width < 500
        assert result.height < 500
        assert result.caption == "Cropped diagram"


class TestGeneralProcessImage:
    """Tests for generic process_image features."""

    def test_file_not_found(self, temp_media_dir: Path):
        with pytest.raises(FileNotFoundError):
            process_image(
                temp_media_dir / "non_existent.png",
                temp_media_dir / "out.png",
            )

    def test_directory_auto_creation(self, sample_diagram_image: Path, temp_media_dir: Path):
        deep_dest = temp_media_dir / "sub1" / "sub2" / "deep_processed.png"
        result = process_image(sample_diagram_image, deep_dest)
        assert deep_dest.exists()
        assert result.path == deep_dest

    def test_aspect_ratio_preservation_tall_image(self, temp_media_dir: Path):
        tall_path = temp_media_dir / "tall.png"
        img = Image.new("RGB", (1000, 4000), color="#123456")
        img.save(tall_path)

        dest = temp_media_dir / "tall_scaled.png"
        result = process_image(
            tall_path,
            dest,
            max_width=500,
            max_height=1000,
        )
        # 1000x4000 has 1:4 aspect ratio.
        # Max width 500 would give 500x2000, but max height is 1000, so fits in 250x1000
        assert result.width == 250
        assert result.height == 1000
        assert pytest.approx(result.aspect_ratio, rel=1e-3) == 0.25

    def test_rgba_to_jpeg_conversion(self, temp_media_dir: Path):
        rgba_path = temp_media_dir / "alpha.png"
        img = Image.new("RGBA", (400, 300), color=(255, 0, 0, 128))
        img.save(rgba_path)

        dest_jpg = temp_media_dir / "alpha_converted.jpg"
        result = process_image(rgba_path, dest_jpg)
        assert dest_jpg.exists()
        assert result.width == 400
        assert result.height == 300

        with Image.open(dest_jpg) as out_img:
            assert out_img.mode == "RGB"

    def test_padding_and_border_combination(self, sample_diagram_image: Path, temp_media_dir: Path):
        dest = temp_media_dir / "padded_bordered.png"
        result = process_image(
            sample_diagram_image,
            dest,
            padding=10,
            padding_color="#ffffff",
            add_border=True,
            border_color="#334155",
            border_width=2,
            max_width=1200,
        )
        # Original: 1200 x 800
        # Scaled first (fits in 1200): 1200 x 800
        # Padding +10 all sides (+20) -> 1220 x 820
        # Border +2 all sides (+4) -> 1224 x 824
        assert result.width == 1224
        assert result.height == 824


class TestPrintDimensionsHelper:
    """Tests for printable page dimensions calculation."""

    def test_calculate_print_dimensions_standard(self, tmp_path: Path):
        proc = ProcessedImage(
            path=tmp_path / "img.png",
            width=1600,
            height=900,
            aspect_ratio=1600 / 900,
        )
        # Default printable width is 500 pt
        pt_w, pt_h = calculate_print_dimensions(proc, max_pt_width=500.0)
        assert pt_w == 500.0
        assert pytest.approx(pt_h, rel=1e-2) == 500.0 / (1600 / 900)

    def test_calculate_print_dimensions_with_height_constraint(self, tmp_path: Path):
        proc = ProcessedImage(
            path=tmp_path / "img.png",
            width=400,
            height=1200,
            aspect_ratio=400 / 1200,
        )
        pt_w, pt_h = calculate_print_dimensions(proc, max_pt_width=500.0, max_pt_height=600.0)
        assert pt_h == 600.0
        assert pytest.approx(pt_w, rel=1e-2) == 200.0


class TestRenderTerminalScreenshot:
    """Tests for authentic terminal screenshot rendering (Candidate 2 and Candidate 4)."""

    def test_render_terminal_screenshot_vscode_style(self, tmp_path: Path):
        dest = tmp_path / "term_vscode.png"
        sample_output = "[*] Verifying RSA Key Pair:\n    Public Key -> [OK] Validated\n[SUCCESS] Decryption verified!"
        res = render_terminal_screenshot(
            content=sample_output,
            dest_path=dest,
            style="vscode",
            command="python verify_rsa.py",
        )
        assert res.path.exists()
        assert res.width > 300
        assert res.height > 100
        assert res.caption == "VS Code Terminal Output"

    def test_render_terminal_screenshot_frameless_style(self, tmp_path: Path):
        dest = tmp_path / "term_frameless.png"
        sample_output = "[*] Ping Test: 4/4 packets received\n[SUCCESS] Latency 0.4ms"
        res = render_terminal_screenshot(
            content=sample_output,
            dest_path=dest,
            style="frameless",
            command="ping 192.168.1.1",
        )
        assert res.path.exists()
        assert res.width > 300
        assert res.height > 100
        assert res.caption == "Terminal Output"

