"""CLI runner for hybrid extraction pipeline."""

from __future__ import annotations

import argparse
import json

from app.engines.extraction.hybrid_pipeline import HybridExtractionPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 4-stage hybrid extraction on one PDF")
    parser.add_argument("pdf_path", help="Path to input PDF")
    parser.add_argument("--model", default=None, help="Ollama model name (default from settings)")
    parser.add_argument("--max-retries", type=int, default=None, help="Max validation retries")
    parser.add_argument(
        "--manual-review-dir",
        default=None,
        help="Directory for PDFs that fail validation after retries",
    )
    args = parser.parse_args()

    pipeline = HybridExtractionPipeline(
        model=args.model,
        max_retries=args.max_retries,
        manual_review_dir=args.manual_review_dir,
        temperature=0.0,
    )

    result = pipeline.run(args.pdf_path)

    payload = {
        "status": result.status,
        "attempts": result.attempts,
        "errors": result.errors,
        "manual_review_path": result.manual_review_path,
        "output": result.output.model_dump() if result.output else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
