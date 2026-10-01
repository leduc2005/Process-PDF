"""
classifier.py - Phân loại trang PDF: Text-heavy hay Visual-heavy.

Heuristic Routing Logic:
- Nếu trang có nhiều text (>30 ký tự) VÀ ít ảnh -> TEXT_HEAVY -> gửi Text LLM (rẻ, nhanh).
- Nếu trang có nhiều ảnh/sơ đồ hoặc ít text -> VISUAL_HEAVY -> gửi Vision LLM (đắt, chính xác).
- Nếu trang hỗn hợp -> MIXED -> gửi cả text lẫn ảnh cho Vision LLM.

Mục đích: Tối ưu chi phí API bằng cách chỉ gọi Vision model khi thực sự cần thiết.
"""

from dataclasses import dataclass
from enum import Enum


class PageType(str, Enum):
    TEXT_HEAVY = "text_heavy"      # Chủ yếu là chữ -> dùng Text LLM
    VISUAL_HEAVY = "visual_heavy"  # Chủ yếu là hình/sơ đồ -> dùng Vision LLM
    MIXED = "mixed"                # Hỗn hợp cả chữ lẫn hình -> dùng Vision LLM


@dataclass
class ClassifiedPage:
    """Kết quả phân loại 1 trang PDF."""
    page_number: int
    page_type: PageType
    text: str
    images: list[bytes]
    page_image: bytes | None  # Ảnh render toàn trang (nếu cần gửi Vision)
    confidence: float         # Độ tin cậy phân loại (0.0 - 1.0)
    reason: str               # Lý do phân loại


# ----- Ngưỡng cấu hình (có thể tinh chỉnh theo thực nghiệm) -----
TEXT_MIN_LENGTH = 30          # Trang cần ít nhất 30 ký tự để coi là "có text"
TEXT_HEAVY_THRESHOLD = 200    # Trang >= 200 ký tự VÀ ít ảnh -> TEXT_HEAVY
IMAGE_COUNT_THRESHOLD = 2    # Trang có >= 2 ảnh nhúng -> nghiêng về VISUAL
TEXT_TO_IMAGE_RATIO = 100     # Mỗi ảnh "đáng giá" bao nhiêu ký tự text


def classify_page(page_data: dict) -> ClassifiedPage:
    """
    Phân loại 1 trang PDF dựa trên heuristic đơn giản.

    Args:
        page_data: dict từ pdf_parser.extract_pages(), gồm:
            page_number, text, images, page_image, has_text.

    Returns:
        ClassifiedPage: Kết quả phân loại.
    """
    text = page_data.get("text", "")
    images = page_data.get("images", [])
    page_image = page_data.get("page_image")
    has_text = page_data.get("has_text", False)
    text_len = len(text)
    num_images = len(images)

    # ---- Logic phân loại ----

    # Case 1: Không có text hoặc quá ít -> chắc chắn là scan/ảnh
    if not has_text:
        return ClassifiedPage(
            page_number=page_data["page_number"],
            page_type=PageType.VISUAL_HEAVY,
            text=text,
            images=images,
            page_image=page_image,
            confidence=0.95,
            reason=f"Trang có rất ít text ({text_len} ký tự) -> cần Vision LLM.",
        )

    # Case 2: Nhiều text, không có ảnh -> thuần text
    if text_len >= TEXT_HEAVY_THRESHOLD and num_images == 0:
        return ClassifiedPage(
            page_number=page_data["page_number"],
            page_type=PageType.TEXT_HEAVY,
            text=text,
            images=images,
            page_image=page_image,
            confidence=0.9,
            reason=f"Trang có {text_len} ký tự, 0 ảnh -> dùng Text LLM tiết kiệm.",
        )

    # Case 3: Có text nhưng cũng nhiều ảnh -> hỗn hợp
    if num_images >= IMAGE_COUNT_THRESHOLD:
        # Nếu text quá ít so với số ảnh -> VISUAL
        if text_len < num_images * TEXT_TO_IMAGE_RATIO:
            return ClassifiedPage(
                page_number=page_data["page_number"],
                page_type=PageType.VISUAL_HEAVY,
                text=text,
                images=images,
                page_image=page_image,
                confidence=0.8,
                reason=f"Trang có {num_images} ảnh, text chỉ {text_len} ký tự -> ảnh chiếm ưu thế.",
            )
        return ClassifiedPage(
            page_number=page_data["page_number"],
            page_type=PageType.MIXED,
            text=text,
            images=images,
            page_image=page_image,
            confidence=0.7,
            reason=f"Trang hỗn hợp: {text_len} ký tự + {num_images} ảnh -> cần Vision LLM.",
        )

    # Case 4: Có text đủ nhiều, ít ảnh -> TEXT_HEAVY
    return ClassifiedPage(
        page_number=page_data["page_number"],
        page_type=PageType.TEXT_HEAVY,
        text=text,
        images=images,
        page_image=page_image,
        confidence=0.85,
        reason=f"Trang có {text_len} ký tự, {num_images} ảnh -> dùng Text LLM.",
    )


def classify_document(pages_data: list[dict]) -> list[ClassifiedPage]:
    """Phân loại toàn bộ document (tất cả các trang)."""
    return [classify_page(p) for p in pages_data]


def get_routing_summary(classified_pages: list[ClassifiedPage]) -> dict:
    """Thống kê nhanh số trang theo từng loại để báo cáo."""
    summary = {"text_heavy": 0, "visual_heavy": 0, "mixed": 0, "total": len(classified_pages)}
    for cp in classified_pages:
        summary[cp.page_type.value] += 1
    return summary
