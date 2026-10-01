"""
text_chunking.py - Chia nhỏ văn bản thành các chunk phù hợp với context window của LLM.

Sử dụng LangChain RecursiveCharacterTextSplitter:
- Ưu tiên cắt theo đoạn văn (\n\n), sau đó theo dòng (\n), sau đó theo câu (. ? !).
- Đảm bảo mỗi chunk không vượt quá giới hạn token của model.
- Giữ overlap (phần chồng lấp) giữa các chunk để không mất ngữ cảnh.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter


# Cấu hình mặc định (phù hợp với Gemini 1.5 Flash / GPT-4o-mini)
DEFAULT_CHUNK_SIZE = 3000       # ~750 tokens (1 token ~ 4 ký tự)
DEFAULT_CHUNK_OVERLAP = 300     # Overlap 10% để giữ ngữ cảnh liền mạch
SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """
    Chia text thành các chunk nhỏ, giữ nguyên ngữ nghĩa.

    Args:
        text: Văn bản cần chia.
        chunk_size: Số ký tự tối đa mỗi chunk.
        chunk_overlap: Số ký tự chồng lấp giữa 2 chunk liên tiếp.

    Returns:
        list[str]: Danh sách các chunk text.
    """
    if not text or not text.strip():
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=SEPARATORS,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = splitter.split_text(text)
    return chunks


def chunk_pages_text(
    classified_pages: list,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    """
    Gom text từ tất cả các trang TEXT_HEAVY, sau đó chia chunk.

    Args:
        classified_pages: Danh sách ClassifiedPage từ classifier.

    Returns:
        list[dict]: Mỗi phần tử gồm:
            - chunk_index (int): Thứ tự chunk.
            - text (str): Nội dung chunk.
            - source_pages (list[int]): Các trang gốc mà chunk này thuộc về.
    """
    # Gom toàn bộ text từ các trang TEXT_HEAVY
    all_text_parts = []
    page_boundaries = []  # Lưu vị trí bắt đầu của mỗi trang trong chuỗi gộp

    for cp in classified_pages:
        if cp.page_type.value == "text_heavy" and cp.text.strip():
            start_pos = sum(len(t) + 2 for t in all_text_parts)  # +2 cho "\n\n"
            page_boundaries.append((start_pos, start_pos + len(cp.text), cp.page_number))
            all_text_parts.append(cp.text)

    if not all_text_parts:
        return []

    combined_text = "\n\n".join(all_text_parts)
    chunks = chunk_text(combined_text, chunk_size, chunk_overlap)

    # Map mỗi chunk về trang gốc
    result = []
    current_pos = 0
    for i, chunk in enumerate(chunks):
        chunk_start = combined_text.find(chunk, current_pos)
        chunk_end = chunk_start + len(chunk) if chunk_start >= 0 else current_pos + len(chunk)
        current_pos = max(current_pos, chunk_start + 1) if chunk_start >= 0 else current_pos

        source_pages = []
        for pb_start, pb_end, page_num in page_boundaries:
            if chunk_start < pb_end and chunk_end > pb_start:
                source_pages.append(page_num)

        result.append({
            "chunk_index": i,
            "text": chunk,
            "source_pages": source_pages if source_pages else [0],
            "char_count": len(chunk),
        })

    return result
