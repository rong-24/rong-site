#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
把本地知乎收藏 Markdown 批量导入 Quartz 网站。

功能：
1. 读取知乎收藏导出的 Markdown 文件；
2. 解析 frontmatter 和正文中的作者、时间、赞同数、原链接等信息；
3. 为每篇内容生成一个 Quartz 页面；
4. 自动生成：
   - 知乎收藏首页
   - 全部内容页
   - 高赞内容页
   - 待人工复核页
   - 领域分类页
   - 内容形式分类页
   - 内容价值分类页

默认是公开安全模式：不发布原文正文，只发布元信息、摘要、个人评论、原链接。
加 --full 后会发布原文正文。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


DEFAULT_SOURCE = "/Users/liu/zhihu_fav_export/zhihu_collection_724494165/contents"
DEFAULT_QUARTZ_CONTENT = str(Path.home() / "Web" / "rong-site" / "content")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ensure_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(value).strip()]


def split_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """
    拆分 Markdown frontmatter。
    """
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, text, flags=re.S)
    if not match:
        return {}, text

    raw_yaml = match.group(1)
    body = match.group(2)

    try:
        data = yaml.safe_load(raw_yaml) or {}
        if not isinstance(data, dict):
            data = {}
    except Exception as e:
        print(f"[警告] frontmatter 解析失败：{e}")
        data = {}

    return data, body


def dump_frontmatter(data: Dict[str, Any]) -> str:
    return yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()


def find_first_hr(body: str):
    """
    查找正文中单独一行 --- 的位置。
    注意：不会匹配 ----- 这种回答里常见的分割线。
    """
    return re.search(r"(?m)^---\s*$", body)


