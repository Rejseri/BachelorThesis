import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF


@dataclass
class SectionMatch:
    start_page: int
    end_page: int
    score: float
    trigger: str
    text: str


HEADING_PATTERNS = [
    r"\bsustainability report\b",
    r"\bsustainability statement\b",
    r"\bsustainability section\b",
    r"\bsustainability\b",
    r"\besg report\b",
    r"\benvironmental[, ]+social[, ]+and governance\b",
    r"\besg\b",
    r"\bnon[- ]financial report\b",
    r"\bcorporate responsibility\b",
    r"\bcsr report\b",
    r"\bresponsibility report\b",
    r"\bnon[- ]financial statement\b",
    r"\bbaeredygtighed\b",
    r"\bhallbarhet\b",
    r"\bnachhaltigkeit\b",
]

POSITIVE_KEYWORDS = {
    "sustainability": 4.0,
    "esg": 2.5,
    "scope 1": 1.0,
    "scope 2": 1.0,
    "scope 3": 1.0,
    "ghg": 1.0,
    "co2": 1.0,
    "emissions": 1.0,
    "climate": 1.2,
    "decarbonization": 1.0,
    "human rights": 0.8,
    "diversity": 0.6,
    "governance": 0.7,
    "materiality": 1.0,
    "double materiality": 1.2,
    "csrd": 1.2,
    "taxonomy": 0.7,
    "tcfd": 0.7,
    "sasb": 0.7,
    "gri": 0.7,
    "baeredygtighed": 1.3,
    "hallbarhet": 1.2,
    "nachhaltigkeit": 1.2,
}

STOP_HEADING_PATTERNS = [
    r"\bconsolidated financial statements\b",
    r"\bfinancial statements\b",
    r"\bnotes to the financial statements\b",
    r"\bauditor'?s report\b",
    r"\bindependent auditor'?s report\b",
    r"\bcorporate governance statement\b",
]

NEGATIVE_KEYWORDS = [
    "consolidated financial statements",
    "notes to the financial statements",
    "independent auditor",
    "statement of cash flows",
    "income statement",
    "balance sheet",
    "shareholders",
    "dividend",
    "remuneration report",
    "board of directors report",
]


def normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pages_text(pdf_path: Path) -> List[str]:
    pages_text: List[str] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text = page.get_text("text")
            pages_text.append(normalize_whitespace(text))
    return pages_text


def keyword_score(text: str) -> float:
    low = text.lower()
    total = 0.0
    for kw, weight in POSITIVE_KEYWORDS.items():
        if any(ch in kw for ch in "[](){}?+*\\|"):
            hits = len(re.findall(kw, low, flags=re.IGNORECASE))
        else:
            hits = low.count(kw)
        total += hits * weight
    # scale by text length to avoid bias toward very long sections
    length_norm = max(len(low) / 2000.0, 1.0)
    return total / length_norm


def page_heading_hits(page_text: str, patterns: Sequence[str]) -> List[str]:
    first_lines = "\n".join(page_text.splitlines()[:40]).lower()
    hits: List[str] = []
    for p in patterns:
        if re.search(p, first_lines, flags=re.IGNORECASE):
            hits.append(p)
    return hits


def detect_start_page(pages: Sequence[str]) -> Optional[Tuple[int, str]]:
    toc_start = detect_start_from_toc(pages)
    if toc_start:
        return toc_start

    for idx, page_text in enumerate(pages):
        hits = page_heading_hits(page_text, HEADING_PATTERNS)
        if hits:
            return idx, hits[0]

    # Fallback: choose first page with high sustainability density.
    best_idx = None
    best_score = 0.0
    for idx, page_text in enumerate(pages):
        first_half = page_text[:4000]
        score = keyword_score(first_half)
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_idx is not None and best_score >= 7.0:
        return best_idx, "keyword-density-fallback"
    return None


def detect_start_from_toc(pages: Sequence[str]) -> Optional[Tuple[int, str]]:
    # TOC is usually early in the document.
    for toc_idx in range(min(15, len(pages))):
        page = pages[toc_idx].lower()
        if "contents" not in page and "table of contents" not in page and "indhold" not in page:
            continue
        lines = page.splitlines()
        for line in lines:
            for pattern in HEADING_PATTERNS:
                if re.search(pattern, line, flags=re.IGNORECASE):
                    page_match = re.search(r"(\d{1,3})\s*$", line.strip())
                    if page_match:
                        candidate = int(page_match.group(1)) - 1
                        if 0 <= candidate < len(pages):
                            return candidate, f"toc:{pattern}"
    return None


def detect_end_page(pages: Sequence[str], start_idx: int) -> int:
    max_scan = min(len(pages), start_idx + 120)
    for idx in range(start_idx + 1, max_scan):
        next_hits = page_heading_hits(pages[idx], STOP_HEADING_PATTERNS)
        if next_hits:
            return idx - 1
    # If no explicit stop heading was found, use declining keyword density to stop.
    prev_high = keyword_score(pages[start_idx])
    for idx in range(start_idx + 1, max_scan):
        score = keyword_score(pages[idx])
        if score < 0.15 and prev_high > 0.8 and idx > start_idx + 4:
            return idx - 1
        prev_high = max(prev_high * 0.9, score)
    return max_scan - 1


def trim_noise_paragraphs(text: str) -> str:
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
    if not blocks:
        return text

    cleaned: List[str] = []
    for block in blocks:
        low = block.lower()
        # Drop repeated footer/header-like short lines with page numbers.
        if len(block) < 50 and re.search(r"\b(page|annual report|copyright|\d{4})\b", low):
            continue
        cleaned.append(block)
    return "\n\n".join(cleaned)


