"""Read-only AIAF workbook importer.

The importer intentionally loads the workbook twice: once for formula text and
once for cached values.  It never saves the source.  Extended x14 validation
rules are read directly from the XLSX ZIP because openpyxl warns that it drops
those extensions when a workbook is saved.
"""

from __future__ import annotations

import hashlib
import io
import re
import warnings
import zipfile
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional

from defusedxml import ElementTree as ET
from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries

from .models import QuestionBank, QuestionnaireMetadata, QuestionRecord


EXPECTED_SHEETS = {
    "Questions",
    "Triggers",
    "ALL Focus Questions",
    "Risks",
    "Treatments",
}

MAX_WORKBOOK_BYTES = 20 * 1024 * 1024
MAX_WORKBOOK_MEMBERS = 2_000
MAX_WORKBOOK_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_WORKBOOK_PART_BYTES = 50 * 1024 * 1024
MAX_WORKSHEET_ROWS = 20_000
MAX_WORKSHEET_COLUMNS = 500
MAX_WORKSHEET_CELLS = 250_000
MAX_TOTAL_WORKSHEET_CELLS = 750_000
MAX_ANY_WORKSHEET_ROWS = 100_000
MAX_ANY_WORKSHEET_COLUMNS = 10_000


def _validate_worksheet_archives(archive: zipfile.ZipFile) -> None:
    """Stream worksheet XML before openpyxl builds a large in-memory graph.

    ZIP metadata limits alone are insufficient: a relatively small worksheet
    XML part can describe millions of cells whose Python objects consume far
    more memory than the decompressed XML.  Count actual row/cell elements and
    validate cell coordinates while retaining only one parsed element at a
    time.
    """

    sheet_parts = _workbook_sheet_parts(archive)
    source_parts = {
        part: name for name, part in sheet_parts.items() if name in EXPECTED_SHEETS
    }
    total_cells = 0

    for member in archive.infolist():
        normalised_name = str(PurePosixPath(member.filename.replace("\\", "/")))
        if not (
            normalised_name.startswith("xl/worksheets/")
            and normalised_name.endswith(".xml")
        ):
            continue

        source_name = source_parts.get(normalised_name)
        row_limit = MAX_WORKSHEET_ROWS if source_name else MAX_ANY_WORKSHEET_ROWS
        column_limit = (
            MAX_WORKSHEET_COLUMNS if source_name else MAX_ANY_WORKSHEET_COLUMNS
        )
        row_count = 0
        cell_count = 0
        try:
            with archive.open(member) as stream:
                for _, element in ET.iterparse(stream, events=("end",)):
                    local_name = element.tag.rsplit("}", 1)[-1]
                    if local_name == "row":
                        row_count += 1
                        if row_count > row_limit:
                            raise ValueError(
                                f"Worksheet {source_name or normalised_name!r} contains too many rows"
                            )
                    elif local_name == "c":
                        cell_count += 1
                        total_cells += 1
                        if cell_count > MAX_WORKSHEET_CELLS:
                            raise ValueError(
                                f"Worksheet {source_name or normalised_name!r} contains too many cells"
                            )
                        if total_cells > MAX_TOTAL_WORKSHEET_CELLS:
                            raise ValueError(
                                "Workbook contains too many worksheet cells"
                            )

                        reference = element.attrib.get("r", "")
                        if reference:
                            try:
                                row_index, column_index = coordinate_to_tuple(reference)
                            except (TypeError, ValueError) as exc:
                                raise ValueError(
                                    f"Worksheet {source_name or normalised_name!r} contains an invalid cell reference"
                                ) from exc
                            if row_index > row_limit or column_index > column_limit:
                                raise ValueError(
                                    f"Worksheet {source_name or normalised_name!r} exceeds the supported dimensions"
                                )
                    element.clear()
        except ET.ParseError as exc:
            raise ValueError(
                f"Worksheet {source_name or normalised_name!r} contains invalid XML"
            ) from exc


