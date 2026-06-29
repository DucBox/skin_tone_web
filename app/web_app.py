import base64
import csv
import io
import os
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, render_template, request

try:
    from app.tool_calc_L import SUPPORTED_IMAGE_EXTENSIONS, analyze_image_array
except ModuleNotFoundError:
    from tool_calc_L import SUPPORTED_IMAGE_EXTENSIONS, analyze_image_array


app = Flask(__name__, template_folder="templates")


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


TEST_MODE = env_flag("APP_TEST_MODE", default=True)


def decode_uploaded_file(file_storage):
    if file_storage is None or not file_storage.filename:
        return None

    file_bytes = np.frombuffer(file_storage.read(), dtype=np.uint8)
    if file_bytes.size == 0:
        return None

    return cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)


def decode_camera_data(data_url):
    if not data_url or "," not in data_url:
        return None

    _, encoded = data_url.split(",", 1)
    image_bytes = base64.b64decode(encoded)
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    if image_array.size == 0:
        return None

    return cv2.imdecode(image_array, cv2.IMREAD_COLOR)


def encode_image_data_url(image_bgr):
    ok, encoded = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        return None

    encoded_text = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded_text}"


def encode_csv_data_url(analyzed_items):
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "duong_dan_anh",
            "trang_thai",
            "lstar_ma_trai",
            "lstar_ma_phai",
            "lstar_trung_binh",
            "nhom_mau_da",
            "mo_ta_nhom",
            "nguong_nhom",
            "thong_bao",
        ],
    )
    writer.writeheader()

    for item in analyzed_items:
        writer.writerow(
            {
                "duong_dan_anh": item["display_path"],
                "trang_thai": "Thanh cong" if item["ok"] else "Loi",
                "lstar_ma_trai": item["left_lstar"] if item["left_lstar"] is not None else "",
                "lstar_ma_phai": item["right_lstar"] if item["right_lstar"] is not None else "",
                "lstar_trung_binh": item["average_lstar"] if item["average_lstar"] is not None else "",
                "nhom_mau_da": item["skin_tone_group"] if item["skin_tone_group"] is not None else "",
                "mo_ta_nhom": item["skin_tone_label"] if item["skin_tone_label"] else "",
                "nguong_nhom": item["skin_tone_range"] if item["skin_tone_range"] else "",
                "thong_bao": item["message"],
            }
        )

    csv_bytes = ("\ufeff" + buffer.getvalue()).encode("utf-8")
    encoded_text = base64.b64encode(csv_bytes).decode("ascii")
    return f"data:text/csv;base64,{encoded_text}"


def allowed_image(filename):
    return Path(filename).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


def build_item_result(display_path, analysis_result):
    item = {
        "display_path": display_path,
        "file_name": Path(display_path).name,
        "ok": analysis_result["ok"],
        "message": analysis_result["message"],
        "original_image_url": None,
        "visualization_image_url": None,
        "left_lstar": None,
        "right_lstar": None,
        "average_lstar": None,
        "skin_tone_group": None,
        "skin_tone_label": None,
        "skin_tone_range": None,
    }

    original_image = analysis_result.get("original_image")
    visualization_image = analysis_result.get("visualization_image")
    if original_image is not None:
        item["original_image_url"] = encode_image_data_url(original_image)
    if visualization_image is not None:
        item["visualization_image_url"] = encode_image_data_url(visualization_image)

    if analysis_result["ok"] and analysis_result["faces"]:
        first_face = analysis_result["faces"][0]
        skin_tone_group = first_face["skin_tone_group"]
        item.update(
            {
                "left_lstar": round(first_face["left_lstar"], 2),
                "right_lstar": round(first_face["right_lstar"], 2),
                "average_lstar": round(first_face["average_lstar"], 2),
                "skin_tone_group": skin_tone_group["group"] if skin_tone_group else None,
                "skin_tone_label": skin_tone_group["label"] if skin_tone_group else "Không có",
                "skin_tone_range": skin_tone_group["range_text"] if skin_tone_group else "Không có",
            }
        )

    return item


def analyze_files(file_storages):
    results = []
    for file_storage in file_storages:
        if not file_storage or not file_storage.filename:
            continue
        if not allowed_image(file_storage.filename):
            continue

        image = decode_uploaded_file(file_storage)
        if image is None:
            continue

        analysis_result = analyze_image_array(image, mode="largest", draw_labels=True)
        results.append(build_item_result(file_storage.filename, analysis_result))

    return results


def analyze_single_image(image, display_path):
    analysis_result = analyze_image_array(image, mode="largest", draw_labels=True)
    return [build_item_result(display_path, analysis_result)]


@app.route("/", methods=["GET", "POST"])
def index():
    analyzed_items = []
    error = None

    if request.method == "POST":
        single_image = request.files.get("single_image")
        folder_files = request.files.getlist("folder_files")
        camera_image = request.form.get("camera_image", "").strip()

        if single_image and single_image.filename:
            analyzed_items = analyze_files([single_image])
        elif camera_image:
            image = decode_camera_data(camera_image)
            if image is not None:
                analyzed_items = analyze_single_image(image, "camera_capture.jpg")
        elif folder_files:
            analyzed_items = analyze_files(folder_files)

        if not analyzed_items:
            error = (
                "Vui lòng tải lên 1 ảnh hợp lệ hoặc chọn thư mục chứa ảnh "
                "(.png, .jpg, .jpeg, .webp)."
            )

    selected_item = analyzed_items[0] if analyzed_items else None
    total_count = len(analyzed_items)
    success_count = sum(1 for item in analyzed_items if item["ok"])
    csv_export_url = encode_csv_data_url(analyzed_items) if analyzed_items else None

    return render_template(
        "index.html",
        analyzed_items=analyzed_items,
        selected_item=selected_item,
        error=error,
        total_count=total_count,
        success_count=success_count,
        csv_export_url=csv_export_url,
        test_mode=TEST_MODE,
    )


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5001"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
