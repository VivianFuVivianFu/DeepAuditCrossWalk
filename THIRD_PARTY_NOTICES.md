# Third-party notices

Dependencies are installed separately and retain their respective notices.

| Dependency | License | Purpose |
| --- | --- | --- |
| FastAPI, Pydantic, openpyxl, python-docx | MIT | API, validation, Excel and Word parsing |
| pypdf | BSD-3-Clause | PDF text extraction |
| defusedxml | PSF-2.0 | Defensive XML parsing |
| Uvicorn, Starlette | BSD-3-Clause | ASGI runtime |
| Next.js, React, TypeScript, Vitest | MIT | Web application and verification |

The PDF parser uses pypdf. PyMuPDF is not a dependency of this distribution.
Review dependency versions and transitive licenses before shipping a binary
distribution or embedding the application in another product. The lists of
resolved packages in dependency locks and SBOMs take precedence over this summary.
