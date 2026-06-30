import argparse
import csv
from collections import Counter
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from tqdm import tqdm

try:
    from app.tool_calc_L import SKIN_TONE_GROUPS, SUPPORTED_IMAGE_EXTENSIONS, analyze_image_path
except ModuleNotFoundError:
    from tool_calc_L import SKIN_TONE_GROUPS, SUPPORTED_IMAGE_EXTENSIONS, analyze_image_path


DEFAULT_INPUT_DIR = "/mounted/input"
DEFAULT_OUTPUT_DIR = "/mounted/output"
MATCH_DIR_OPTIONS = {
    "match": "Match",
    "non-match": "Non-Match",
}
IMAGE_ROLE_PREFIXES = {
    "live": "live_",
    "portrait": "portrait_",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Xu ly 1 thu muc anh va ve phan phoi nhom da, L*."
    )
    parser.add_argument(
        "--input-dir",
        default=DEFAULT_INPUT_DIR,
        help="Thu muc anh dau vao.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Thu muc luu ket qua.",
    )
    parser.add_argument(
        "--mode",
        default="largest",
        choices=["largest", "all"],
        help="largest: mat lon nhat, all: tat ca khuon mat.",
    )
    parser.add_argument(
        "--match-type",
        default="all",
        choices=["all", "match", "non-match"],
        help="Loc theo folder Match / Non-Match.",
    )
    parser.add_argument(
        "--image-type",
        default="all",
        choices=["all", "live", "portrait"],
        help="Loc theo ten anh live_ / portrait_.",
    )
    return parser.parse_args()


def normalize_name(text):
    return text.strip().lower()


def selected_match_dirs(match_type):
    if match_type == "all":
        return list(MATCH_DIR_OPTIONS.values())
    return [MATCH_DIR_OPTIONS[match_type]]


def image_name_matches(image_path, image_type):
    if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        return False

    if image_type == "all":
        return True

    file_name = normalize_name(image_path.name)
    return file_name.startswith(IMAGE_ROLE_PREFIXES[image_type])


def collect_image_paths(input_dir, match_type, image_type):
    image_paths = []

    for match_dir_name in selected_match_dirs(match_type):
        match_dir = input_dir / match_dir_name
        if not match_dir.exists() or not match_dir.is_dir():
            continue

        for id_dir in sorted(path for path in match_dir.iterdir() if path.is_dir()):
            for image_path in sorted(path for path in id_dir.iterdir() if path.is_file()):
                if image_name_matches(image_path, image_type):
                    image_paths.append(image_path)

    return image_paths


def ensure_parent_dir(file_path):
    file_path.parent.mkdir(parents=True, exist_ok=True)


def visualization_output_path(output_dir, relative_path):
    return output_dir / "visualizations" / relative_path.with_suffix(".png")


def summary_csv_path(output_dir):
    return output_dir / "tong_hop_ket_qua.csv"


def group_chart_path(output_dir):
    return output_dir / "phan_phoi_nhom_da.png"


def lstar_chart_path(output_dir):
    return output_dir / "phan_phoi_gia_tri_lstar.png"


def save_visualization(image, output_path):
    ensure_parent_dir(output_path)
    cv2.imwrite(str(output_path), image)


def extract_match_context(relative_path):
    parts = relative_path.parts
    match_group = parts[0] if len(parts) >= 1 else ""
    subject_id = parts[1] if len(parts) >= 2 else ""
    file_name = parts[-1] if parts else ""

    image_role = ""
    file_name_lower = normalize_name(file_name)
    for role, prefix in IMAGE_ROLE_PREFIXES.items():
        if file_name_lower.startswith(prefix):
            image_role = role
            break

    return match_group, subject_id, image_role


def build_row(relative_path, analysis_result, visualization_path=None):
    match_group, subject_id, image_role = extract_match_context(relative_path)
    row = {
        "duong_dan_anh": relative_path.as_posix(),
        "nhom_du_lieu": match_group,
        "id": subject_id,
        "loai_anh": image_role,
        "trang_thai": "Thanh cong" if analysis_result["ok"] else "Loi",
        "lstar_ma_trai": "",
        "lstar_ma_phai": "",
        "lstar_cuoi": "",
        "nhom_mau_da": "",
        "mo_ta_nhom": "",
        "nguong_nhom": "",
        "thong_bao": analysis_result["message"],
        "anh_visualization": visualization_path.as_posix() if visualization_path else "",
    }

    if analysis_result["ok"] and analysis_result["faces"]:
        face = analysis_result["faces"][0]
        group_info = face["skin_tone_group"]
        row.update(
            {
                "lstar_ma_trai": f"{face['left_lstar']:.2f}",
                "lstar_ma_phai": f"{face['right_lstar']:.2f}",
                "lstar_cuoi": f"{face['average_lstar']:.2f}",
                "nhom_mau_da": group_info["group"] if group_info else "",
                "mo_ta_nhom": group_info["label"] if group_info else "",
                "nguong_nhom": group_info["range_text"] if group_info else "",
            }
        )

    return row


