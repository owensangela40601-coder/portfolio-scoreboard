# Portfolio Scoreboard App

A Flask app that reads portfolio screenshots, builds a student scoreboard, and organizes kids into pods.

## Run locally

1. Install Python and Tesseract OCR.
2. Install packages:

   pip install -r requirements.txt

3. Run:

   python app.py

4. Open:

   http://127.0.0.1:5000

## Notes

- Put screenshots of the positions table, not just the summary page.
- Supported uploads: PNG, JPG, JPEG, WEBP
- Data saves to `pods.json`
- Click a student's name to reopen that student's scorecard
