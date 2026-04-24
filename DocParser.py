import argparse
import json
from pathlib import Path

from docling.document_converter import DocumentConverter
from sentiment_analyzer import SentimentAnalyzer, SentimentConfig, build_default_model_path
from sustainability_section_finder import extract_sustainability_section


def parse_pdfs_to_markdown(
    input_folder: str,
    output_folder: str,
    sentiment_model: str,
    max_chunk_tokens: int,
    device: str,
    disable_sentiment: bool,
    sentiment_scope: str,
    min_section_confidence: float,
):
    """
    Parses all PDF files in the input_folder and saves them as Markdown files in the output_folder.
    """
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    
    # Ensure output directory exists
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize DocumentConverter
    print("Initializing DocumentConverter...")
    converter = DocumentConverter()
    
    # Initialize sentiment analyzer once for the full run.
    analyzer = None
    if not disable_sentiment:
        print("Initializing sentiment analyzer...")
        analyzer = SentimentAnalyzer(
            SentimentConfig(
                model_path=sentiment_model,
                max_chunk_tokens=max_chunk_tokens,
                device=device,
            )
        )

    # Find all PDF files in the input folder
    pdf_files = list(input_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in {input_folder}")
        return

    print(f"Found {len(pdf_files)} PDF files. Starting conversion...")
    
    for pdf_file in pdf_files:
        print(f"Processing: {pdf_file.name}...")
        try:
            # Convert document
            result = converter.convert(str(pdf_file))
            
            # Export to Markdown
            markdown_content = result.document.export_to_markdown()
            
            # Define output file path
            output_file = output_path / f"{pdf_file.stem}.md"
            
            # Save Markdown content
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            if analyzer is not None:
                sentiment_input = markdown_content
                extraction_meta = {
                    "scope_requested": sentiment_scope,
                    "scope_used": "full_report",
                    "section_found": False,
                    "section_heading": "",
                    "section_confidence": 0.0,
                    "section_line_start": 0,
                    "section_line_end": 0,
                    "match_type": "disabled",
                }

                if sentiment_scope == "sustainability":
                    section = extract_sustainability_section(markdown_content)
                    section_accepted = (
                        section.found
                        and section.text.strip() != ""
                        and section.confidence >= min_section_confidence
                    )
                    extraction_meta = {
                        "scope_requested": sentiment_scope,
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
                    if section_accepted:
                        sentiment_input = section.text

                    section_output_file = output_path / f"{pdf_file.stem}.sustainability.md"
                    if section.found and section.text.strip():
                        with open(section_output_file, "w", encoding="utf-8") as f:
                            f.write(section.text)
                        print(f"Sustainability section saved to: {section_output_file}")
                    else:
                        with open(section_output_file, "w", encoding="utf-8") as f:
                            f.write(
                                "# Sustainability section not confidently detected\n\n"
                                "Sentiment was calculated on the full report markdown.\n"
                            )
                        print(
                            "No clear sustainability section found; "
                            f"wrote note file: {section_output_file}"
                        )

                    if section.found and not section_accepted:
                        print(
                            "Sustainability section detected but rejected by strict threshold "
                            f"({section.confidence:.3f} < {min_section_confidence:.3f}); "
                            "using full report for sentiment."
                        )

                sentiment_result = analyzer.analyze(sentiment_input)
                sentiment_result["file_name"] = pdf_file.name
                sentiment_result["text_scope"] = extraction_meta
                sentiment_output_file = output_path / f"{pdf_file.stem}.sentiment.json"
                with open(sentiment_output_file, "w", encoding="utf-8") as f:
                    json.dump(sentiment_result, f, indent=2)
                print(f"Sentiment saved to: {sentiment_output_file}")

            print(f"Successfully converted and saved to: {output_file}")
        except Exception as e:
            print(f"Failed to convert {pdf_file.name}. Error: {e}")

if __name__ == "__main__":
    # Hyperparameters for the folder paths
    # You can change these defaults or pass them via command line arguments
    DEFAULT_INPUT_FOLDER = "AnnualReports2023"
    DEFAULT_OUTPUT_FOLDER = "ParsedReports2023"

    parser = argparse.ArgumentParser(description="Parse PDF files to Markdown using Docling.")
    parser.add_argument(
        "--input_folder",
        type=str,
        default=DEFAULT_INPUT_FOLDER,
        help="Path to the folder containing PDF files."
    )
    parser.add_argument(
        "--output_folder",
        type=str,
        default=DEFAULT_OUTPUT_FOLDER,
        help="Path to the folder where Markdown files will be saved."
    )
    parser.add_argument(
        "--sentiment_model",
        type=str,
        default=build_default_model_path(),
        help="Local path or HF model id for sentiment sequence-classification model."
    )
    parser.add_argument(
        "--max_chunk_tokens",
        type=int,
        default=512,
        help="Max number of tokens per sentiment chunk."
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Torch device for sentiment inference."
    )
    parser.add_argument(
        "--disable_sentiment",
        action="store_true",
        help="Disable sentiment analysis and only parse PDFs to Markdown."
    )
    parser.add_argument(
        "--sentiment_scope",
        type=str,
        default="sustainability",
        choices=["sustainability", "full_report"],
        help="Analyze only sustainability section (default) or full report markdown.",
    )
    parser.add_argument(
        "--min_section_confidence",
        type=float,
        default=0.75,
        help="Strict minimum confidence required to use detected sustainability section.",
    )

    args = parser.parse_args()

    parse_pdfs_to_markdown(
        input_folder=args.input_folder,
        output_folder=args.output_folder,
        sentiment_model=args.sentiment_model,
        max_chunk_tokens=args.max_chunk_tokens,
        device=args.device,
        disable_sentiment=args.disable_sentiment,
        sentiment_scope=args.sentiment_scope,
        min_section_confidence=args.min_section_confidence,
    )