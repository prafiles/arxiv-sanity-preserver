#!/usr/bin/env bash

cd "$(dirname "$0")" #change to current directory as working directory
PATH=/usr/local/bin/ices:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH #Updating path for CronJob

. env/bin/activate

python3 fetch_papers.py
python3 download_pdfs.py
python3 parse_pdf_to_text.py
python3 thumb_pdf.py
python3 analyze.py
