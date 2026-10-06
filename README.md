# Darija Pharmacy Assistant

A local, searchable consultation interface for the Moroccan medicine catalog exported in `moroccan_medications.csv`.

## Run locally

```bash
export OPENAI_API_KEY="your_api_key"
# Optional: choose an API model available to your account.
export OPENAI_MODEL="gpt-6-astra"
python3 app.py
```

Open <http://127.0.0.1:8000>. No package installation is required. On first run, the app builds `pharmacy.db`, an indexed local cache that is intentionally ignored by Git.

## What is functional

- Full-text local search by brand, substance active, dosage, form, and marketing status
- Paginated results, medicine detail sheets, and an actual CSV export of the current results
- A real multi-turn chatbot using the OpenAI Responses API and a server-side tool loop. The model can call `search_catalog` and `get_medication`; it never receives database access or raw SQL.
- A JSON API: `/api/health`, `/api/medications`, `/api/medications/{id}`, `/api/export`, and `/api/chat`

## Safety and data limits

This is a catalog browser, not a prescribing or diagnostic system. It deliberately does not provide individual doses, diagnoses, contraindications, interaction checking, or availability guarantees. Prices, status, and catalog fields can be outdated; confirm them with a pharmacist and consult a clinician for medical decisions.

The API key stays in the server environment (or a local `.env` file that is ignored by Git); it is never sent to the browser. Without `OPENAI_API_KEY`, the catalog app works but chat is explicitly disabled rather than replaced with a pretend chatbot.

The current dataset comes from the existing AMMPS scrape/export in this repository. Refresh it with the scraper only when you have reviewed that source and its current terms.
