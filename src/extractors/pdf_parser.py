"""
pdf_parser.py (Đã nâng cấp: Lọc tọa độ + Đa cột + Diệt Logo Lặp Lại)
"""

import pymupdf as fitz
from pathlib import Path

MIN_IMAGE_WIDTH = 150
MIN_IMAGE_HEIGHT = 150
MIN_IMAGE_BYTES = 5000
MAX_DUPLICATE_BYTES = 50000 # Nếu ảnh lặp lại mà dung lượng < 50KB -> Chắc chắn là Logo

def extract_pages(pdf_path: str | Path) -> list[dict]:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file PDF: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    pages_data = []
    
    # --- VŨ KHÍ 2: THEO DÕI LOGO LẶP LẠI THEO DUNG LƯỢNG BYTE ---
    seen_image_sizes = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # 1. Đọc khối chữ, bỏ lề 10%
        page_height = page.rect.height
        margin_top = page_height * 0.10
        margin_bottom = page_height * 0.90
        
        blocks = page.get_text("blocks", sort=True)
        valid_text_blocks = []
        for b in blocks:
            x0, y0, x1, y1, block_text, block_no, block_type = b
            if block_type == 0:
                if y0 >= margin_top and y1 <= margin_bottom:
                    valid_text_blocks.append(block_text.strip())
        text = "\n".join(valid_text_blocks)

        # 2. Trích xuất và Lọc ảnh
        images = []
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                if not base_image or not base_image.get("image"):
                    continue

                img_bytes = base_image["image"]
                img_width = base_image.get("width", 0)
                img_height = base_image.get("height", 0)
                img_size = len(img_bytes)

                # Lọc theo kích thước tối thiểu
                if img_width < MIN_IMAGE_WIDTH or img_height < MIN_IMAGE_HEIGHT:
                    continue
                if img_size < MIN_IMAGE_BYTES:
                    continue
                    
                # Thuật toán lọc Logo lặp lại (Duplicate Heuristic)
                if img_size < MAX_DUPLICATE_BYTES:
                    if img_size in seen_image_sizes:
                        continue # Bỏ qua ảnh này vì dung lượng y hệt ảnh trang trước (Chắc chắn là logo lặp)
                    seen_image_sizes.add(img_size)

                images.append(img_bytes)
            except Exception:
                continue

        has_meaningful_text = len(text) > 30
        page_image = None
        if not has_meaningful_text:
            pix = page.get_pixmap(dpi=200)
            page_image = pix.tobytes("png")

        pages_data.append({
            "page_number": page_num + 1,
            "text": text,
            "images": images,
            "page_image": page_image,
            "has_text": has_meaningful_text,
        })

    doc.close()
    return pages_data

def get_pdf_metadata(pdf_path: str | Path) -> dict:
    doc = fitz.open(str(pdf_path))
    metadata = {
        "title": doc.metadata.get("title", ""),
        "author": doc.metadata.get("author", ""),
        "total_pages": len(doc),
        "file_size_mb": round(Path(pdf_path).stat().st_size / (1024 * 1024), 2),
    }
    doc.close()
    return metadata