def keep_only_sustainability_paragraphs(text: str) -> str:
    """
    Keep only paragraphs strongly related to sustainability reporting.
    This is a strict post-filter to avoid unrelated annual report content.
    """
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
    kept: List[str] = []

    for i, block in enumerate(blocks):
        low = block.lower()
        if any(nk in low for nk in NEGATIVE_KEYWORDS):
            continue

        score = keyword_score(block)
        has_heading_signal = any(
            re.search(p, low, flags=re.IGNORECASE) for p in HEADING_PATTERNS
        )

        # Keep strict relevance paragraphs:
        # - strong keyword score, or
        # - explicit sustainability heading signal.
        if score >= 0.45 or has_heading_signal:
            kept.append(block)
            continue

        # Contextual keep: if both neighboring paragraphs are strong sustainability text.
        prev_score = keyword_score(blocks[i - 1]) if i > 0 else 0.0
        next_score = keyword_score(blocks[i + 1]) if i + 1 < len(blocks) else 0.0
        if prev_score >= 0.9 and next_score >= 0.9 and len(block) > 80:
            kept.append(block)

    return "\n\n".join(kept).strip()


def extract_sustainability_section(pdf_path: Path) -> Optional[SectionMatch]:
    pages = extract_pages_text(pdf_path)
    if not pages:
        return None

    if _likely_scanned(pages):
        ocr_pages = try_ocr_pages(pdf_path)
        if ocr_pages:
            merged_pages = []
            for i, base in enumerate(pages):
                if len(base.strip()) < 50:
                    merged_pages.append(ocr_pages[i])
                else:
                    merged_pages.append(base)
            pages = merged_pages

    start = detect_start_page(pages)
    if not start:
        start = best_window_start(pages)
        if not start:
            return None
    start_idx, trigger = start
    end_idx = detect_end_page(pages, start_idx)

    section_text = "\n\n".join(pages[start_idx : end_idx + 1]).strip()
    section_text = trim_noise_paragraphs(normalize_whitespace(section_text))
    section_text = keep_only_sustainability_paragraphs(section_text)
    if not section_text:
        return None
    score = keyword_score(section_text)
    return SectionMatch(
        start_page=start_idx + 1,
        end_page=end_idx + 1,
        score=score,
        trigger=trigger,
        text=section_text,
    )


def best_window_start(pages: Sequence[str]) -> Optional[Tuple[int, str]]:
    # Fallback: pick the center of the best sustainability-heavy 3-page window.
    if not pages:
        return None
    best_idx = -1
    best = 0.0
    for i in range(len(pages)):
        window = pages[max(0, i - 1) : min(len(pages), i + 2)]
        score = keyword_score("\n".join(window))
        if score > best:
            best = score
            best_idx = i
    if best_idx >= 0 and best >= 3.5:
        return best_idx, "window-keyword-fallback"
    return None


def _likely_scanned(pages: Sequence[str]) -> bool:
    non_empty = [p for p in pages if p.strip()]
    if not non_empty:
        return True
    short_pages = sum(1 for p in non_empty if len(p) < 80)
    return (short_pages / len(non_empty)) > 0.7


def try_ocr_pages(pdf_path: Path) -> Optional[List[str]]:
    """
    Optional OCR fallback for image-based PDFs.
    Requires pytesseract + pillow to be installed in the environment.
    """
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return None

    ocr_pages: List[str] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img)
            ocr_pages.append(normalize_whitespace(text))
    return ocr_pages


def write_outputs(
    output_dir: Path,
    pdf_name: str,
    match: SectionMatch,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(pdf_name).stem
    txt_path = output_dir / f"{stem}_sustainability.txt"
    meta_path = output_dir / f"{stem}_sustainability.meta.json"

    txt_path.write_text(match.text, encoding="utf-8")
    meta = {
        "source_file": pdf_name,
        "start_page": match.start_page,
        "end_page": match.end_page,
        "score": round(match.score, 3),
        "trigger": match.trigger,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def process_directory(input_dir: Path, output_dir: Path) -> Dict[str, str]:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in: {input_dir}")

    results: Dict[str, str] = {}
    for pdf in pdf_files:
        print(f"\nProcessing: {pdf.name}")
        try:
            match = extract_sustainability_section(pdf)
            if not match:
                results[pdf.name] = "No sustainability section detected."
                print("  -> No sustainability section detected.")
                continue

            write_outputs(output_dir, pdf.name, match)
            results[pdf.name] = (
                f"Extracted pages {match.start_page}-{match.end_page} "
                f"(score={match.score:.2f}, trigger={match.trigger})"
            )
            print(f"  -> {results[pdf.name]}")
        except Exception as exc:
            results[pdf.name] = f"Failed: {exc}"
            print(f"  -> Failed: {exc}")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract sustainability report text from annual report PDFs."
    )
    parser.add_argument(
        "--input-dir",
        default="AnnualReports2023",
        help="Directory containing annual report PDFs.",
    )
    parser.add_argument(
        "--output-dir",
        default="Annualreports2023txt",
        help="Final output directory for extracted sustainability TXT files and metadata.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    results = process_directory(input_dir, output_dir)
    print("\n=== Extraction Summary ===")
    for name, status in results.items():
        print(f"- {name}: {status}")


if __name__ == "__main__":
    main()
