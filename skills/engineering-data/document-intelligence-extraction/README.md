# Document Intelligence Extraction

This public community skill provides deterministic source classification, extraction routing, and a source-traceable evidence contract for mixed engineering documents and images.

It deliberately separates two concerns:

- adapters and AI tools recover text, tables, coordinates, and visual relationships;
- this package plans the required operations and validates every extracted engineering fact before downstream use.

Supported intake families include PDF, Word/OpenDocument, Excel/CSV, presentations, plain text, and common raster images. Scanned PDFs and images route through OCR and vision; digital files retain native text/table extraction so structure is not discarded.

## Install and test

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Optional dependency groups are available as `pdf`, `office`, `ocr`, and `all`. External OCR engines and multimodal models remain adapter/runtime concerns.
