import cv2
import mediapipe as mp
import os
import io
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif'}
MIN_BRIGHTNESS_SCALE = 0.2
MAX_BRIGHTNESS_SCALE = 2.0

# Luu y: left/right o day la theo phia cua nguoi trong anh, khong phai phia nguoi xem.
# Polygon duoc dat theo thu tu di quanh vung ma de mask ra "mieng ma" ro hon.
LEFT_CHEEK_INDICES = [117, 119, 100, 142, 203, 186, 192, 213, 123, 116]
RIGHT_CHEEK_INDICES = [348, 346, 345, 352, 433, 416, 436, 423, 355, 329]

SKIN_TONE_GROUPS = [
    {
        "group": 1,
        "label": "Rất sáng / Trắng",
        "range_text": ">= 70",
        "min_inclusive": 70.0,
        "max_exclusive": None,
    },
    {
        "group": 2,
        "label": "Vàng sáng / Olive nhạt",
        "range_text": "57-70",
        "min_inclusive": 57.0,
        "max_exclusive": 70.0,
    },
    {
        "group": 3,
        "label": "Nâu nhạt / Olive đậm",
        "range_text": "44-57",
        "min_inclusive": 44.0,
        "max_exclusive": 57.0,
    },
    {
        "group": 4,
        "label": "Nâu đậm",
        "range_text": "32-44",
        "min_inclusive": 32.0,
        "max_exclusive": 44.0,
    },
    {
        "group": 5,
        "label": "Rất tối / Đen",
        "range_text": "< 32",
        "min_inclusive": None,
        "max_exclusive": 32.0,
    },
]

# Khởi tạo module Face Mesh của MediaPipe
mp_face_mesh = mp.solutions.face_mesh


def normalize_brightness_scale(brightness_scale):
    try:
        scale = float(brightness_scale)
    except (TypeError, ValueError):
        return 1.0
    return max(MIN_BRIGHTNESS_SCALE, min(MAX_BRIGHTNESS_SCALE, scale))


def adjust_measurement_brightness(image_bgr, brightness_scale):
    scale = normalize_brightness_scale(brightness_scale)
    if abs(scale - 1.0) < 1e-6:
        return image_bgr

    hsv_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv_image[:, :, 2] = np.clip(hsv_image[:, :, 2] * scale, 0, 255)
    return cv2.cvtColor(hsv_image.astype(np.uint8), cv2.COLOR_HSV2BGR)


def pil_to_bgr(pil_image):
    rgb_image = ImageOps.exif_transpose(pil_image).convert("RGB")
    rgb_array = np.array(rgb_image)
    return cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)


def decode_image_bytes(image_bytes):
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    if image_array.size > 0:
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if image is not None:
            return image

    try:
        with Image.open(io.BytesIO(image_bytes)) as pil_image:
            return pil_to_bgr(pil_image)
    except Exception:
        return None


def load_image_path(image_path):
    try:
        image_bytes = Path(image_path).read_bytes()
    except OSError:
        return None
    return decode_image_bytes(image_bytes)


def landmark_to_pixel(face_landmarks, index, width, height):
    landmark = face_landmarks.landmark[index]
    return np.array([int(landmark.x * width), int(landmark.y * height)])


def build_region_points(face_landmarks, indices, width, height):
    return np.array(
        [landmark_to_pixel(face_landmarks, idx, width, height) for idx in indices],
        dtype=np.int32,
    )


def create_polygon_mask(shape, polygon_points):
    mask = np.zeros(shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [polygon_points], 255)
    return mask


def extract_lstar_pixels(image_lab, polygon_points):
    mask = create_polygon_mask(image_lab.shape, polygon_points)
    l_channel = image_lab[:, :, 0].astype(np.float32)
    return l_channel[mask > 0]


def l_channel_mean_to_lstar(selected_pixels):
    if selected_pixels.size == 0:
        return None

    # OpenCV stores L in [0, 255]; convert to CIE L* in [0, 100].
    return float(selected_pixels.mean() * 100.0 / 255.0)


def compute_mean_lstar(image_bgr, polygon_points):
    mask = create_polygon_mask(image_bgr.shape, polygon_points)
    image_lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    l_channel = image_lab[:, :, 0].astype(np.float32)
    selected_pixels = l_channel[mask > 0]
    return l_channel_mean_to_lstar(selected_pixels)


def classify_skin_tone(lstar_value):
    for group_info in SKIN_TONE_GROUPS:
        min_ok = (
            group_info["min_inclusive"] is None
            or lstar_value >= group_info["min_inclusive"]
        )
        max_ok = (
            group_info["max_exclusive"] is None
            or lstar_value < group_info["max_exclusive"]
        )
        if min_ok and max_ok:
            return group_info
    return None


