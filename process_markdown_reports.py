from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

from sentiment_analyzer import SentimentAnalyzer, SentimentConfig, build_default_model_path
from sustainability_section_finder import extract_sustainability_section


def process_markdown_reports(
    input_folder: str,
    output_folder: str,
    sentiment_model: str,
    max_chunk_tokens: int,
    device: str,
    min_section_confidence: float,
) -> Dict[str, str]:
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input folder not found: {input_path}")

    md_files = sorted(input_path.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md files found in: {input_path}")

    print("Initializing sentiment analyzer...")
    analyzer = SentimentAnalyzer(
        SentimentConfig(
            model_path=sentiment_model,
            max_chunk_tokens=max_chunk_tokens,
            device=device,
        )
    )

    summary: Dict[str, str] = {}
    print(f"Found {len(md_files)} markdown files. Starting processing...")

    for md_file in md_files:
        print(f"Processing: {md_file.name}...")
        try:
            markdown_text = md_file.read_text(encoding="utf-8")
            section = extract_sustainability_section(markdown_text)

            section_accepted = (
                section.found
                and section.text.strip() != ""
                and section.confidence >= min_section_confidence
            )
            sentiment_input = section.text if section_accepted else markdown_text

            section_out = output_path / f"{md_file.stem}.sustainability.md"
            if section.found and section.text.strip():
                section_out.write_text(section.text, encoding="utf-8")
            else:
                section_out.write_text(
                    "# Sustainability section not confidently detected\n\n"
                    "Sentiment was calculated on the full report markdown.\n",
                    encoding="utf-8",
                )

            result = analyzer.analyze(sentiment_input)
            result["file_name"] = md_file.name
            result["text_scope"] = {
                "scope_requested": "sustainability",
                "scope_used": "sustainability_section" if section_accepted else "full_report",
                "section_found": section.found,
                "section_accepted": section_accepted,
                "min_section_confidence": min_section_confidence,
                "section_heading": section.heading,
                "section_confidence": round(section.confidence, 4),
                "section_line_start": section.start_line,
                "section_line_end": section.end_line,
                "match_type": section.match_type,
            }

            sentiment_out = output_path / f"{md_file.stem}.sentiment.json"
            sentiment_out.write_text(json.dumps(result, indent=2), encoding="utf-8")

            summary[md_file.name] = (
                f"ok | scope={result['text_scope']['scope_used']} "
                f"| conf={result['text_scope']['section_confidence']}"
            )
            print(f"  -> Sentiment saved to: {sentiment_out}")
        except (OSError, ValueError, RuntimeError) as exc:
            summary[md_file.name] = f"failed | {exc}"
            print(f"  -> Failed: {exc}")

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process parsed markdown annual reports with ESG extraction + sentiment."
    )
    parser.add_argument(
        "--input_folder",
        type=str,
        default="ParsedReports2023",
        help="Folder containing parsed .md reports.",
    )
    parser.add_argument(
        "--output_folder",
        type=str,
        default="ProcessedReports2023",
        help="Folder to write .sustainability.md and .sentiment.json files.",
    )
    parser.add_argument(
        "--sentiment_model",
        type=str,
        default=build_default_model_path(),
        help="Local path or HF model id for sentiment sequence-classification model.",
    )
    parser.add_argument(
        "--max_chunk_tokens",
        type=int,
        default=512,
        help="Max number of tokens per sentiment chunk.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Torch device for sentiment inference.",
    )
    parser.add_argument(
        "--min_section_confidence",
        type=float,
        default=0.75,
        help="Strict minimum confidence required to use detected sustainability section.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = process_markdown_reports(
        input_folder=args.input_folder,
        output_folder=args.output_folder,
        sentiment_model=args.sentiment_model,
        max_chunk_tokens=args.max_chunk_tokens,
        device=args.device,
        min_section_confidence=args.min_section_confidence,
    )
    print("\n=== Processing Summary ===")
    for name, status in summary.items():
        print(f"- {name}: {status}")


if __name__ == "__main__":
    main()
