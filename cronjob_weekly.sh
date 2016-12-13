#!/usr/bin/env bash

cd "$(dirname "$0")" #change to current directory as working directory
PATH=/usr/local/bin/ices:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH #Updating path for CronJob

. env/bin/activate

python fetch_papers.py
python download_pdfs.py
python parse_pdf_to_text.py
python thumb_pdf.py
python analyze.py
