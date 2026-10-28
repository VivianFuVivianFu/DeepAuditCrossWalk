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
from typing import Any, Dict, List

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


def import_aiaf_workbook(raw: bytes, filename: str = "aiaf.xlsx") -> QuestionBank:
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
