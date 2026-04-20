#!/usr/bin/env python3
"""Preview layout algorithm with test cases.

Generates preview PDFs for different photo count scenarios to validate layout quality.
Run from the project root: python scripts/preview_layouts.py

Usage:
    python scripts/preview_layouts.py
    # Generates preview PDFs in scripts/preview_layouts/ directory
"""

import sys
import tempfile
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader

from src.render.layout import compute_layout


def create_test_images(count: int, orientations: list[str] | None = None) -> list[Path]:
    """Create test images with specified orientations.
    
    Args:
        count: Number of images to create
        orientations: List of 'portrait' or 'landscape' (default: mix)
        
    Returns:
        List of Path objects to temporary image files
    """
    if orientations is None:
        # Default: mix of orientations
        orientations = ['portrait' if i % 2 == 0 else 'landscape' for i in range(count)]
    
    images = []
    for i in range(count):
        orientation = orientations[i] if i < len(orientations) else 'portrait'
        
        if orientation == 'portrait':
            size = (600, 800)
            color = (220, 100, 100)
        else:
            size = (800, 600)
            color = (100, 150, 220)
        
        img = Image.new('RGB', size, color)
        draw = ImageDraw.Draw(img)
        text = f"Image {i+1}"
        draw.text((size[0]//2 - 30, size[1]//2 - 10), text, fill=(255, 255, 255))
        
        tmp = Path(tempfile.gettempdir()) / f"test_img_{i:02d}.jpg"
        img.save(str(tmp), quality=85)
        images.append(tmp)
    
    return images


def render_preview_page(canvas: Canvas, layout_name: str, image_paths: list[Path], 
                       seed: int, layout_mode: str = "grid_compacto") -> None:
    """Render a single page with photos using the new layout algorithm."""
    title = f"{layout_name} ({len(image_paths)} photos)"
    
    # Draw background
    canvas.setFillColor(canvas.getPageNumber() % 2 == 0 and (0.95, 0.95, 0.95) or (1, 1, 1))
    canvas.rect(0, 0, *A4, fill=1, stroke=0)
    
    # Draw title
    canvas.setFont("Helvetica", 16)
    canvas.drawString(50, A4[1] - 40, title)
    
    # Compute layout
    placed = compute_layout(
        image_paths,
        seed=seed,
        layout_mode=layout_mode,
        has_title=True,
    )
    
    # Render photos
    for photo in placed:
        try:
            reader = ImageReader(str(photo.path))
            canvas.saveState()
            canvas.translate(photo.x + photo.w / 2, photo.y + photo.h / 2)
            canvas.rotate(photo.rotation)
            canvas.drawImage(
                reader,
                -photo.w / 2,
                -photo.h / 2,
                width=photo.w,
                height=photo.h,
                preserveAspectRatio=True,
            )
            canvas.restoreState()
            
            # Draw border
            canvas.setLineWidth(2)
            canvas.setStrokeColor((0.8, 0.8, 0.8))
            canvas.rect(photo.x, photo.y, photo.w, photo.h, fill=0)
        except Exception as e:
            print(f"  Warning: Could not render {photo.path}: {e}")
    
    canvas.showPage()


def main():
    output_dir = Path(__file__).parent / "preview_layouts"
    output_dir.mkdir(exist_ok=True)
    
    pdf_path = output_dir / "layout_previews.pdf"
    canvas = Canvas(str(pdf_path), pagesize=A4)
    
    test_cases = [
        ("3 Mixed", 3, ['portrait', 'landscape', 'portrait']),
        ("4 Mixed (2x2 case)", 4, ['portrait', 'portrait', 'landscape', 'landscape']),
        ("5 Mixed", 5, ['portrait'] * 5),
        ("6 Portrait", 6, ['portrait'] * 6),
        ("7 Portrait", 7, ['portrait'] * 7),
        ("8 Portrait", 8, ['portrait'] * 8),
        ("9 Portrait (3x3)", 9, ['portrait'] * 9),
        ("6 Landscape", 6, ['landscape'] * 6),
    ]
    
    for name, count, orientations in test_cases:
        print(f"Generating preview: {name}")
        try:
            images = create_test_images(count, orientations)
            render_preview_page(canvas, name, images, seed=42 + count, layout_mode="grid_compacto")
            # Clean up temp images
            for img in images:
                img.unlink()
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
    
    canvas.save()
    print(f"\nPreview PDF saved to: {pdf_path}")
    print("Open this file to visually inspect the layouts.")


if __name__ == "__main__":
    main()
