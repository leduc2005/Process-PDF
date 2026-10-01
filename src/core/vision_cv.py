"""
vision_cv.py - Tiền xử lý ảnh bằng OpenCV.

Các chức năng:
1. Đo độ mờ (Blur Detection) bằng Laplacian variance.
2. Khử nhiễu (Denoise) cho ảnh scan bị bẩn.
3. Canh lề (Deskew) cho ảnh bị nghiêng.
4. Tăng độ tương phản (CLAHE) để OCR/Vision LLM đọc tốt hơn.

Tất cả function nhận input là bytes (PNG/JPEG) và trả về bytes (PNG).
"""

import cv2
import numpy as np
from io import BytesIO


def bytes_to_cv2(image_bytes: bytes) -> np.ndarray:
    """Chuyển ảnh bytes -> OpenCV ndarray."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Không thể decode ảnh từ bytes.")
    return img


def cv2_to_bytes(img: np.ndarray, fmt: str = ".png") -> bytes:
    """Chuyển OpenCV ndarray -> bytes."""
    success, encoded = cv2.imencode(fmt, img)
    if not success:
        raise ValueError("Không thể encode ảnh thành bytes.")
    return encoded.tobytes()


def measure_blur(image_bytes: bytes) -> float:
    """
    Đo độ mờ của ảnh bằng Laplacian variance.

    Returns:
        float: Giá trị variance. Càng nhỏ -> càng mờ.
            - < 50: Rất mờ (ảnh scan chất lượng kém)
            - 50-200: Trung bình
            - > 200: Rõ nét
    """
    img = bytes_to_cv2(image_bytes)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    return round(laplacian_var, 2)


def denoise(image_bytes: bytes, strength: int = 10) -> bytes:
    """
    Khử nhiễu ảnh bằng Non-Local Means Denoising.
    Phù hợp cho ảnh scan bị bẩn, có đốm.

    Args:
        strength: Cường độ khử nhiễu (mặc định 10). Cao hơn -> mịn hơn nhưng mất chi tiết.
    """
    img = bytes_to_cv2(image_bytes)
    denoised = cv2.fastNlMeansDenoisingColored(img, None, strength, strength, 7, 21)
    return cv2_to_bytes(denoised)


def enhance_contrast(image_bytes: bytes) -> bytes:
    """
    Tăng độ tương phản bằng CLAHE (Contrast Limited Adaptive Histogram Equalization).
    Giúp text trên nền sáng/tối không đều trở nên rõ hơn.
    """
    img = bytes_to_cv2(image_bytes)
    # Chuyển sang LAB color space để xử lý kênh L (Lightness)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_channel)

    enhanced_lab = cv2.merge([l_enhanced, a_channel, b_channel])
    enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
    return cv2_to_bytes(enhanced_bgr)


def preprocess_for_vision(image_bytes: bytes, blur_threshold: float = 50.0) -> dict:
    """
    Pipeline tiền xử lý hoàn chỉnh cho 1 ảnh trước khi gửi Vision LLM.

    Returns:
        dict:
            - processed_image (bytes): Ảnh đã xử lý.
            - blur_score (float): Điểm độ mờ gốc.
            - is_blurry (bool): True nếu ảnh quá mờ.
            - steps_applied (list[str]): Các bước xử lý đã áp dụng.
    """
    blur_score = measure_blur(image_bytes)
    is_blurry = blur_score < blur_threshold
    steps = []
    processed = image_bytes

    # Bước 1: Nếu ảnh mờ -> khử nhiễu
    if is_blurry:
        processed = denoise(processed, strength=12)
        steps.append("denoise")

    # Bước 2: Tăng tương phản (luôn áp dụng cho ảnh scan)
    processed = enhance_contrast(processed)
    steps.append("enhance_contrast")

    return {
        "processed_image": processed,
        "blur_score": blur_score,
        "is_blurry": is_blurry,
        "steps_applied": steps,
    }