def _validate_workbook_archive(raw: bytes) -> None:
    """Reject oversized, encrypted or structurally dangerous XLSX archives."""
    if len(raw) > MAX_WORKBOOK_BYTES:
        raise ValueError("Workbook exceeds the 20 MB import limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > MAX_WORKBOOK_MEMBERS:
                raise ValueError("Workbook contains too many archive members")
            total_size = 0
            for member in members:
                path = PurePosixPath(member.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Workbook contains an unsafe archive path")
                if member.flag_bits & 0x1:
                    raise ValueError("Encrypted workbook archives are not supported")
                if member.file_size > MAX_WORKBOOK_PART_BYTES:
                    raise ValueError("Workbook contains an oversized archive part")
                total_size += member.file_size
                if total_size > MAX_WORKBOOK_UNCOMPRESSED_BYTES:
                    raise ValueError("Workbook expands beyond the 100 MB import limit")
            _validate_worksheet_archives(archive)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError("Workbook is not a valid XLSX archive") from exc


QUESTION_TEXT_HEADER_NAMES = {
    "question",
    "question text",
    "question_text",
    "question description",
    "questions",
    "requirement",
    "requirement text",
    "requirement description",
    "requirements",
    "control description",
    "control requirement",
    "assurance question",
    "assessment question",
    "prompt",
    "item description",
    "audit question",
    "evaluation question",
    "clause text",
    "description",
    "governance question",
    "control objective",
}

QUESTION_ID_HEADER_NAMES = {
    "id",
    "question id",
    "question_id",
    "qid",
    "q id",
    "item id",
    "item",
    "item no",
    "item number",
    "ref",
    "reference",
    "ref no",
    "ref id",
    "reference id",
    "code",
    "control id",
    "clause id",
    "no",
    "number",
}

DOMAIN_HEADER_NAMES = {
    "domain",
    "risk domain",
    "category",
    "topic",
    "section",
    "risk area",
    "theme",
    "pillar",
    "area",
    "stream",
}

ANSWER_HEADER_NAMES = {
    "answer",
    "response",
    "options",
    "answer options",
    "response options",
    "guidance",
    "notes",
    "evidence guidance",
    "acceptable responses",
}


def _validate_cell_security(val: Any) -> None:
    """Validate cell contents for formula injection, prohibited HTML markup, and encoding issues."""
    if val is None:
        return
    text = str(val)
    if "\x00" in text or any(0xD800 <= ord(c) <= 0xDFFF for c in text):
        raise ValueError("Cell contains prohibited null byte or invalid character encoding")
    stripped = text.strip()
    if not stripped:
        return
    # Formula injection rejection: (=, +, -, @)
    if stripped.startswith(("=", "@")):
        raise ValueError(f"Cell contains prohibited formula expression: {stripped[:30]!r}")
    if stripped.startswith(("+", "-")):
        rest = stripped[1:].strip()
        try:
            float(stripped)
            is_number = True
        except ValueError:
            is_number = False
        if not is_number or any(c in rest for c in "()|'\"="):
            raise ValueError(f"Cell contains prohibited formula injection: {stripped[:30]!r}")
    # Prohibited HTML markup rejection
    if re.search(r"<\s*/*\s*[a-zA-Z][^>]*>", text):
        raise ValueError(f"Cell contains prohibited HTML markup: {text[:30]!r}")


def _validate_worksheet_dimensions(workbook) -> None:
    # The workbook contains wide presentation/template sheets (for example
    # DeepDive). Import logic iterates only the five structured source sheets,
    # so dimension limits apply to that actual trust boundary.
    for sheet_name in EXPECTED_SHEETS.intersection(workbook.sheetnames):
        worksheet = workbook[sheet_name]
        if (
            worksheet.max_row > MAX_WORKSHEET_ROWS
            or worksheet.max_column > MAX_WORKSHEET_COLUMNS
        ):
            raise ValueError(
                f"Worksheet {worksheet.title!r} exceeds the supported dimensions"
            )


def _split_list(value: Any) -> List[str]:
    if value is None:
        return []
    values = re.split(r"[,;]", str(value))
    seen: set[str] = set()
    output: List[str] = []
    for value_part in values:
        cleaned = value_part.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return output


def _normalise_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\u0000", "").split())


def _stable_question_id(question_type: str, text: str) -> str:
    normalised = (
        f"aiaf-questionnaire-v1|{question_type}|{_normalise_text(text).lower()}"
    )
    prefix = "CORE" if question_type == "core" else "BENEFIT"
    return f"AIAF-{prefix}-{hashlib.sha256(normalised.encode('utf-8')).hexdigest()[:12].upper()}"


def _formula_text(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    text = getattr(value, "text", None)
    if text is not None:
        return text
    return str(value)


def _count_ids(ws, column: int, start_row: int = 2) -> int:
    return sum(
        bool(_normalise_text(ws.cell(row, column).value))
        for row in range(start_row, ws.max_row + 1)
    )


def _header_fingerprint(workbook) -> str:
    """Fingerprint source-table headers without depending on formatted UI ranges."""

    source_ranges = {
        "Questions": 17,
        "Triggers": 17,
        "ALL Focus Questions": 72,
        "Risks": 4,
        "Treatments": 6,
    }
    lines: List[str] = []
    for sheet_name, width in source_ranges.items():
        ws = workbook[sheet_name]
        # Triggers has two header rows; the other source tables have one.
        header_rows = 2 if sheet_name == "Triggers" else 1
        for row in range(1, header_rows + 1):
            values = [
                _normalise_text(ws.cell(row, column).value)
                for column in range(1, width + 1)
            ]
            lines.append(f"{sheet_name}!{row}|" + "|".join(values))
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _workbook_sheet_parts(archive: zipfile.ZipFile) -> Dict[str, str]:
    ns_main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{{{ns_pkg}}}Relationship")
    }
    output: Dict[str, str] = {}
    sheets = workbook.find(f"{{{ns_main}}}sheets")
    if sheets is None:
        return output
    for sheet in sheets:
        relationship_id = sheet.attrib.get(f"{{{ns_rel}}}id")
        target = targets.get(relationship_id or "")
        if not target:
            continue
        normalised = str(PurePosixPath("xl") / target).replace("xl/xl/", "xl/")
        output[sheet.attrib.get("name", "")] = normalised
    return output


def _extract_x14_validations(raw: bytes) -> Dict[str, List[Dict[str, str]]]:
    """Extract extended validation rules without modifying the workbook."""

    output: Dict[str, List[Dict[str, str]]] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            parts = _workbook_sheet_parts(archive)
            for sheet_name, part in parts.items():
                if part not in archive.namelist():
                    continue
                root = ET.fromstring(archive.read(part))
                records: List[Dict[str, str]] = []
                for node in root.iter():
                    if not node.tag.endswith("dataValidation"):
                        continue
                    sqref = node.attrib.get("sqref") or ""
                    if not sqref:
                        # x14 validations store their target in a child
                        # ``xm:sqref`` element, unlike classic validations
                        # where ``sqref`` is an attribute.
                        sqref = next(
                            (
                                "".join(child.itertext()).strip()
                                for child in node.iter()
                                if child is not node and child.tag.endswith("sqref")
                            ),
                            "",
                        )
                    formulas = [
                        "".join(child.itertext()).strip()
                        for child in node
                        if child.tag.endswith("formula1")
                        or child.tag.endswith("formula2")
                    ]
                    if sqref or formulas:
                        records.append(
                            {
                                "sqref": sqref,
                                "type": node.attrib.get("type", ""),
                                "formula1": formulas[0] if formulas else "",
                                "formula2": formulas[1] if len(formulas) > 1 else "",
                            }
                        )
                if records:
                    output[sheet_name] = records
    except (KeyError, zipfile.BadZipFile, ET.ParseError):
        return {}
    return output


_QUESTION_LIST_FORMULA = re.compile(
    r"^(?:'Questions'|Questions)!\$?B\$?(\d+):\$?B\$?(\d+)$",
    re.IGNORECASE,
)


def _sqref_intersects_assessment_core(sqref: str) -> bool:
    """Return whether a validation target touches ``Assessment!E3:E18``."""

    for token in str(sqref or "").split():
        try:
            min_col, min_row, max_col, max_row = range_boundaries(
                token.replace("$", "")
            )
        except ValueError:
            continue
        if min_col <= 5 <= max_col and min_row <= 18 and max_row >= 3:
            return True
    return False


def _assessment_core_validations(
    validations: Dict[str, List[Dict[str, str]]],
) -> List[Dict[str, Any]]:
    """Resolve Assessment dropdown rules to their Questions source rows."""

    resolved: List[Dict[str, Any]] = []
    for record in validations.get("Assessment", []):
        if str(record.get("type") or "").lower() != "list":
            continue
        if not _sqref_intersects_assessment_core(record.get("sqref", "")):
            continue
        formula = str(record.get("formula1") or "").strip().lstrip("=")
        match = _QUESTION_LIST_FORMULA.fullmatch(formula)
        if not match:
            continue
        start_row, end_row = (int(match.group(1)), int(match.group(2)))
        if start_row > end_row:
            start_row, end_row = end_row, start_row
        resolved.append(
            {
                **record,
                "source_sheet": "Questions",
                "source_column": "B",
                "source_start_row": start_row,
                "source_end_row": end_row,
            }
        )

    def target_row(item: Dict[str, Any]) -> int:
        for token in str(item.get("sqref") or "").split():
            try:
                _, min_row, _, _ = range_boundaries(token.replace("$", ""))
                return min_row
            except ValueError:
                continue
        return 10**9

    return sorted(resolved, key=target_row)


def _is_benefit_group(group: Dict[str, Any]) -> bool:
    tags = [str(tag).strip() for tag in group.get("tags", [])]
    return any(
        tag.upper().startswith("BEN_") or tag.lower().startswith("benefit:")
        for tag in tags
    )


def _question_groups(questions_ws, cached_questions_ws) -> List[Dict[str, Any]]:
    """Discover consecutive question/answer groups without fixed row numbers."""

    groups: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for row in range(2, questions_ws.max_row + 1):
        text = _normalise_text(questions_ws.cell(row, 1).value)
        answer = _normalise_text(questions_ws.cell(row, 2).value)
        if not text or not answer:
            current = None
            continue
        if current is None or current["text"] != text or row != current["last_row"] + 1:
            current = {
                "text": text,
                "answers": [],
                "tags": [],
                "options": [],
                "first_row": row,
                "last_row": row,
            }
            groups.append(current)
        current["last_row"] = row
        if answer not in current["answers"]:
            current["answers"].append(answer)
        tag = _normalise_text(questions_ws.cell(row, 5).value)
        if tag and tag not in current["tags"]:
            current["tags"].append(tag)
        current["options"].append(
            {
                "source_row": row,
                "response": answer,
                "cached_response": _normalise_text(
                    cached_questions_ws.cell(row, 2).value
                ),
                "tag": tag,
                "response_number": _normalise_text(questions_ws.cell(row, 17).value),
            }
        )
    return groups


def _import_legacy_aiaf_internal(
    formula_wb, cached_wb, raw: bytes, filename: str, caught: list
) -> QuestionBank:
    digest = hashlib.sha256(raw).hexdigest()
    try:
        _validate_worksheet_dimensions(formula_wb)
    except ValueError:
        formula_wb.close()
        cached_wb.close()
        raise

    missing = sorted(EXPECTED_SHEETS - set(formula_wb.sheetnames))
    if missing:
        formula_wb.close()
        cached_wb.close()
        raise ValueError(f"Workbook is missing required AIAF source sheets: {missing}")

    validations = _extract_x14_validations(raw)
    core_validations = _assessment_core_validations(validations)
    import_warnings: List[str] = []

    source_version = _normalise_text(cached_wb["Questions"]["P2"].value)
    if not source_version:
        source_version = (
            _normalise_text(_formula_text(formula_wb["Questions"]["P2"].value))
            or "unversioned"
        )

    question_records: List[QuestionRecord] = []
    questions_ws = formula_wb["Questions"]
    grouped = _question_groups(questions_ws, cached_wb["Questions"])
    if core_validations:
        group_ranges = {(group["first_row"], group["last_row"]) for group in grouped}
        for validation in core_validations:
            source_range = (
                validation["source_start_row"],
                validation["source_end_row"],
            )
            if source_range not in group_ranges:
                import_warnings.append(
                    "Assessment validation "
                    f"{validation['sqref']} references Questions!B{source_range[0]}:B{source_range[1]}, "
                    "which does not exactly match one consecutive question group."
                )

    seen_question_ids: set[str] = set()
    for group in grouped:
        text = group["text"]
        _validate_cell_security(text)
        group_rows = set(range(group["first_row"], group["last_row"] + 1))
        matching_validations = [
            item
            for item in core_validations
            if group_rows
            & set(range(item["source_start_row"], item["source_end_row"] + 1))
        ]
        if matching_validations:
            question_type = "core"
        elif _is_benefit_group(group):
            question_type = "benefit"
        else:
            # Preserve an unreferenced non-benefit group rather than silently
            # dropping it.  A routing warning makes the drift reviewable.
            question_type = "core"
            if core_validations:
                import_warnings.append(
                    f"Core question group Questions!A{group['first_row']}:B{group['last_row']} "
                    "is not referenced by an Assessment!E3:E18 list validation."
                )
        question_id = _stable_question_id(question_type, text)
        if question_id in seen_question_ids:
            formula_wb.close()
            cached_wb.close()
            raise ValueError(
                f"Duplicate generated {question_type} question ID {question_id!r}; "
                "separated question groups must have distinct source text."
            )
        seen_question_ids.add(question_id)
        seen_option_ids: set[str] = set()
        response_options: List[Dict[str, Any]] = []
        for option in group["options"]:
            candidate = option["tag"]
            if not candidate or candidate in seen_option_ids:
                option_hash = (
                    hashlib.sha256(
                        f"{question_id}|{option['response']}".lower().encode("utf-8")
                    )
                    .hexdigest()[:10]
                    .upper()
                )
                candidate = f"{question_id}-OPT-{option_hash}"
            seen_option_ids.add(candidate)
            response_options.append({"option_id": candidate, **option})
        question_records.append(
            QuestionRecord(
                question_id=question_id,
                question_text=text,
                response_tags=group["tags"],
                answer_options=group["answers"],
                source_version=source_version,
                source_sheet="Questions",
                question_type=question_type,
                source_location=f"Questions!A{group['first_row']}:Q{group['last_row']}",
                routing_logic={"response_options": response_options},
                provenance={
                    "source_namespace": "AIAF_QUESTIONNAIRE_V1",
                    "sheet_visibility": questions_ws.sheet_state,
                    "assessment_validations": matching_validations,
                },
            )
        )

    focus_ws = formula_wb["ALL Focus Questions"]
    seen_focus_ids: set[str] = set()
    cached_focus_ws = cached_wb["ALL Focus Questions"]
    for row in range(2, focus_ws.max_row + 1):
        question_id = _normalise_text(focus_ws.cell(row, 1).value)
        text = _normalise_text(focus_ws.cell(row, 4).value)
        if not question_id or not text:
            continue
        _validate_cell_security(question_id)
        _validate_cell_security(text)
        if question_id in seen_focus_ids:
            formula_wb.close()
            cached_wb.close()
            raise ValueError(
                f"Duplicate Focus Question ID {question_id!r} at row {row}"
            )
        seen_focus_ids.add(question_id)
        default_answer = _normalise_text(focus_ws.cell(row, 5).value)
        question_records.append(
            QuestionRecord(
                question_id=question_id,
                question_text=text,
                risk_domain=_normalise_text(focus_ws.cell(row, 3).value) or None,
                risk_factor_ids=_split_list(focus_ws.cell(row, 8).value),
                treatment_ids=_split_list(focus_ws.cell(row, 9).value),
                response_tags=_split_list(focus_ws.cell(row, 2).value),
                phase_tags=_split_list(focus_ws.cell(row, 6).value),
                sme_tags=_split_list(focus_ws.cell(row, 7).value),
                answer_options=[default_answer] if default_answer else [],
                source_version=source_version,
                source_sheet="ALL Focus Questions",
                question_type="focus",
                source_location=f"ALL Focus Questions!A{row}:I{row}",
                routing_logic={
                    "raw_response_tags": _normalise_text(focus_ws.cell(row, 2).value),
                    "raw_phase_tags": _normalise_text(focus_ws.cell(row, 6).value),
                    "has_all_keys": _split_list(focus_ws.cell(row, 2).value),
                    "has_any_phase_tag": _split_list(focus_ws.cell(row, 6).value),
                },
                provenance={
                    "source_namespace": "AIAF_QUESTIONNAIRE_V1",
                    "sheet_visibility": focus_ws.sheet_state,
                    "formula_cells": {
                        "calculated": _formula_text(focus_ws.cell(row, 10).value),
                        "check": _formula_text(focus_ws.cell(row, 12).value),
                        "focus_area": _formula_text(focus_ws.cell(row, 13).value),
                    },
                    "cached_cells": {
                        "calculated": cached_focus_ws.cell(row, 10).value,
                        "check": cached_focus_ws.cell(row, 12).value,
                        "focus_area": cached_focus_ws.cell(row, 13).value,
                    },
                },
            )
        )

    trigger_ws = formula_wb["Triggers"]
    triggers: List[Dict[str, Any]] = []
    for row in range(3, trigger_ws.max_row + 1):
        requirement = _normalise_text(trigger_ws.cell(row, 6).value)
        risk = _normalise_text(trigger_ws.cell(row, 5).value)
        if not requirement and not risk:
            continue
        _validate_cell_security(requirement)
        _validate_cell_security(risk)
        triggers.append(
            {
                "rule_id": f"AIAF-TRIGGER-{row - 2:03d}",
                "dont_match": _split_list(trigger_ws.cell(row, 2).value),
                "match_all": _split_list(trigger_ws.cell(row, 3).value),
                "match_any": _split_list(trigger_ws.cell(row, 4).value),
                "risk": risk,
                "requirement": requirement,
                "icon": _normalise_text(trigger_ws.cell(row, 7).value),
                "flag_as": _normalise_text(trigger_ws.cell(row, 8).value),
                "special_tag": _normalise_text(
                    _formula_text(trigger_ws.cell(row, 11).value)
                ),
                "audit_record": _normalise_text(trigger_ws.cell(row, 12).value),
                "reason": _normalise_text(trigger_ws.cell(row, 13).value),
            }
        )

    warning_messages = [str(item.message) for item in caught]
    warning_messages.extend(import_warnings)
    if validations:
        warning_messages.append(
            f"Preserved {sum(len(items) for items in validations.values())} extended x14 data-validation rules from raw XLSX XML."
        )
    else:
        warning_messages.append(
            "No extended x14 data-validation rules were found in the XLSX package."
        )

    focus_count = sum(
        item.source_sheet == "ALL Focus Questions" for item in question_records
    )
    core_count = sum(item.question_type == "core" for item in question_records)
    benefit_count = sum(item.question_type == "benefit" for item in question_records)
    expected_counts = {
        "focus": 446,
        "triggers": 51,
        "treatments": 121,
        "risks": 109,
        "core": 16,
        "benefit": 16,
    }
    observed_counts = {
        "focus": focus_count,
        "triggers": len(triggers),
        "treatments": _count_ids(formula_wb["Treatments"], 1),
        "risks": _count_ids(formula_wb["Risks"], 1),
        "core": core_count,
        "benefit": benefit_count,
    }
    for key, expected in expected_counts.items():
        if observed_counts[key] != expected:
            warning_messages.append(
                f"Version drift: observed {observed_counts[key]} {key} records; reference catalogue had {expected}."
            )

    metadata = QuestionnaireMetadata(
        questionnaire_id=f"AIAF-{digest[:12]}",
        source_filename=filename,
        source_sha256=digest,
        source_version=source_version,
        header_fingerprint=_header_fingerprint(formula_wb),
        sheets={ws.title: ws.sheet_state for ws in formula_wb.worksheets},
        core_question_count=core_count,
        benefit_question_count=benefit_count,
        focus_question_count=focus_count,
        trigger_count=len(triggers),
        treatment_count=observed_counts["treatments"],
        risk_count=observed_counts["risks"],
        warnings=list(dict.fromkeys(warning_messages)),
    )
    formula_wb.close()
    cached_wb.close()
    return QuestionBank(
        metadata=metadata,
        questions=question_records,
        triggers=triggers,
        routing_metadata={
            "extended_data_validations": validations,
            "core_question_validations": core_validations,
            "focus_selection": "all response_tags AND any phase_tags",
            "assessment_core_dropdowns": "Assessment!E3:E18",
            "source_workbook_never_saved": True,
        },
    )


def import_questionnaire_workbook(
    raw: bytes,
    filename: str = "questionnaire.xlsx",
    sheet_names: Optional[List[str]] = None,
    column_mapping: Optional[Dict[str, str]] = None,
) -> QuestionBank:
    """Import an arbitrary enterprise AI governance questionnaire from an XLSX workbook.

    Dynamically detects Question Text, Question ID, and Category columns across all
    sheets (or user-specified sheets). Enforces strict archive safety limits, streaming XML
    validation, formula injection rejection, and HTML stripping.
    """
    _validate_workbook_archive(raw)
    digest = hashlib.sha256(raw).hexdigest()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        formula_wb = load_workbook(
            io.BytesIO(raw), data_only=False, read_only=False, keep_links=False
        )
        cached_wb = load_workbook(
            io.BytesIO(raw), data_only=True, read_only=False, keep_links=False
        )

    # Legacy AIAF layout dispatch if caller did not request specific sheets or column mapping
    if (
        EXPECTED_SHEETS.issubset(formula_wb.sheetnames)
        and not sheet_names
        and not column_mapping
    ):
        return _import_legacy_aiaf_internal(
            formula_wb, cached_wb, raw, filename, caught
        )

    try:
        # Validate dimensions across all worksheets
        for ws in formula_wb.worksheets:
            if (
                ws.max_row > MAX_WORKSHEET_ROWS
                or ws.max_column > MAX_WORKSHEET_COLUMNS
            ):
                raise ValueError(
                    f"Worksheet {ws.title!r} exceeds the supported dimensions"
                )

        # Determine target sheets
        if sheet_names:
            missing_sheets = [
                s for s in sheet_names if s not in formula_wb.sheetnames
            ]
            if missing_sheets:
                raise ValueError(
                    f"Specified sheet(s) not found in workbook: {missing_sheets}"
                )
            target_sheets = [formula_wb[name] for name in sheet_names]
        else:
            target_sheets = list(formula_wb.worksheets)

        question_records: List[QuestionRecord] = []
        seen_question_ids: set[str] = set()
        import_warnings: List[str] = [str(item.message) for item in caught]

        for ws in target_sheets:
            if ws.max_row < 2:
                if sheet_names and ws.title in sheet_names:
                    raise ValueError(f"Worksheet {ws.title!r} contains no data rows")
                continue

            # Header row analysis (check row 1, then row 2)
            header_row = 1
            col_q_idx: Optional[int] = None
            col_id_idx: Optional[int] = None
            col_domain_idx: Optional[int] = None
            col_answer_idx: Optional[int] = None

            # Check caller-provided column mapping first
            if column_mapping:
                for col in range(1, ws.max_column + 1):
                    val = _normalise_text(ws.cell(header_row, col).value).lower()
                    if column_mapping.get("question_text", "").lower() in (
                        val,
                        str(col),
                    ):
                        col_q_idx = col
                    if column_mapping.get("question_id", "").lower() in (
                        val,
                        str(col),
                    ):
                        col_id_idx = col
                    if column_mapping.get("domain", "").lower() in (val, str(col)):
                        col_domain_idx = col

            # Automatic header discovery if not resolved by mapping
            if col_q_idx is None:
                for candidate_row in (1, 2):
                    if candidate_row > ws.max_row:
                        break
                    for col in range(1, ws.max_column + 1):
                        cell_val = _normalise_text(
                            ws.cell(candidate_row, col).value
                        ).lower()
                        if not cell_val:
                            continue
                        clean_hdr = re.sub(r"[^a-z0-9]+", " ", cell_val).strip()
                        if col_id_idx is None and (
                            clean_hdr in QUESTION_ID_HEADER_NAMES
                            or clean_hdr.endswith(" id")
                            or clean_hdr.startswith("id ")
                            or clean_hdr.endswith(" no")
                            or clean_hdr == "ref"
                        ):
                            col_id_idx = col
                        elif col_q_idx is None and (
                            clean_hdr in QUESTION_TEXT_HEADER_NAMES
                            or "question" in clean_hdr
                            or "requirement" in clean_hdr
                        ):
                            col_q_idx = col
                            header_row = candidate_row
                        elif (
                            col_domain_idx is None
                            and clean_hdr in DOMAIN_HEADER_NAMES
                        ):
                            col_domain_idx = col
                        elif (
                            col_answer_idx is None
                            and clean_hdr in ANSWER_HEADER_NAMES
                        ):
                            col_answer_idx = col
                    if col_q_idx is not None:
                        break

            # Fallback to text-dense column if no header matched
            if col_q_idx is None:
                best_col = None
                best_score = 0
                sample_end = min(ws.max_row, header_row + 20)
                for col in range(1, ws.max_column + 1):
                    str_lengths = []
                    for r in range(header_row + 1, sample_end + 1):
                        v = ws.cell(r, col).value
                        if isinstance(v, str) and len(v.strip()) > 0:
                            str_lengths.append(len(v.strip()))
                    if str_lengths:
                        avg_len = sum(str_lengths) / len(str_lengths)
                        if avg_len >= 12 and len(str_lengths) > best_score:
                            best_score = len(str_lengths)
                            best_col = col
                if best_col is not None:
                    col_q_idx = best_col
                    import_warnings.append(
                        f"Worksheet {ws.title!r}: dynamically fell back to text-dense Column {col_q_idx} for question text."
                    )

            if col_q_idx is None:
                if sheet_names and ws.title in sheet_names:
                    raise ValueError(
                        f"Worksheet {ws.title!r} contains no identifiable question text column"
                    )
                continue

            # Ingest rows
            sheet_slug = (
                re.sub(r"[^A-Za-z0-9]+", "-", ws.title).strip("-").upper()
                or "SHEET"
            )
            for row in range(header_row + 1, ws.max_row + 1):
                raw_cell = ws.cell(row, col_q_idx).value
                _validate_cell_security(raw_cell)
                q_text = _normalise_text(raw_cell)
                if not q_text:
                    continue

                if col_id_idx is not None:
                    raw_id_cell = ws.cell(row, col_id_idx).value
                    _validate_cell_security(raw_id_cell)
                    qid = _normalise_text(raw_id_cell)
                else:
                    qid = ""

                if not qid:
                    # Content-addressable stable question ID
                    content_hash = hashlib.sha256(
                        f"{ws.title}|{row}|{q_text}".encode("utf-8")
                    ).hexdigest()[:8].upper()
                    qid = f"{sheet_slug}-Q{row:03d}-{content_hash}"

                # Disambiguate duplicate IDs
                if qid in seen_question_ids:
                    extra_hash = hashlib.sha256(
                        f"{row}|{q_text}".encode("utf-8")
                    ).hexdigest()[:4].upper()
                    qid = f"{qid}-{extra_hash}"
                seen_question_ids.add(qid)

                domain = None
                if col_domain_idx is not None:
                    raw_domain = ws.cell(row, col_domain_idx).value
                    _validate_cell_security(raw_domain)
                    domain = _normalise_text(raw_domain) or None

                answers = []
                if col_answer_idx is not None:
                    raw_answer = ws.cell(row, col_answer_idx).value
                    _validate_cell_security(raw_answer)
                    ans = _normalise_text(raw_answer)
                    if ans:
                        answers.append(ans)

                question_records.append(
                    QuestionRecord(
                        question_id=qid,
                        question_text=q_text,
                        risk_domain=domain,
                        answer_options=answers,
                        source_version="1.0.0",
                        source_sheet=ws.title,
                        question_type="question",
                        source_location=f"{ws.title}!R{row}C{col_q_idx}",
                        routing_logic={},
                        provenance={
                            "source_namespace": "GENERAL_QUESTIONNAIRE_V1",
                            "sheet_title": ws.title,
                            "row_index": row,
                        },
                    )
                )

        if not question_records:
            raise ValueError(
                "Workbook contains no identifiable question columns or question rows"
            )

        source_version = "1.0.0"
        fingerprint_content = f"{filename}|{len(question_records)}|{digest}"
        metadata = QuestionnaireMetadata(
            questionnaire_id=f"QBANK-{digest[:12]}",
            source_filename=filename,
            source_sha256=digest,
            source_version=source_version,
            header_fingerprint=hashlib.sha256(
                fingerprint_content.encode("utf-8")
            ).hexdigest(),
            sheets={ws.title: ws.sheet_state for ws in formula_wb.worksheets},
            core_question_count=len(question_records),
            benefit_question_count=0,
            focus_question_count=0,
            trigger_count=0,
            treatment_count=0,
            risk_count=0,
            warnings=list(dict.fromkeys(import_warnings)),
        )

        return QuestionBank(
            metadata=metadata,
            questions=question_records,
            triggers=[],
            routing_metadata={
                "selection_mode": "full_questionnaire",
                "source_workbook_never_saved": True,
                "question_count": len(question_records),
            },
        )
    finally:
        formula_wb.close()
        cached_wb.close()


def import_aiaf_workbook(raw: bytes, filename: str = "aiaf.xlsx") -> QuestionBank:
    """Deprecated alias for importing questionnaires.

    Retained for backward compatibility. Emits a DeprecationWarning.
    """
    warnings.warn(
        "import_aiaf_workbook is deprecated and will be removed in a future release. "
        "Use import_questionnaire_workbook instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return import_questionnaire_workbook(raw, filename=filename)