def draw_result_label(image, lines):
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.65
    thickness = 2
    line_height = 28
    padding = 14

    max_width = 0
    for line in lines:
        (text_width, _), _ = cv2.getTextSize(line, font, font_scale, thickness)
        max_width = max(max_width, text_width)

    box_width = max_width + padding * 2
    box_height = line_height * len(lines) + padding * 2
    x0, y0 = 16, 16
    x1, y1 = x0 + box_width, y0 + box_height

    overlay = image.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), (20, 20, 20), thickness=-1)
    cv2.rectangle(overlay, (x0, y0), (x1, y1), (255, 255, 255), thickness=2)
    image[:] = cv2.addWeighted(overlay, 0.72, image, 0.28, 0)

    text_y = y0 + padding + 16
    for line in lines:
        cv2.putText(
            image,
            line,
            (x0 + padding, text_y),
            font,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )
        text_y += line_height


def draw_cheek_regions(image, face_landmarks, width, height):
    overlay = image.copy()
    left_cheek = build_region_points(face_landmarks, LEFT_CHEEK_INDICES, width, height)
    right_cheek = build_region_points(face_landmarks, RIGHT_CHEEK_INDICES, width, height)

    cv2.fillPoly(overlay, [left_cheek], (255, 180, 0))
    cv2.fillPoly(overlay, [right_cheek], (0, 180, 255))

    cv2.polylines(overlay, [left_cheek], isClosed=True, color=(255, 120, 0), thickness=2)
    cv2.polylines(overlay, [right_cheek], isClosed=True, color=(0, 120, 255), thickness=2)

    image[:] = cv2.addWeighted(overlay, 0.28, image, 0.72, 0)

    return {
        "left_cheek": LEFT_CHEEK_INDICES,
        "right_cheek": RIGHT_CHEEK_INDICES,
        "left_polygon": left_cheek,
        "right_polygon": right_cheek,
    }

def select_faces(faces, width, height, mode='largest'):
    if mode != 'largest':
        return list(faces)

    max_area = 0
    largest_face = None
    for face_landmarks in faces:
        x_coords = [landmark.x * width for landmark in face_landmarks.landmark]
        y_coords = [landmark.y * height for landmark in face_landmarks.landmark]
        face_width = max(x_coords) - min(x_coords)
        face_height = max(y_coords) - min(y_coords)
        area = face_width * face_height
        if area > max_area:
            max_area = area
            largest_face = face_landmarks

    return [largest_face] if largest_face is not None else []


def build_label_lines(left_lstar, right_lstar, final_lstar, skin_tone_group):
    lines = [
        f"L* trai: {left_lstar:.2f}",
        f"L* phai: {right_lstar:.2f}",
        f"L* cuoi: {final_lstar:.2f}",
    ]
    if skin_tone_group is None:
        lines.append("Nhom da: N/A")
    else:
        lines.append(
            f"Nhom da: {skin_tone_group['group']} - {skin_tone_group['label']}"
        )
    return lines


def _analyze_image_with_results(
    original_image,
    measurement_image,
    results,
    mode='largest',
    draw_labels=True,
):
    height, width, _ = original_image.shape

    if not results.multi_face_landmarks:
        return {
            "ok": False,
            "message": "Không tìm thấy khuôn mặt.",
            "original_image": original_image,
            "visualization_image": original_image.copy(),
            "faces": [],
        }

    selected_faces = select_faces(results.multi_face_landmarks, width, height, mode=mode)
    annotated_image = original_image.copy()
    face_results = []
    image_lab = cv2.cvtColor(measurement_image, cv2.COLOR_BGR2LAB)

    for face_index, face_landmarks in enumerate(selected_faces, start=1):
        cheek_regions = draw_cheek_regions(annotated_image, face_landmarks, width, height)
        left_pixels = extract_lstar_pixels(image_lab, cheek_regions["left_polygon"])
        right_pixels = extract_lstar_pixels(image_lab, cheek_regions["right_polygon"])
        left_lstar = l_channel_mean_to_lstar(left_pixels)
        right_lstar = l_channel_mean_to_lstar(right_pixels)

        if left_lstar is None or right_lstar is None:
            continue

        combined_pixels = np.concatenate((left_pixels, right_pixels))
        final_lstar = l_channel_mean_to_lstar(combined_pixels)
        skin_tone_group = classify_skin_tone(final_lstar)
        label_lines = build_label_lines(
            left_lstar,
            right_lstar,
            final_lstar,
            skin_tone_group,
        )

        if draw_labels:
            draw_result_label(annotated_image, label_lines)

        face_results.append(
            {
                "face_index": face_index,
                "left_cheek_indices": cheek_regions["left_cheek"],
                "right_cheek_indices": cheek_regions["right_cheek"],
                "left_lstar": left_lstar,
                "right_lstar": right_lstar,
                "average_lstar": final_lstar,
                "skin_tone_group": skin_tone_group,
                "label_lines": label_lines,
            }
        )

    if not face_results:
        return {
            "ok": False,
            "message": "Không tính được L*.",
            "original_image": original_image,
            "visualization_image": annotated_image,
            "faces": [],
        }

    return {
        "ok": True,
        "message": "Thành công.",
        "original_image": original_image,
        "visualization_image": annotated_image,
        "faces": face_results,
    }


