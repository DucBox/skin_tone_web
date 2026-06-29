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
    return parser.parse_args()


def collect_image_paths(input_dir):
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    )


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


def build_row(relative_path, analysis_result, visualization_path=None):
    row = {
        "duong_dan_anh": relative_path.as_posix(),
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


def run_batch(input_dir, output_dir, mode):
    image_paths = collect_image_paths(input_dir)
    if not image_paths:
        raise SystemExit("Khong tim thay anh hop le trong thu muc dau vao.")

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    for image_path in tqdm(image_paths, desc="Dang xu ly anh", unit="anh"):
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


def main():
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit("Thu muc dau vao khong ton tai hoac khong hop le.")

    run_batch(input_dir, output_dir, args.mode)


if __name__ == "__main__":
    main()
