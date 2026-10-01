"""
compare_models.py - So sánh output giữa gemini-3.8-flash và gemini-3.5-flash-lite.

Chạy cùng 1 file PDF qua cả 2 model, đo:
- Thời gian xử lý (Latency)
- Chất lượng JSON output (Parse thành công hay không)
- Số lượng câu hỏi Quiz sinh được
- Độ dài Summary
- Token usage (nếu API trả về)
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from src.extractors.pdf_parser import extract_pages, get_pdf_metadata
from src.core.classifier import classify_document, get_routing_summary, PageType
from src.core.vision_cv import preprocess_for_vision
from src.core.text_chunking import chunk_pages_text
from src.ai_router import generate_summary, generate_quiz, analyze_visual_page


MODELS_TO_COMPARE = [
    {"name": "gemini-3.1-flash-lite", "litellm_id": "gemini/gemini-3.1-flash-lite", "tier": "Flash Lite 3.1 (Older)"},
    {"name": "gemini-3.5-flash-lite", "litellm_id": "gemini/gemini-3.5-flash-lite", "tier": "Flash Lite (Budget)"},
]


def run_model_on_text(all_text: str, model_info: dict, vision_pages: list) -> dict:
    """Chạy 1 model trên text + vision pages, đo thời gian và chất lượng."""
    model_id = model_info["litellm_id"]
    result = {"model": model_info["name"], "tier": model_info["tier"]}

    # --- Summary ---
    t0 = time.time()
    summary = generate_summary(all_text, model=model_id)
    summary_time = round(time.time() - t0, 2)

    result["summary"] = {
        "time_seconds": summary_time,
        "success": "parse_error" not in summary and "error" not in summary,
        "title": summary.get("title", "N/A"),
        "num_points": len(summary.get("summary_points", [])),
        "num_concepts": len(summary.get("key_concepts", [])),
        "data": summary,
    }

    # --- Quiz ---
    t0 = time.time()
    quiz = generate_quiz(all_text, num_questions=5, model=model_id)
    quiz_time = round(time.time() - t0, 2)

    questions = quiz.get("questions", [])
    result["quiz"] = {
        "time_seconds": quiz_time,
        "success": "parse_error" not in quiz and "error" not in quiz,
        "num_questions": len(questions),
        "json_valid": not quiz.get("parse_error", False),
        "data": quiz,
    }

    # --- Vision (nếu có) ---
    vision_results = []
    vision_total_time = 0
    for vp in vision_pages:
        t0 = time.time()
        va = analyze_visual_page(vp["image"], model=model_id)
        vt = round(time.time() - t0, 2)
        vision_total_time += vt
        vision_results.append({
            "page": vp["page"],
            "time_seconds": vt,
            "success": "parse_error" not in va and "error" not in va,
            "data": va,
        })

    result["vision"] = {
        "total_time_seconds": round(vision_total_time, 2),
        "pages_analyzed": len(vision_results),
        "details": vision_results,
    }

    result["total_time_seconds"] = round(summary_time + quiz_time + vision_total_time, 2)
    return result


def main():
    dataset_dir = Path(__file__).parent / "dataset"
    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(exist_ok=True)

    pdf_files = list(dataset_dir.glob("*.pdf"))
    if not pdf_files:
        print("Khong co file PDF nao trong dataset/")
        return

    # Chọn file đầu tiên để so sánh (hoặc có thể truyền argument)
    target = pdf_files[0]
    if len(sys.argv) > 1:
        for pf in pdf_files:
            if sys.argv[1].lower() in pf.name.lower():
                target = pf
                break

    print(f"{'='*70}")
    print(f"  SO SANH 2 MODEL TREN FILE: {target.name}")
    print(f"{'='*70}")

    # Bước 1-4: Xử lý chung (Extract, Classify, Vision preprocess, Chunk)
    metadata = get_pdf_metadata(target)
    print(f"\n  Metadata: {metadata['total_pages']} trang, {metadata['file_size_mb']} MB")

    pages_data = extract_pages(target)
    classified_pages = classify_document(pages_data)
    routing = get_routing_summary(classified_pages)
    print(f"  Routing: Text={routing['text_heavy']} | Visual={routing['visual_heavy']} | Mixed={routing['mixed']}")

    # Chuẩn bị Vision pages
    vision_pages = []
    for cp in classified_pages:
        if cp.page_type in (PageType.VISUAL_HEAVY, PageType.MIXED):
            img = cp.page_image or (cp.images[0] if cp.images else None)
            if img:
                cv_result = preprocess_for_vision(img)
                vision_pages.append({"page": cp.page_number, "image": cv_result["processed_image"]})

    # Chuẩn bị text
    text_chunks = chunk_pages_text(classified_pages)
    all_text = "\n\n".join([c["text"] for c in text_chunks]) if text_chunks else ""
    print(f"  Text chunks: {len(text_chunks)} | Vision pages: {len(vision_pages)}")

    # Bước 5: Chạy từng model
    comparison = {
        "file": target.name,
        "metadata": metadata,
        "routing": routing,
        "text_chunks": len(text_chunks),
        "vision_pages_count": len(vision_pages),
        "models": [],
    }

    for model_info in MODELS_TO_COMPARE:
        print(f"\n  {'─'*50}")
        print(f"  Dang chay model: {model_info['name']} ({model_info['tier']})")
        print(f"  {'─'*50}")

        result = run_model_on_text(all_text, model_info, vision_pages)

        s = result["summary"]
        q = result["quiz"]
        v = result["vision"]

        print(f"    Summary: {'OK' if s['success'] else 'FAIL'} | {s['time_seconds']}s | {s['num_points']} diem | Title: {s['title'][:50]}")
        print(f"    Quiz:    {'OK' if q['success'] else 'FAIL'} | {q['time_seconds']}s | {q['num_questions']} cau | JSON valid: {q['json_valid']}")
        print(f"    Vision:  {v['pages_analyzed']} trang | {v['total_time_seconds']}s")
        print(f"    TONG:    {result['total_time_seconds']}s")

        comparison["models"].append(result)

    # Bảng so sánh
    print(f"\n{'='*70}")
    print(f"  BANG SO SANH TONG HOP")
    print(f"{'='*70}")
    print(f"  {'Metric':<30} {'gemini-3.8-flash':>18} {'gemini-3.5-flash-lite':>22}")
    print(f"  {'─'*70}")

    m1 = comparison["models"][0]
    m2 = comparison["models"][1]

    rows = [
        ("Tong thoi gian (s)", m1["total_time_seconds"], m2["total_time_seconds"]),
        ("Summary time (s)", m1["summary"]["time_seconds"], m2["summary"]["time_seconds"]),
        ("Quiz time (s)", m1["quiz"]["time_seconds"], m2["quiz"]["time_seconds"]),
        ("Vision time (s)", m1["vision"]["total_time_seconds"], m2["vision"]["total_time_seconds"]),
        ("Summary OK?", m1["summary"]["success"], m2["summary"]["success"]),
        ("Quiz JSON valid?", m1["quiz"]["json_valid"], m2["quiz"]["json_valid"]),
        ("So cau quiz", m1["quiz"]["num_questions"], m2["quiz"]["num_questions"]),
        ("So diem summary", m1["summary"]["num_points"], m2["summary"]["num_points"]),
    ]

    for label, v1, v2 in rows:
        print(f"  {label:<30} {str(v1):>18} {str(v2):>22}")

    print(f"  {'─'*70}")

    # Lưu kết quả
    out_file = output_dir / f"_compare_{target.stem}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)

    print(f"\n  Ket qua chi tiet luu tai: {out_file}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()