def analyze_image_array(
    image,
    mode='largest',
    draw_labels=True,
    face_mesh=None,
    brightness_scale=1.0,
):
    if image is None:
        return {
            "ok": False,
            "message": "Không đọc được ảnh.",
        }

    measurement_image = adjust_measurement_brightness(image, brightness_scale)
    image_rgb = cv2.cvtColor(measurement_image, cv2.COLOR_BGR2RGB)
    if face_mesh is not None:
        results = face_mesh.process(image_rgb)
        return _analyze_image_with_results(
            image,
            measurement_image,
            results,
            mode=mode,
            draw_labels=draw_labels,
        )

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=20,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as local_face_mesh:
        results = local_face_mesh.process(image_rgb)

    return _analyze_image_with_results(
        image,
        measurement_image,
        results,
        mode=mode,
        draw_labels=draw_labels,
    )


def analyze_image_path(
    image_path,
    mode='largest',
    draw_labels=True,
    face_mesh=None,
    brightness_scale=1.0,
):
    image = load_image_path(image_path)
    return analyze_image_array(
        image,
        mode=mode,
        draw_labels=draw_labels,
        face_mesh=face_mesh,
        brightness_scale=brightness_scale,
    )


def print_analysis_summary(image_name, analysis_result):
    for face_result in analysis_result["faces"]:
        print(f"Cheek landmarks for {image_name}:")
        print(f"  - left_cheek: {face_result['left_cheek_indices']}")
        print(f"  - right_cheek: {face_result['right_cheek_indices']}")
        print(f"Face {face_result['face_index']} - {image_name}:")
        print(f"  - L* ma trai: {face_result['left_lstar']:.2f}")
        print(f"  - L* ma phai: {face_result['right_lstar']:.2f}")
        print(f"  - L* trung binh: {face_result['average_lstar']:.2f}")
        if face_result["skin_tone_group"] is not None:
            skin_tone_group = face_result["skin_tone_group"]
            print(
                f"  - Nhom mau da: {skin_tone_group['group']} "
                f"({skin_tone_group['label']}, L* {skin_tone_group['range_text']})"
            )


def process_image(image_path, output_path, mode='largest'):
    analysis_result = analyze_image_path(image_path, mode=mode, draw_labels=True)
    if not analysis_result["ok"]:
        print(f"ℹ️ {analysis_result['message']} {image_path}")
        return

    print_analysis_summary(Path(image_path).name, analysis_result)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(str(output_path), analysis_result["visualization_image"])
    print(f"✅ Đã xử lý và lưu: {output_path}")

def run_pipeline(input_source, output_base_dir="visualization", mode='largest'):
    """
    Hàm pipeline nhận đầu vào là file hoặc folder và giữ nguyên cấu trúc thư mục.
    mode: 'largest' (Mặt to nhất) hoặc 'all' (Tất cả các mặt)
    """
    input_path = Path(input_source)
    output_base_dir = Path(output_base_dir)

    if input_path.is_file():
        # Nếu truyền vào 1 file ảnh trực tiếp
        if input_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            output_path = output_base_dir / input_path.name
            process_image(input_path, output_path, mode)
        else:
            print("Định dạng file không được hỗ trợ (cần .png, .jpg, .jpeg, .webp, .heic, .heif).")
            
    elif input_path.is_dir():
        # Nếu truyền vào folder: duyệt qua tất cả sub-folder
        print(f"Bắt đầu quét thư mục: {input_path}")
        for root, _, files in os.walk(input_path):
            for file in files:
                if Path(file).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    file_path = Path(root) / file
                    
                    # Tạo cấu trúc thư mục tương ứng cho output
                    relative_path = file_path.relative_to(input_path)
                    output_path = output_base_dir / relative_path
                    
                    process_image(file_path, output_path, mode)
    else:
        print("Đường dẫn đầu vào không tồn tại!")

# ==========================================
# CÁCH CHẠY THỬ THỰC TẾ
# ==========================================
if __name__ == "__main__":
    # Thay đường dẫn này bằng ảnh hoặc folder thực tế của bạn
    INPUT_PATH = "/Users/ngoquangduc/Desktop/workspace/flash-based/images/image1.png"
    
    # Chạy script với cấu hình lấy mặt to nhất
    run_pipeline(
        input_source=INPUT_PATH, 
        output_base_dir="visualization_output", 
        mode='largest' # Đổi thành 'all' nếu muốn bắt hết mặt
    )
