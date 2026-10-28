# DeepAuditCrossWalk engine

Independent Python package for the DeepAuditCrossWalk application. See the
repository README for the product scope, local setup, and release limitations.

Install with `pip install -e '.[dev]'` and run
`uvicorn banking_crosswalk.app:app --host 127.0.0.1 --port 8000`.

The embedded questionnaire is synthetic. Import an authorised AIAF workbook
through `/v1/questionnaires/import` to assess its original questions and routing.
