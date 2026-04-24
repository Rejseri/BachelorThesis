from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


SUSTAINABILITY_HEADING_TERMS = [
    "sustainability",
    "esg",
    "environmental social and governance",
    "non-financial statement",
    "non-financial report",
    "corporate social responsibility",
    "corporate responsibility",
    "responsibility report",
    "climate report",
    "sustainability statement",
    "sustainability report",
    "csrd",
]

ESG_SUBLEVEL_TERMS = [
    "environment",
    "environmental",
    "social",
    "governance",
    "diversity",
    "inclusion",
    "people",
    "human rights",
]

SUSTAINABILITY_BODY_TERMS = [
    "scope 1",
    "scope 2",
    "scope 3",
    "ghg",
    "co2",
    "carbon",
    "emissions",
    "decarbonization",
    "climate",
    "biodiversity",
    "renewable",
    "waste",
    "water",
    "human rights",
    "diversity",
    "inclusion",
    "governance",
    "materiality",
    "double materiality",
    "taxonomy",
    "tcfd",
    "sasb",
    "gri",
]

STOP_SECTION_TERMS = [
    "financial statements",
    "consolidated financial statements",
    "notes to the financial statements",
    "independent auditor",
    "remuneration report",
]


@dataclass
class SustainabilitySection:
    found: bool
    heading: str
    confidence: float
    start_line: int
    end_line: int
    text: str
    match_type: str


