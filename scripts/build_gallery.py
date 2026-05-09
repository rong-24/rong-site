#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
自动扫描本地图片目录，生成：
1. Obsidian 可查看的图片库 Markdown 页面
2. 网站可用的 webp 缩略图和压缩大图

用法示例：
python3 tools/build_gallery.py \
  --src "/Users/liu/Pictures/personal_gallery_raw" \
  --vault "/Users/liu/Obsidian/个人网站" \
  --title "我的图片库"
"""

import argparse
import hashlib
import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from tqdm import tqdm

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:
    HEIF_OK = False


SUPPORTED_EXTS = {
    ".jpg", ".jpeg", ".png", ".webp",
    ".bmp", ".tif", ".tiff",
    ".heic", ".heif"
}


def print_step(msg: str):
    print(f"\n[步骤] {msg}")


def print_info(msg: str):
    print(f"[信息] {msg}")


def print_warn(msg: str):
    print(f"[警告] {msg}")


def sha1_short(text: str, length: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def is_hidden_path(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def collect_images(src_dir: Path):
    images = []
    for p in src_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src_dir)
        if is_hidden_path(rel):
            continue
        if p.suffix.lower() in SUPPORTED_EXTS:
            images.append(p)
    return sorted(images, key=lambda x: str(x).lower())


def make_safe_name(src_dir: Path, img_path: Path) -> str:
    rel = img_path.relative_to(src_dir)
    stem = img_path.stem
    digest = sha1_short(rel.as_posix())
    return f"{digest}.webp"


def to_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img

    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg

    return img.convert("RGB")


def save_large_webp(img: Image.Image, out_path: Path, max_side: int, quality: int):
    img = ImageOps.exif_transpose(img)
    img = to_rgb(img)
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "WEBP", quality=quality, method=6)


def save_thumb_webp(img: Image.Image, out_path: Path, size: int, quality: int):
    img = ImageOps.exif_transpose(img)
    img = to_rgb(img)

    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((size, size), Image.Resampling.LANCZOS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "WEBP", quality=quality, method=6)


def rel_url(from_file: Path, target_file: Path) -> str:
    return os.path.relpath(target_file, from_file.parent).replace(os.sep, "/")


def build_page_md(title, page_no, total_pages, records, page_file: Path):
    lines = []
    lines.append("---")
    lines.append("cssclasses:")
    lines.append("  - image-gallery-page")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title} · 第 {page_no} 页")
    lines.append("")
    lines.append(f"> 共 {total_pages} 页。本页图片数量：{len(records)}。")
    lines.append("")
    lines.append("[返回图片库首页](../图片库.md)")
    lines.append("")
    lines.append('<div class="gallery-grid">')

    for r in records:
        thumb = rel_url(page_file, r["thumb"])
        large = rel_url(page_file, r["large"])
        alt = r["name"].replace('"', "")
        folder = r["folder"].replace('"', "")
        lines.append(
            f'<a class="gallery-item" href="{large}">'
            f'<img src="{thumb}" loading="lazy" alt="{alt}">'
            f'<span>{folder}</span>'
            f'</a>'
        )

    lines.append("</div>")
    lines.append("")
    lines.append("[返回图片库首页](../图片库.md)")
    lines.append("")
    return "\n".join(lines)


def build_index_md(title, total_images, total_pages, page_files, index_file: Path):
    lines = []
    lines.append("---")
    lines.append("cssclasses:")
    lines.append("  - image-gallery-index")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"这里是自动生成的图片库，共 **{total_images}** 张图片，分为 **{total_pages}** 页。")
    lines.append("")
    lines.append("> 原图不放进网站，这里展示的是压缩后的网页版本。")
    lines.append("")
    lines.append("## 分页浏览")
    lines.append("")

    for i, pf in enumerate(page_files, start=1):
        link = rel_url(index_file, pf)
        lines.append(f"- [第 {i:03d} 页]({link})")

    lines.append("")
    lines.append("## 使用说明")
    lines.append("")
    lines.append("- 点击缩略图可以打开较大的网页版图片。")
    lines.append("- 如果你新增了原图，重新运行脚本即可更新图库。")
    lines.append("- 如果图片太多，不建议全部放到一个页面里，所以这里自动分卷。")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True, help="原始图片目录，不要放在 Obsidian 库里")
    parser.add_argument("--vault", required=True, help="Obsidian 库根目录")
    parser.add_argument("--title", default="我的图片库", help="图片库标题")
    parser.add_argument("--page-size", type=int, default=240, help="每页图片数量")
    parser.add_argument("--large-side", type=int, default=1800, help="网页大图最长边")
    parser.add_argument("--thumb-size", type=int, default=420, help="缩略图尺寸")
    parser.add_argument("--large-quality", type=int, default=82, help="网页大图质量")
    parser.add_argument("--thumb-quality", type=int, default=76, help="缩略图质量")
    parser.add_argument("--force", action="store_true", help="强制重新生成所有图片")
    args = parser.parse_args()

    src_dir = Path(args.src).expanduser().resolve()
    vault_dir = Path(args.vault).expanduser().resolve()

    if not src_dir.exists():
        print_warn(f"原图目录不存在：{src_dir}")
        sys.exit(1)

    if not vault_dir.exists():
        print_warn(f"Obsidian 库不存在：{vault_dir}")
        sys.exit(1)

    print_step("检查环境")
    print_info(f"原图目录：{src_dir}")
    print_info(f"Obsidian 库：{vault_dir}")
    print_info(f"HEIC/HEIF 支持：{'已启用' if HEIF_OK else '未启用'}")

    thumbs_dir = vault_dir / "assets" / "gallery" / "thumbs"
    large_dir = vault_dir / "assets" / "gallery" / "large"
    pages_dir = vault_dir / "图库分卷"
    index_file = vault_dir / "图片库.md"

    thumbs_dir.mkdir(parents=True, exist_ok=True)
    large_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    print_step("扫描图片")
    images = collect_images(src_dir)
    print_info(f"识别到图片数量：{len(images)}")

    if not images:
        print_warn("没有找到可处理图片。")
        return

    records = []
    failed = []

    print_step("生成缩略图和网页大图")
    for img_path in tqdm(images):
        rel = img_path.relative_to(src_dir)
        safe_name = make_safe_name(src_dir, img_path)

        thumb_path = thumbs_dir / safe_name
        large_path = large_dir / safe_name

        need_process = args.force or (not thumb_path.exists()) or (not large_path.exists())

        if need_process:
            try:
                with Image.open(img_path) as img:
                    save_large_webp(img.copy(), large_path, args.large_side, args.large_quality)
                    save_thumb_webp(img.copy(), thumb_path, args.thumb_size, args.thumb_quality)
            except (UnidentifiedImageError, OSError, ValueError) as e:
                failed.append((img_path, str(e)))
                continue

        folder = rel.parent.as_posix()
        if folder == ".":
            folder = "未分类"

        records.append({
            "name": img_path.stem,
            "folder": folder,
            "thumb": thumb_path,
            "large": large_path,
        })

    print_info(f"成功处理图片：{len(records)}")
    if failed:
        print_warn(f"处理失败图片：{len(failed)}")
        for p, err in failed[:20]:
            print_warn(f"{p} -> {err}")
        if len(failed) > 20:
            print_warn("失败图片超过 20 张，仅显示前 20 张。")

    print_step("生成 Obsidian 图片库页面")
    total_pages = math.ceil(len(records) / args.page_size)
    page_files = []

    for page_idx in range(total_pages):
        start = page_idx * args.page_size
        end = start + args.page_size
        page_records = records[start:end]

        page_file = pages_dir / f"gallery_{page_idx + 1:03d}.md"
        md = build_page_md(
            title=args.title,
            page_no=page_idx + 1,
            total_pages=total_pages,
            records=page_records,
            page_file=page_file,
        )
        page_file.write_text(md, encoding="utf-8")
        page_files.append(page_file)

    index_md = build_index_md(
        title=args.title,
        total_images=len(records),
        total_pages=total_pages,
        page_files=page_files,
        index_file=index_file,
    )
    index_file.write_text(index_md, encoding="utf-8")

    print_step("完成")
    print_info(f"首页文件：{index_file}")
    print_info(f"分卷目录：{pages_dir}")
    print_info(f"缩略图目录：{thumbs_dir}")
    print_info(f"网页大图目录：{large_dir}")
    print_info("现在打开 Obsidian，查看《图片库.md》即可。")


if __name__ == "__main__":
    main()
