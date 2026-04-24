import os
import argparse
from pathlib import Path
from docling.document_converter import DocumentConverter

def parse_pdfs_to_markdown(input_folder: str, output_folder: str):
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
    
    # Find all PDF files in the input folder
    pdf_files = list(input_path.glob('*.pdf'))
    
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
    
    args = parser.parse_args()
    
    parse_pdfs_to_markdown(args.input_folder, args.output_folder)