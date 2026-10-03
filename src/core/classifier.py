"""
classifier.py - Phan loai trang PDF: Text-heavy hay Visual-heavy.

Cai tien:
- Nhan biet trang da duoc OCR thanh cong (ocr_applied=True) -> xu ly nhu TEXT_HEAVY
- Bat cu anh nao song sot qua luoi loc rac -> deu la bieu do/so do quan trong
"""

from dataclasses import dataclass
from enum import Enum


class PageType(str, Enum):
    TEXT_HEAVY = "text_heavy"
    VISUAL_HEAVY = "visual_heavy"
    MIXED = "mixed"


@dataclass
class ClassifiedPage:
    page_number: int
    page_type: PageType
    text: str
    images: list[bytes]
    page_image: bytes | None
    confidence: float
    reason: str


TEXT_MIN_LENGTH = 30
TEXT_HEAVY_THRESHOLD = 200


def classify_page(page_data: dict) -> ClassifiedPage:
    """Phan loai 1 trang PDF dua tren heuristic."""
    text = page_data.get("text", "")
    images = page_data.get("images", [])
    page_image = page_data.get("page_image")
    has_text = page_data.get("has_text", False)
    ocr_applied = page_data.get("ocr_applied", False)
    text_len = len(text)
    num_images = len(images)

    # Case 1: Trang da duoc OCR thanh cong -> Co text roi, xu ly nhu TEXT
    if ocr_applied and has_text:
        return ClassifiedPage(
            page_number=page_data["page_number"],
            page_type=PageType.TEXT_HEAVY,
            text=text,
            images=images,
            page_image=page_image,
            confidence=0.85,
            reason=f"Trang scan da OCR thanh cong ({text_len} ky tu) -> dung Text LLM (tiet kiem).",
        )

    # Case 2: Khong co text va khong OCR duoc -> Visual
    if not has_text:
        return ClassifiedPage(
            page_number=page_data["page_number"],
            page_type=PageType.VISUAL_HEAVY,
            text=text,
            images=images,
            page_image=page_image,
            confidence=0.95,
            reason=f"Trang co rat it text ({text_len} ky tu) -> can Vision LLM.",
        )

    # Case 3: Co text + Co anh quan trong (da lot qua loc rac) -> MIXED
    if num_images > 0:
        if text_len < 300:
            return ClassifiedPage(
                page_number=page_data["page_number"],
                page_type=PageType.VISUAL_HEAVY,
                text=text,
                images=images,
                page_image=page_image,
                confidence=0.8,
                reason=f"Trang co {num_images} anh quan trong, text chi {text_len} ky tu -> Visual.",
            )
        return ClassifiedPage(
            page_number=page_data["page_number"],
            page_type=PageType.MIXED,
            text=text,
            images=images,
            page_image=page_image,
            confidence=0.7,
            reason=f"Trang hon hop: {text_len} ky tu + {num_images} anh -> can Vision LLM.",
        )

    # Case 4: Nhieu text, khong co anh -> TEXT_HEAVY
    return ClassifiedPage(
        page_number=page_data["page_number"],
        page_type=PageType.TEXT_HEAVY,
        text=text,
        images=images,
        page_image=page_image,
        confidence=0.9,
        reason=f"Trang co {text_len} ky tu, {num_images} anh -> dung Text LLM tiet kiem.",
    )


def classify_document(pages_data: list[dict]) -> list[ClassifiedPage]:
    """Phan loai toan bo document (tat ca cac trang)."""
    return [classify_page(p) for p in pages_data]


def get_routing_summary(classified_pages: list[ClassifiedPage]) -> dict:
    """Thong ke nhanh so trang theo tung loai."""
    summary = {"text_heavy": 0, "visual_heavy": 0, "mixed": 0, "total": len(classified_pages)}
    for cp in classified_pages:
        summary[cp.page_type.value] += 1
    return summary
