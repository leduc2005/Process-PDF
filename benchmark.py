"""
benchmark.py - Script chạy toàn bộ pipeline PDF Processing.

Luồng xử lý:
1. Đọc tất cả file PDF trong thư mục dataset/
2. Trích xuất text & ảnh từ mỗi file (pdf_parser)
3. Phân loại từng trang: Text-heavy hay Visual-heavy (classifier)
4. Tiền xử lý ảnh nếu cần (vision_cv)
5. Chia chunk text (text_chunking)
6. Gọi AI tạo Summary + Quiz (ai_router)
7. Lưu kết quả JSON vào outputs/
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime

# Thêm thư mục gốc vào sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.extractors.pdf_parser import extract_pages, get_pdf_metadata
from src.core.classifier import classify_document, get_routing_summary, PageType
from src.core.vision_cv import preprocess_for_vision
from src.core.text_chunking import chunk_pages_text
from src.ai_router import generate_summary, generate_quiz, analyze_visual_page


def process_single_pdf(pdf_path: Path, output_dir: Path) -> dict:
    """Xử lý 1 file PDF qua toàn bộ pipeline."""
    print(f"\n{'='*60}")
    print(f"📄 Đang xử lý: {pdf_path.name}")
    print(f"{'='*60}")
    start_time = time.time()

    # ---- Bước 1: Metadata ----
    metadata = get_pdf_metadata(pdf_path)
    print(f"  📊 Metadata: {metadata['total_pages']} trang, {metadata['file_size_mb']} MB")

    # ---- Bước 2: Trích xuất text & ảnh ----
    print("  📖 Đang trích xuất text & ảnh từ PDF...")
    pages_data = extract_pages(pdf_path)

    # ---- Bước 3: Phân loại từng trang ----
    print("  🔍 Đang phân loại từng trang (Text vs Visual)...")
    classified_pages = classify_document(pages_data)
    routing_summary = get_routing_summary(classified_pages)
    print(f"     → Text: {routing_summary['text_heavy']} trang | "
          f"Visual: {routing_summary['visual_heavy']} trang | "
          f"Mixed: {routing_summary['mixed']} trang")

    # ---- Bước 4: Tiền xử lý ảnh (cho Visual pages) ----
    vision_results = []
    for cp in classified_pages:
        if cp.page_type in (PageType.VISUAL_HEAVY, PageType.MIXED):
            image_to_process = cp.page_image or (cp.images[0] if cp.images else None)
            if image_to_process:
                print(f"  🖼️  Tiền xử lý ảnh trang {cp.page_number}...")
                cv_result = preprocess_for_vision(image_to_process)
                print(f"     → Blur score: {cv_result['blur_score']} | "
                      f"Mờ: {'Có' if cv_result['is_blurry'] else 'Không'} | "
                      f"Bước xử lý: {cv_result['steps_applied']}")

                # Gọi Vision LLM phân tích trang ảnh
                print(f"  🤖 Gọi Vision LLM phân tích trang {cp.page_number}...")
                vision_analysis = analyze_visual_page(cv_result["processed_image"])
                vision_results.append({
                    "page_number": cp.page_number,
                    "analysis": vision_analysis,
                    "blur_score": cv_result["blur_score"],
                })

    # ---- Bước 5: Chia chunk text ----
    print("  ✂️  Đang chia chunk text...")
    text_chunks = chunk_pages_text(classified_pages)
    print(f"     → Tổng {len(text_chunks)} chunk")

    # ---- Bước 6: Gọi AI tạo Summary & Quiz ----
    all_text = "\n\n".join([c["text"] for c in text_chunks]) if text_chunks else ""

    # Bổ sung text từ Vision analysis vào
    for vr in vision_results:
        if isinstance(vr["analysis"], dict) and "page_description" in vr["analysis"]:
            all_text += "\n\n" + vr["analysis"]["page_description"]

    summary_result = {}
    quiz_result = {}

    if all_text.strip():
        print("  📝 Gọi AI tạo Summary (Micro-learning)...")
        summary_result = generate_summary(all_text)

        print("  ❓ Gọi AI tạo Quiz (trắc nghiệm)...")
        quiz_result = generate_quiz(all_text, num_questions=5)
    else:
        print("  ⚠️  Không có text để xử lý AI!")

    elapsed = round(time.time() - start_time, 2)
    print(f"  ⏱️  Hoàn thành trong {elapsed}s")

    # ---- Bước 7: Ghi kết quả ----
    result = {
        "file_name": pdf_path.name,
        "metadata": metadata,
        "routing_summary": routing_summary,
        "text_chunks_count": len(text_chunks),
        "vision_pages_analyzed": len(vision_results),
        "ocr_pages_count": len([p for p in pages_data if p.get("ocr_applied")]),
        "vision_results": vision_results,
        "summary": summary_result,
        "quiz": quiz_result,
        "processing_time_seconds": elapsed,
        "timestamp": datetime.now().isoformat(),
    }

    output_file = output_dir / f"{pdf_path.stem}_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  💾 Kết quả lưu tại: {output_file}")

    return result


def main():
    """Chạy benchmark trên tất cả PDF trong thư mục dataset/."""
    dataset_dir = Path(__file__).parent / "dataset"
    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(exist_ok=True)

    pdf_files = list(dataset_dir.glob("*.pdf"))

    if not pdf_files:
        print("⚠️  Không tìm thấy file PDF nào trong thư mục dataset/")
        print(f"   Hãy đặt file PDF vào: {dataset_dir.absolute()}")
        return

    print(f"🚀 Tìm thấy {len(pdf_files)} file PDF. Bắt đầu xử lý...")

    results = []
    for pdf_file in pdf_files:
        try:
            result = process_single_pdf(pdf_file, output_dir)
            results.append(result)
        except Exception as e:
            print(f"  ❌ Lỗi khi xử lý {pdf_file.name}: {e}")
            results.append({"file_name": pdf_file.name, "error": str(e)})

    # Ghi tổng kết
    report = {
        "total_files": len(pdf_files),
        "successful": sum(1 for r in results if "error" not in r),
        "failed": sum(1 for r in results if "error" in r),
        "results_summary": [
            {
                "file": r.get("file_name", "?"),
                "pages": r.get("metadata", {}).get("total_pages", 0),
                "time": r.get("processing_time_seconds", 0),
                "has_summary": bool(r.get("summary")),
                "has_quiz": bool(r.get("quiz")),
            }
            for r in results
        ],
    }

    report_file = output_dir / "_benchmark_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ HOÀN TẤT! Xử lý {report['successful']}/{report['total_files']} file thành công.")
    print(f"📂 Kết quả lưu tại: {output_dir.absolute()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