def extract_info_from_body(body: str) -> Tuple[Dict[str, str], str]:
    """
    从原始正文开头的项目符号区提取信息。
    例如：
    - 作者：阿怪
    - 发布时间：2014-02-20 06:01:31
    - 原链接：https://...
    """
    hr = find_first_hr(body)

    if hr:
        info_part = body[:hr.start()]
        article_part = body[hr.end():].strip()
    else:
        info_part = body[:2500]
        article_part = re.sub(r"^# .+?\n+", "", body.strip(), count=1)

    info: Dict[str, str] = {}

    for line in info_part.splitlines():
        line = line.strip()
        match = re.match(r"^-\s*([^：:]+)[：:]\s*(.*)$", line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            info[key] = value

    return info, article_part


def normalize_date(value: str) -> str:
    if not value:
        return ""
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    return match.group(0) if match else ""


def parse_int(value: str) -> int:
    if not value:
        return 0
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else 0


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("|", "\\|")
    text = text.replace("\n", " ")
    return text.strip()


def short_text(value: str, limit: int = 32) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "..."


def infer_content_id(meta: Dict[str, Any], info: Dict[str, str], path: Path) -> str:
    """
    优先从“内容 ID”里取；
    其次从 source_file / 文件名中取；
    最后用文件内容 hash。
    """
    for key in ["内容 ID", "content_id", "id"]:
        if key in info and str(info[key]).strip():
            return str(info[key]).strip()
        if key in meta and str(meta[key]).strip():
            return str(meta[key]).strip()

    candidates = [
        str(meta.get("source_file", "")),
        path.name,
        path.stem,
    ]

    for text in candidates:
        match = re.search(r"(?:answer|article|zvideo|pin)[_-](\d+)", text)
        if match:
            return match.group(1)

    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    return digest


def link_to_item(item: Dict[str, Any]) -> str:
    title = md_escape(item["title"])
    slug = item["slug"]
    return f"[[知乎收藏/items/{slug}|{title}]]"


def make_table(items: List[Dict[str, Any]]) -> str:
    lines = [
        "| 标题 | 作者 | 领域 | 形式 | 赞同 | 状态 |",
        "|---|---|---|---|---:|---|",
    ]

    for item in items:
        title_link = link_to_item(item)
        author = md_escape(item.get("author", ""))
        domains = md_escape("、".join(item.get("domain", [])))
        forms = md_escape("、".join(item.get("form", [])))
        likes = item.get("likes", 0)
        status = "需复核" if item.get("needs_review") else "已归档"

        lines.append(
            f"| {title_link} | {author} | {domains} | {forms} | {likes} | {status} |"
        )

    return "\n".join(lines)


def make_group_links(groups: Dict[str, List[Dict[str, Any]]], base: str) -> str:
    lines = []
    for name, group_items in sorted(groups.items(), key=lambda x: (-len(x[1]), x[0])):
        safe_name = md_escape(name)
        lines.append(f"- [[知乎收藏/{base}/{safe_name}|{safe_name}]]：{len(group_items)} 篇")
    return "\n".join(lines)


def build_item_page(item: Dict[str, Any], full_mode: bool) -> str:
    summary = str(item.get("summary") or "").strip()
    my_comment = str(item.get("my_comment") or "").strip()
    raw_content = str(item.get("raw_content") or "").strip()

    fm = {
        "title": item["title"],
        "date": item.get("date") or None,
        "description": summary or None,
        "tags": item.get("tags", []),
        "source": "zhihu",
        "author": item.get("author") or None,
        "zhihu_url": item.get("url") or None,
        "domain": item.get("domain", []),
        "form": item.get("form", []),
        "value": item.get("value", []),
        "rating": item.get("rating"),
        "needs_review": item.get("needs_review", False),
        "draft": False,
    }

    # 去掉 None，frontmatter 更干净
    fm = {k: v for k, v in fm.items() if v is not None}

    lines = []
    lines.append("---")
    lines.append(dump_frontmatter(fm))
    lines.append("---")
    lines.append("")
    lines.append(f"# {item['title']}")
    lines.append("")
    lines.append("> [!info] 收藏信息")
    lines.append(f"> - 类型：{item.get('content_type', '')}")
    lines.append(f"> - 作者：{item.get('author', '')}")
    if item.get("author_intro"):
        lines.append(f"> - 作者简介：{item.get('author_intro', '')}")
    if item.get("published_at"):
        lines.append(f"> - 发布时间：{item.get('published_at')}")
    if item.get("updated_at"):
        lines.append(f"> - 更新时间：{item.get('updated_at')}")
    if item.get("collected_at"):
        lines.append(f"> - 收藏时间：{item.get('collected_at')}")
    lines.append(f"> - 赞同/喜欢数：{item.get('likes', 0)}")
    lines.append(f"> - 评论数：{item.get('comments', 0)}")
    if item.get("url"):
        lines.append(f"> - 原链接：{item.get('url')}")
    lines.append("")
    lines.append("## 自动分类")
    lines.append("")
    lines.append(f"- 领域：{md_escape('、'.join(item.get('domain', [])))}")
    lines.append(f"- 形式：{md_escape('、'.join(item.get('form', [])))}")
    lines.append(f"- 价值：{md_escape('、'.join(item.get('value', [])))}")
    lines.append(f"- 状态：{'需要人工复核' if item.get('needs_review') else '已归档'}")
    if item.get("classification_score"):
        lines.append(f"- 分类依据：{item.get('classification_score')}")
    lines.append("")
    lines.append("## 摘要")
    lines.append("")
    lines.append(summary if summary else "> 暂未填写。")
    lines.append("")
    lines.append("## 我的评论")
    lines.append("")
    lines.append(my_comment if my_comment else "> 暂未填写。")
    lines.append("")

    if full_mode:
        lines.append("## 原文内容")
        lines.append("")
        lines.append(raw_content if raw_content else "> 原文内容为空。")
        lines.append("")
    else:
        lines.append("## 原文")
        lines.append("")
        if item.get("url"):
            lines.append(f"- [查看知乎原文]({item.get('url')})")
        else:
            lines.append("> 未找到原链接。")
        lines.append("")
        lines.append("> [!warning] 说明")
        lines.append("> 当前页面处于公开安全模式，只展示元信息、摘要、评论和原链接，不全文转载原回答。")
        lines.append("> 若这是仅供自己访问的私有网站，可以重新运行脚本并添加 `--full` 参数。")
        lines.append("")

    return "\n".join(lines)


def collect_items(source_dir: Path) -> List[Dict[str, Any]]:
    files = sorted(source_dir.glob("*.md"))
    items: List[Dict[str, Any]] = []

    print(f"[扫描] 源目录：{source_dir}")
    print(f"[扫描] Markdown 文件数量：{len(files)}")

    for idx, path in enumerate(files, start=1):
        text = read_text(path)
        meta, body = split_frontmatter(text)
        info, article_content = extract_info_from_body(body)

        title = str(meta.get("title") or "").strip()
        if not title:
            # 尝试从正文一级标题取标题
            m = re.search(r"^#\s+(.+)$", body, flags=re.M)
            title = m.group(1).strip() if m else path.stem

        content_id = infer_content_id(meta, info, path)
        slug = f"zhihu-{content_id}"

        domain = ensure_list(meta.get("domain"))
        form = ensure_list(meta.get("form"))
        value = ensure_list(meta.get("value"))
        tags = ensure_list(meta.get("tags"))
        tags = sorted(set(tags + ["source/zhihu"]))

        content_type = info.get("类型", "")
        author = info.get("作者", "")
        author_intro = info.get("作者简介", "")
        published_at = info.get("发布时间", "")
        updated_at = info.get("更新时间", "")
        collected_at = info.get("收藏时间", "")
        url = info.get("原链接", "")

        likes = parse_int(info.get("赞同/喜欢数", ""))
        comments = parse_int(info.get("评论数", ""))

        date = normalize_date(collected_at) or normalize_date(published_at)

        needs_review = bool(meta.get("needs_review", False))
        if "待判断" in value or "需人工复核" in value:
            needs_review = True

        item = {
            "source_path": str(path),
            "source_file": meta.get("source_file") or path.name,
            "slug": slug,
            "content_id": content_id,
            "title": title,
            "date": date,
            "content_type": content_type,
            "author": author,
            "author_intro": author_intro,
            "published_at": published_at,
            "updated_at": updated_at,
            "collected_at": collected_at,
            "url": url,
            "likes": likes,
            "comments": comments,
            "domain": domain,
            "form": form,
            "value": value,
            "tags": tags,
            "rating": meta.get("rating"),
            "needs_review": needs_review,
            "classification_score": meta.get("classification_score", ""),
            "summary": meta.get("summary", ""),
            "my_comment": meta.get("my_comment", ""),
            "raw_content": article_content,
        }

        items.append(item)

        if idx % 50 == 0:
            print(f"[进度] 已解析 {idx}/{len(files)} 篇")

    print(f"[完成] 共解析 {len(items)} 篇知乎收藏")
    return items


def build_pages(items: List[Dict[str, Any]], out_dir: Path, full_mode: bool) -> None:
    article_dir = out_dir / "items"
    domain_dir = out_dir / "分类"
    form_dir = out_dir / "形式"
    value_dir = out_dir / "价值"

    print(f"[清理] 输出目录：{out_dir}")

    for d in [article_dir, domain_dir, form_dir, value_dir]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    out_dir.mkdir(parents=True, exist_ok=True)

    # 去重 slug
    seen = {}
    for item in items:
        slug = item["slug"]
        if slug not in seen:
            seen[slug] = 1
        else:
            seen[slug] += 1
            item["slug"] = f"{slug}-{seen[slug]}"

    # 生成每篇详情页
    print("[生成] 每篇知乎收藏详情页")
    for idx, item in enumerate(items, start=1):
        page = build_item_page(item, full_mode=full_mode)
        write_text(article_dir / f"{item['slug']}.md", page)

        if idx % 50 == 0:
            print(f"[进度] 已生成详情页 {idx}/{len(items)}")

    # 分组
    domain_groups = defaultdict(list)
    form_groups = defaultdict(list)
    value_groups = defaultdict(list)

    for item in items:
        for d in item.get("domain", []) or ["未分类"]:
            domain_groups[d].append(item)
        for f in item.get("form", []) or ["未分类"]:
            form_groups[f].append(item)
        for v in item.get("value", []) or ["未分类"]:
            value_groups[v].append(item)

    # 排序
    by_likes = sorted(items, key=lambda x: x.get("likes", 0), reverse=True)
    by_title = sorted(items, key=lambda x: x.get("title", ""))
    review_items = [x for x in items if x.get("needs_review")]

    # 首页
    index_lines = []
    index_lines.append("---")
    index_lines.append("title: 知乎收藏")
    index_lines.append("description: Rong 的知乎收藏内容索引")
    index_lines.append("tags:")
    index_lines.append("  - 知乎收藏")
    index_lines.append("  - 个人知识库")
    index_lines.append("---")
    index_lines.append("")
    index_lines.append("# 知乎收藏")
    index_lines.append("")
    index_lines.append("> 这里保存和整理我收藏过的知乎内容。它不是简单堆积，而是一个逐步人工复核、摘要、评论和再分类的资料库。")
    index_lines.append("")
    index_lines.append("## 总览")
    index_lines.append("")
    index_lines.append(f"- 收藏总数：**{len(items)}** 篇")
    index_lines.append(f"- 待人工复核：**{len(review_items)}** 篇")
    index_lines.append(f"- 领域分类数：**{len(domain_groups)}** 个")
    index_lines.append(f"- 内容形式数：**{len(form_groups)}** 个")
    index_lines.append(f"- 价值标签数：**{len(value_groups)}** 个")
    index_lines.append("")
    index_lines.append("## 快速入口")
    index_lines.append("")
    index_lines.append("- [[知乎收藏/全部内容|全部内容]]")
    index_lines.append("- [[知乎收藏/高赞内容|高赞内容]]")
    index_lines.append("- [[知乎收藏/待人工复核|待人工复核]]")
    index_lines.append("")
    index_lines.append("## 领域分类")
    index_lines.append("")
    index_lines.append(make_group_links(domain_groups, "分类"))
    index_lines.append("")
    index_lines.append("## 内容形式")
    index_lines.append("")
    index_lines.append(make_group_links(form_groups, "形式"))
    index_lines.append("")
    index_lines.append("## 价值标签")
    index_lines.append("")
    index_lines.append(make_group_links(value_groups, "价值"))
    index_lines.append("")
    index_lines.append("## 高赞内容预览")
    index_lines.append("")
    index_lines.append(make_table(by_likes[:20]))
    index_lines.append("")
    index_lines.append("> [!note] 维护方式")
    index_lines.append("> 修改原始 Markdown 文件中的 `summary`、`my_comment`、`rating`、`needs_review` 等字段后，重新运行生成脚本即可更新本页。")
    index_lines.append("")
    write_text(out_dir / "index.md", "\n".join(index_lines))

    # 全部内容页
    all_lines = []
    all_lines.append("---")
    all_lines.append("title: 全部知乎收藏")
    all_lines.append("tags:")
    all_lines.append("  - 知乎收藏")
    all_lines.append("---")
    all_lines.append("")
    all_lines.append("# 全部知乎收藏")
    all_lines.append("")
    all_lines.append(f"共 **{len(items)}** 篇。")
    all_lines.append("")
    all_lines.append(make_table(by_title))
    write_text(out_dir / "全部内容.md", "\n".join(all_lines))

    # 高赞内容页
    hot_lines = []
    hot_lines.append("---")
    hot_lines.append("title: 高赞知乎收藏")
    hot_lines.append("tags:")
    hot_lines.append("  - 知乎收藏")
    hot_lines.append("---")
    hot_lines.append("")
    hot_lines.append("# 高赞知乎收藏")
    hot_lines.append("")
    hot_lines.append("按赞同/喜欢数从高到低排列。")
    hot_lines.append("")
    hot_lines.append(make_table(by_likes))
    write_text(out_dir / "高赞内容.md", "\n".join(hot_lines))

    # 待复核页
    review_lines = []
    review_lines.append("---")
    review_lines.append("title: 待人工复核")
    review_lines.append("tags:")
    review_lines.append("  - 知乎收藏")
    review_lines.append("  - 待复核")
    review_lines.append("---")
    review_lines.append("")
    review_lines.append("# 待人工复核")
    review_lines.append("")
    review_lines.append(f"共 **{len(review_items)}** 篇需要人工复核。")
    review_lines.append("")
    review_lines.append(make_table(sorted(review_items, key=lambda x: x.get("likes", 0), reverse=True)))
    write_text(out_dir / "待人工复核.md", "\n".join(review_lines))

    # 分类页
    print("[生成] 分类页")

    for name, group_items in domain_groups.items():
        lines = [
            "---",
            f"title: 知乎收藏 - {name}",
            "tags:",
            "  - 知乎收藏",
            "  - 领域分类",
            "---",
            "",
            f"# {name}",
            "",
            f"共 **{len(group_items)}** 篇。",
            "",
            make_table(sorted(group_items, key=lambda x: x.get("likes", 0), reverse=True)),
        ]
        write_text(domain_dir / f"{name}.md", "\n".join(lines))

    for name, group_items in form_groups.items():
        lines = [
            "---",
            f"title: 知乎收藏 - {name}",
            "tags:",
            "  - 知乎收藏",
            "  - 内容形式",
            "---",
            "",
            f"# {name}",
            "",
            f"共 **{len(group_items)}** 篇。",
            "",
            make_table(sorted(group_items, key=lambda x: x.get("likes", 0), reverse=True)),
        ]
        write_text(form_dir / f"{name}.md", "\n".join(lines))

    for name, group_items in value_groups.items():
        lines = [
            "---",
            f"title: 知乎收藏 - {name}",
            "tags:",
            "  - 知乎收藏",
            "  - 价值标签",
            "---",
            "",
            f"# {name}",
            "",
            f"共 **{len(group_items)}** 篇。",
            "",
            make_table(sorted(group_items, key=lambda x: x.get("likes", 0), reverse=True)),
        ]
        write_text(value_dir / f"{name}.md", "\n".join(lines))

    print("[完成] 所有知乎收藏页面已生成")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="知乎收藏 Markdown 源目录",
    )
    parser.add_argument(
        "--quartz-content",
        default=DEFAULT_QUARTZ_CONTENT,
        help="Quartz content 目录",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="发布原文正文。公开网站慎用。",
    )

    args = parser.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    quartz_content = Path(args.quartz_content).expanduser().resolve()
    out_dir = quartz_content / "知乎收藏"

    print("====== 知乎收藏导入 Quartz ======")
    print(f"[参数] 源目录：{source_dir}")
    print(f"[参数] Quartz content：{quartz_content}")
    print(f"[参数] 输出目录：{out_dir}")
    print(f"[参数] 全文模式：{'开启' if args.full else '关闭'}")

    if not source_dir.exists():
        raise FileNotFoundError(f"源目录不存在：{source_dir}")

    if not quartz_content.exists():
        raise FileNotFoundError(f"Quartz content 目录不存在：{quartz_content}")

    items = collect_items(source_dir)
    build_pages(items, out_dir, full_mode=args.full)

    print("")
    print("====== 下一步 ======")
    print("1. 运行：npx quartz build --serve")
    print("2. 浏览器打开：http://localhost:8080/")
    print("3. 确认无误后运行：npx quartz sync")


if __name__ == "__main__":
    main()
