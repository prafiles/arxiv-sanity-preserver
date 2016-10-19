#!/usr/bin/env bash

source env/bin/activate

python fetch_papers.py
python download_pdf.py
python parse_pdf_to_text.py
python thumb_pdf.py
python analyze.py