def _normalize(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _is_markdown_heading(line: str) -> bool:
    return bool(re.match(r"^\s{0,3}#{1,6}\s+\S", line))


def _heading_level(line: str) -> int:
    m = re.match(r"^\s{0,3}(#{1,6})\s+\S", line)
    if not m:
        return 0
    return len(m.group(1))


def _line_score(line: str, terms: List[str]) -> float:
    low = line.lower()
    score = 0.0
    for term in terms:
        if term in low:
            score += 1.0
    return score


def _contains_any(line: str, terms: List[str]) -> bool:
    low = line.lower()
    return any(term in low for term in terms)


def _body_density_score(text: str) -> float:
    low = text.lower()
    hits = 0
    for term in SUSTAINABILITY_BODY_TERMS:
        hits += low.count(term)
    return hits / max(1.0, len(low) / 2000.0)


def _slice_by_heading(lines: List[str], start_idx: int) -> Tuple[int, int]:
    start_level = _heading_level(lines[start_idx])
    if start_level <= 0:
        return start_idx, len(lines) - 1

    for i in range(start_idx + 1, len(lines)):
        if not _is_markdown_heading(lines[i]):
            continue
        lvl = _heading_level(lines[i])
        if 0 < lvl <= start_level:
            return start_idx, i - 1
    return start_idx, len(lines) - 1


def _normalize_title(text: str) -> str:
    low = text.lower()
    low = re.sub(r"^\s{0,3}#{1,6}\s+", "", low)
    low = re.sub(r"\s+", " ", low)
    return low.strip()


def _extract_toc_titles(lines: List[str]) -> List[str]:
    titles: List[str] = []
    max_scan = min(500, len(lines))
    toc_region = lines[:max_scan]
    in_toc = False

    for raw in toc_region:
        line = raw.strip()
        low = line.lower()
        if not line:
            continue
        if "table of contents" in low or low == "contents" or low.startswith("# contents"):
            in_toc = True
            continue
        if in_toc and line.startswith("#") and not _contains_any(low, SUSTAINABILITY_HEADING_TERMS):
            # Likely left TOC region once real top heading starts.
            break
        if not in_toc:
            continue

        if not _contains_any(low, SUSTAINABILITY_HEADING_TERMS):
            continue

        # Typical TOC line forms:
        # "Sustainability report .......... 42"
        # "ESG 35"
        candidate = re.sub(r"\.{2,}\s*\d{1,4}\s*$", "", line)
        candidate = re.sub(r"\s+\d{1,4}\s*$", "", candidate)
        candidate = candidate.strip("- ").strip()
        if len(candidate) >= 4:
            titles.append(_normalize_title(candidate))

    # Preserve order, deduplicate
    seen = set()
    out: List[str] = []
    for t in titles:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _find_heading_from_toc(lines: List[str], toc_titles: List[str]) -> Optional[int]:
    if not toc_titles:
        return None
    for i, line in enumerate(lines):
        if not _is_markdown_heading(line):
            continue
        h = _normalize_title(line)
        for title in toc_titles:
            if title in h or h in title:
                return i
    return None


def _promote_to_parent_esg_heading(lines: List[str], idx: int) -> int:
    if not (0 <= idx < len(lines)):
        return idx
    if not _is_markdown_heading(lines[idx]):
        return idx
    level = _heading_level(lines[idx])
    # If we already matched a clear ESG parent heading, keep it.
    if _contains_any(lines[idx], SUSTAINABILITY_HEADING_TERMS):
        return idx

    # If we matched a sublevel heading (e.g. Diversity), climb to nearest preceding
    # ESG heading at same or higher hierarchy level.
    if not _contains_any(lines[idx], ESG_SUBLEVEL_TERMS):
        return idx

    for j in range(idx - 1, max(-1, idx - 250), -1):
        if not _is_markdown_heading(lines[j]):
            continue
        parent_level = _heading_level(lines[j])
        if parent_level > level:
            continue
        if _contains_any(lines[j], SUSTAINABILITY_HEADING_TERMS):
            return j
    return idx


def _find_best_heading(lines: List[str]) -> Optional[Tuple[int, float]]:
    best_idx = None
    best_score = 0.0

    for i, line in enumerate(lines):
        if not _is_markdown_heading(line):
            continue
        heading_score = (_line_score(line, SUSTAINABILITY_HEADING_TERMS) * 2.0) + _line_score(
            line, ESG_SUBLEVEL_TERMS
        )
        if heading_score <= 0:
            continue

        local_preview = "\n".join(lines[i : min(len(lines), i + 80)])
        density = _body_density_score(local_preview)
        total_score = (heading_score * 3.0) + density
        if total_score > best_score:
            best_score = total_score
            best_idx = i

    if best_idx is None:
        return None
    return best_idx, best_score


def _extract_dense_fallback(lines: List[str]) -> Optional[SustainabilitySection]:
    window = 140
    if not lines:
        return None

    best_idx = -1
    best_score = 0.0
    for i in range(0, len(lines)):
        snippet = "\n".join(lines[i : i + window])
        score = _body_density_score(snippet)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_idx < 0 or best_score < 4.0:
        return None

    start_idx = best_idx
    end_idx = min(len(lines) - 1, best_idx + window - 1)
    text = "\n".join(lines[start_idx : end_idx + 1]).strip()
    if not text:
        return None

    return SustainabilitySection(
        found=True,
        heading="keyword-density-fallback",
        confidence=min(0.95, 0.35 + (best_score / 10.0)),
        start_line=start_idx + 1,
        end_line=end_idx + 1,
        text=text,
        match_type="density_fallback",
    )


def extract_sustainability_section(markdown_text: str) -> SustainabilitySection:
    cleaned = _normalize(markdown_text or "").strip()
    if not cleaned:
        return SustainabilitySection(
            found=False,
            heading="",
            confidence=0.0,
            start_line=0,
            end_line=0,
            text="",
            match_type="empty",
        )

    lines = cleaned.splitlines()
    toc_titles = _extract_toc_titles(lines)
    toc_idx = _find_heading_from_toc(lines, toc_titles)
    best = _find_best_heading(lines)

    if toc_idx is not None or best is not None:
        if toc_idx is not None:
            start_idx = toc_idx
            score = 8.0 + _body_density_score("\n".join(lines[toc_idx : toc_idx + 120]))
            match_type = "toc_heading"
        else:
            start_idx, score = best  # type: ignore[misc]
            match_type = "heading"

        start_idx = _promote_to_parent_esg_heading(lines, start_idx)
        start_idx, end_idx = _slice_by_heading(lines, start_idx)
        section_text = "\n".join(lines[start_idx : end_idx + 1]).strip()

        # If extracted section is clearly non-sustainability, reject and fallback.
        low = section_text.lower()
        if any(term in low for term in STOP_SECTION_TERMS) and _body_density_score(section_text) < 2.0:
            dense = _extract_dense_fallback(lines)
            if dense is not None:
                return dense

        confidence = min(0.99, 0.45 + (score / 12.0))
        return SustainabilitySection(
            found=True,
            heading=lines[start_idx].strip(),
            confidence=confidence,
            start_line=start_idx + 1,
            end_line=end_idx + 1,
            text=section_text,
            match_type=match_type,
        )

    dense = _extract_dense_fallback(lines)
    if dense is not None:
        return dense

    return SustainabilitySection(
        found=False,
        heading="",
        confidence=0.0,
        start_line=0,
        end_line=0,
        text=cleaned,
        match_type="not_found",
    )
