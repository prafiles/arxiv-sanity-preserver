#!/usr/bin/env bash

source env/bin/activate

python fetch_papers.py
download_pdf.py
parse_pdf_to_text.py
thumb_pdf.py
analyze.py
buildsvm.py

pm2 restart -1