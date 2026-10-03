"""
pdf_parser.py - Trich xuat text va anh tu file PDF.

Cai tien:
1. Doc van ban theo Block & ho tro Da cot (sort=True).
2. Loc Header/Footer dua tren toa do Y (Cat 10% le tren, 10% le duoi).
3. Loc rac kich thuoc anh (Icon, Logo) + Diet Logo lap lai (Duplicate Hashing).
4. Selective OCR: Chi chay Tesseract tren trang KHONG co text (scan pages).
   Trang co text san -> bo qua OCR hoan toan -> tiet kiem thoi gian & tai nguyen.
"""

import pymupdf as fitz
from pathlib import Path
from io import BytesIO

# ---- Nguong loc anh rac ----
MIN_IMAGE_WIDTH = 150
MIN_IMAGE_HEIGHT = 150
MIN_IMAGE_BYTES = 5000
MAX_DUPLICATE_BYTES = 50000

# ---- OCR Config ----
OCR_ENABLED = True
OCR_MIN_TEXT_LENGTH = 30

# Thu import pytesseract
try:
    import pytesseract
    from PIL import Image
    _tesseract_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for _path in _tesseract_paths:
        if Path(_path).exists():
            pytesseract.pytesseract.tesseract_cmd = _path
            break
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    print("[pdf_parser] pytesseract chua cai. OCR bi tat. pip install pytesseract")


def _run_ocr_on_image(image_bytes: bytes) -> str:
    """Chay Tesseract OCR tren anh trang PDF de lay text tu ban scan."""
    if not HAS_TESSERACT:
        return ""
    try:
        img = Image.open(BytesIO(image_bytes))
        try:
            text = pytesseract.image_to_string(img, lang="vie+eng")
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(img, lang="eng")
        return text.strip()
    except Exception as e:
        print(f"  [OCR] Loi OCR: {e}")
        return ""


def extract_pages(pdf_path: str | Path) -> list[dict]:
    """
    Trich xuat text va anh tu file PDF.
    
    Quy trinh Selective OCR:
    1. Thu boc text bang PyMuPDF (nhanh, mien phi).
    2. Neu trang khong co text (< 30 ky tu) -> day la trang scan -> chay OCR.
    3. Neu OCR thu duoc nhieu chu -> chuyen luong ve nhanh Text LLM (re).
       Neu OCR thu duoc it chu -> giu nguyen la Visual (gui anh cho Vision LLM).
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Khong tim thay file PDF: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    pages_data = []
    seen_image_sizes = set()

    for page_num in range(len(doc)):
        page = doc[page_num]

        # === BUOC 1: Doc text theo Block, bo le 10%, ho tro da cot ===
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

        # === BUOC 2: Trich xuat va Loc anh rac ===
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

                if img_width < MIN_IMAGE_WIDTH or img_height < MIN_IMAGE_HEIGHT:
                    continue
                if img_size < MIN_IMAGE_BYTES:
                    continue

                if img_size < MAX_DUPLICATE_BYTES:
                    if img_size in seen_image_sizes:
                        continue
                    seen_image_sizes.add(img_size)

                images.append(img_bytes)
            except Exception:
                continue

        # === BUOC 3: Selective OCR - Chi OCR khi trang khong co text ===
        has_meaningful_text = len(text) > OCR_MIN_TEXT_LENGTH
        page_image = None
        ocr_applied = False

        if not has_meaningful_text:
            pix = page.get_pixmap(dpi=200)
            page_image = pix.tobytes("png")

            if OCR_ENABLED and HAS_TESSERACT:
                print(f"  [OCR] Trang {page_num + 1}: Khong co text -> Chay Tesseract OCR...")
                ocr_text = _run_ocr_on_image(page_image)

                if len(ocr_text) > OCR_MIN_TEXT_LENGTH:
                    text = ocr_text
                    has_meaningful_text = True
                    ocr_applied = True
                    print(f"       -> OCR thanh cong! Lay duoc {len(ocr_text)} ky tu -> Chuyen sang Text LLM (tiet kiem)")
                else:
                    print(f"       -> OCR chi lay duoc {len(ocr_text)} ky tu -> Giu nguyen Visual cho Vision LLM")

        pages_data.append({
            "page_number": page_num + 1,
            "text": text,
            "images": images,
            "page_image": page_image,
            "has_text": has_meaningful_text,
            "ocr_applied": ocr_applied,
        })

    doc.close()
    return pages_data


def get_pdf_metadata(pdf_path: str | Path) -> dict:
    """Lay metadata co ban cua file PDF."""
    doc = fitz.open(str(pdf_path))
    metadata = {
        "title": doc.metadata.get("title", ""),
        "author": doc.metadata.get("author", ""),
        "total_pages": len(doc),
        "file_size_mb": round(Path(pdf_path).stat().st_size / (1024 * 1024), 2),
    }
    doc.close()
    return metadata