def write_summary_csv(rows, output_path):
    ensure_parent_dir(output_path)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        file_obj.write("sep=;\n")
        writer = csv.DictWriter(
            file_obj,
            fieldnames=[
                "duong_dan_anh",
                "nhom_du_lieu",
                "id",
                "loai_anh",
                "trang_thai",
                "lstar_ma_trai",
                "lstar_ma_phai",
                "lstar_cuoi",
                "nhom_mau_da",
                "mo_ta_nhom",
                "nguong_nhom",
                "thong_bao",
                "anh_visualization",
            ],
            delimiter=";",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def render_group_distribution(rows, output_path):
    counts = Counter()
    for row in rows:
        if row["nhom_mau_da"]:
            counts[int(row["nhom_mau_da"])] += 1

    groups = [group_info["group"] for group_info in SKIN_TONE_GROUPS]
    values = [counts.get(group, 0) for group in groups]

    plt.figure(figsize=(8, 5))
    bars = plt.bar(groups, values, color=["#cb6d2d", "#d9924b", "#b68463", "#8f6b56", "#5f4a43"])
    plt.title("Phan phoi nhom mau da")
    plt.xlabel("Nhom mau da")
    plt.ylabel("So anh")
    plt.xticks(groups)
    plt.grid(axis="y", alpha=0.18)

    for bar, value in zip(bars, values):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.05,
            str(value),
            ha="center",
            va="bottom",
        )

    ensure_parent_dir(output_path)
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def render_lstar_distribution(rows, output_path):
    lstar_values = [
        float(row["lstar_cuoi"])
        for row in rows
        if row["lstar_cuoi"]
    ]

    plt.figure(figsize=(8, 5))
    plt.hist(lstar_values, bins=12, range=(0, 100), color="#325b84", edgecolor="white")
    plt.title("Phan phoi gia tri L*")
    plt.xlabel("Gia tri L*")
    plt.ylabel("So anh")
    plt.grid(axis="y", alpha=0.18)

    ensure_parent_dir(output_path)
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()


def run_batch(input_dir, output_dir, mode, match_type, image_type):
    image_paths = collect_image_paths(input_dir, match_type, image_type)
    if not image_paths:
        raise SystemExit("Khong tim thay anh hop le theo bo loc da chon.")

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    progress_desc = f"Dang xu ly anh ({match_type}/{image_type})"
    for image_path in tqdm(image_paths, desc=progress_desc, unit="anh"):
        relative_path = image_path.relative_to(input_dir)
        analysis_result = analyze_image_path(image_path, mode=mode, draw_labels=True)
        vis_path = None

        if analysis_result.get("visualization_image") is not None:
            vis_path = visualization_output_path(output_dir, relative_path)
            save_visualization(analysis_result["visualization_image"], vis_path)

        rows.append(build_row(relative_path, analysis_result, vis_path))

    write_summary_csv(rows, summary_csv_path(output_dir))
    render_group_distribution(rows, group_chart_path(output_dir))
    render_lstar_distribution(rows, lstar_chart_path(output_dir))

    success_count = sum(1 for row in rows if row["trang_thai"] == "Thanh cong")
    print(f"Da xu ly {len(rows)} anh. Thanh cong: {success_count}.")
    print(f"CSV: {summary_csv_path(output_dir)}")
    print(f"Chart nhom da: {group_chart_path(output_dir)}")
    print(f"Chart L*: {lstar_chart_path(output_dir)}")
    print(f"Visualization: {output_dir / 'visualizations'}")
    print(f"Bo loc: match_type={match_type}, image_type={image_type}")


def main():
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit("Thu muc dau vao khong ton tai hoac khong hop le.")

    run_batch(input_dir, output_dir, args.mode, args.match_type, args.image_type)


if __name__ == "__main__":
    main()
