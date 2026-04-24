import os
import argparse
import time
from pathlib import Path

"""
Ändra till din hårdvara för optimal kod och parallellisering 
"""
CPU_CORES = 8
RAM_GB = 16

# 1. Document Concurrency: How many PDFs to process at once.
# Docling's AI models (Layout/Tables) use ~3-4GB of RAM per process.
# 16GB / 4GB = 4 workers. We use 3 to stay safe and leave RAM for the OS.
DOC_CONCURRENCY = max(1, RAM_GB // 5) 

# 2. Threading: How many CPU threads each worker uses.
# We distribute our 8 cores across our document workers.
THREADS_PER_WORKER = max(1, CPU_CORES // DOC_CONCURRENCY)
# ==========================================

# Apply threading limits to the system environment before importing docling
os.environ["OMP_NUM_THREADS"] = str(THREADS_PER_WORKER)
os.environ["MKL_NUM_THREADS"] = str(THREADS_PER_WORKER)

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.settings import settings

def parse_pdfs_to_markdown(input_folder: str, output_folder: str):
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Configure Docling to use the hardware-based limits
    pipeline_options = PdfPipelineOptions()
    # Since these are 60-page reports, we chunk them for parallel page parsing
    pipeline_options.page_chunk_size = 15 
    
    # Internal performance settings
    settings.perf.doc_batch_concurrency = DOC_CONCURRENCY
    
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    
    pdf_files = list(input_path.glob('*.pdf'))
    if not pdf_files:
        print(f"No PDF files found in {input_folder}")
        return

    print(f"--- Hardware Profile: {CPU_CORES} Cores | {RAM_GB}GB RAM ---")
    print(f"--- Parallel Strategy: {DOC_CONCURRENCY} Docs at a time | {THREADS_PER_WORKER} Threads each ---")
    print(f"Processing {len(pdf_files)} files...")

    start_time = time.time()
    
    # convert_all is the fastest way to run docling in a batch
    results = converter.convert_all(pdf_files, raises_on_error=False)
    
    for result in results:
        if result.document:
            file_stem = Path(result.input.file).stem
            output_file = output_path / f"{file_stem}.md"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result.document.export_to_markdown())
            print(f"Done: {file_stem}.md")
        else:
            print(f"Error processing a file.")

    end_time = time.time()
    print(f"\nFinished in {round(end_time - start_time, 2)} seconds.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_folder", type=str, default="AnnualReports2023")
    parser.add_argument("--output_folder", type=str, default="ParsedReports2023")
    args = parser.parse_args()
    
    parse_pdfs_to_markdown(args.input_folder, args.output_folder)