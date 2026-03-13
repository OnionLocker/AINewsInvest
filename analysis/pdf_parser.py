"""
analysis/pdf_parser.py - PDF 年报解析器

参考龟龟框架 scripts/pdf_preprocessor.py 的设计:
- 使用 pdfplumber 提取特定章节
- 目标章节: 受限资产、应收账款账龄、关联交易、或有事项、非经常性损益、经营分析、子公司

输入: PDF 文件路径
输出: 结构化 dict (各章节文本)

使用场景: 用户上传年报 PDF → 提取关键信息 → 喂给 LLM 做深度分析
"""
import os
import re
from utils.logger import app_logger

SECTION_KEYWORDS = {
    "restricted_assets": ["受限资产", "使用受到限制", "受到限制的资产"],
    "ar_aging": ["账龄分析", "应收账款账龄", "按账龄列示"],
    "related_party": ["关联方交易", "关联交易", "关联方关系"],
    "contingent": ["或有事项", "未决诉讼", "担保事项"],
    "non_recurring": ["非经常性损益", "非经常性损益明细"],
    "mda": ["经营情况讨论与分析", "管理层讨论与分析", "董事会报告"],
    "subsidiaries": ["主要子公司", "纳入合并范围", "子公司情况"],
}

SECTION_LABELS = {
    "restricted_assets": "受限资产",
    "ar_aging": "应收账款账龄",
    "related_party": "关联方交易",
    "contingent": "或有事项",
    "non_recurring": "非经常性损益",
    "mda": "经营情况讨论与分析",
    "subsidiaries": "主要子公司",
}

MAX_SECTION_CHARS = 3000
MAX_TOTAL_PAGES = 300


def parse_annual_report(pdf_path: str) -> dict | None:
    """
    解析 A 股年报 PDF，提取关键章节内容。

    参数:
        pdf_path: PDF 文件路径

    返回:
    {
        "file_name": str,
        "total_pages": int,
        "sections": {
            "restricted_assets": {"label": str, "content": str, "page_range": str},
            "ar_aging": {...},
            ...
        },
        "extracted_count": int,  # 成功提取的章节数
    }
    失败返回 None。
    """
    if not os.path.exists(pdf_path):
        app_logger.warning(f"[PDF] 文件不存在: {pdf_path}")
        return None

    try:
        import pdfplumber
    except ImportError:
        app_logger.error("[PDF] pdfplumber 未安装，请执行 pip install pdfplumber")
        return None

    try:
        return _parse_core(pdf_path, pdfplumber)
    except Exception as e:
        app_logger.error(f"[PDF] 解析失败 {pdf_path}: {e}")
        return None


def _parse_core(pdf_path: str, pdfplumber) -> dict:
    file_name = os.path.basename(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        if total_pages > MAX_TOTAL_PAGES:
            app_logger.warning(
                f"[PDF] 页数过多({total_pages}), 仅处理前{MAX_TOTAL_PAGES}页")

        page_texts = []
        for i, page in enumerate(pdf.pages[:MAX_TOTAL_PAGES]):
            text = page.extract_text() or ""
            page_texts.append(text)

    sections = {}
    for key, keywords in SECTION_KEYWORDS.items():
        result = _find_section(page_texts, keywords)
        if result:
            sections[key] = {
                "label": SECTION_LABELS.get(key, key),
                "content": result["content"],
                "page_range": result["page_range"],
            }
        else:
            sections[key] = {
                "label": SECTION_LABELS.get(key, key),
                "content": "",
                "page_range": "",
            }

    extracted = sum(1 for s in sections.values() if s["content"])

    return {
        "file_name": file_name,
        "total_pages": total_pages,
        "sections": sections,
        "extracted_count": extracted,
    }


def _find_section(page_texts: list[str], keywords: list[str]) -> dict | None:
    """
    在所有页面文本中搜索关键词，找到后提取该位置起的内容。
    向后延伸直到遇到下一个大标题或达到字数上限。
    """
    for page_idx, text in enumerate(page_texts):
        for kw in keywords:
            pos = text.find(kw)
            if pos == -1:
                continue

            content_parts = [text[pos:]]
            current_len = len(content_parts[0])
            end_page = page_idx

            for next_idx in range(page_idx + 1, min(page_idx + 5, len(page_texts))):
                if current_len >= MAX_SECTION_CHARS:
                    break
                next_text = page_texts[next_idx]
                if _is_new_major_section(next_text):
                    break
                content_parts.append(next_text)
                current_len += len(next_text)
                end_page = next_idx

            full_content = "\n".join(content_parts)
            if len(full_content) > MAX_SECTION_CHARS:
                full_content = full_content[:MAX_SECTION_CHARS] + "...(截断)"

            full_content = _clean_text(full_content)

            if page_idx == end_page:
                page_range = f"第{page_idx + 1}页"
            else:
                page_range = f"第{page_idx + 1}-{end_page + 1}页"

            return {"content": full_content, "page_range": page_range}

    return None


_MAJOR_SECTION_PATTERN = re.compile(
    r'^[一二三四五六七八九十]{1,2}[、.]\s*[^\n]{2,20}$',
    re.MULTILINE
)


def _is_new_major_section(text: str) -> bool:
    """判断页面开头是否是新的大章节（一、xxx 格式）"""
    first_lines = text[:200]
    return bool(_MAJOR_SECTION_PATTERN.search(first_lines))


def _clean_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {4,}', '  ', text)
    return text.strip()


def format_for_llm(parsed: dict) -> str:
    """
    将解析结果格式化为适合喂给 LLM 的文本。
    """
    if not parsed:
        return "PDF 解析失败，无法提取内容。"

    parts = [f"年报: {parsed['file_name']} (共{parsed['total_pages']}页)\n"]

    for key, section in parsed["sections"].items():
        if not section["content"]:
            continue
        parts.append(f"\n## {section['label']} ({section['page_range']})\n")
        parts.append(section["content"])

    if parsed["extracted_count"] == 0:
        parts.append("\n未能从该 PDF 中提取到关键章节内容。")

    return "\n".join(parts)
