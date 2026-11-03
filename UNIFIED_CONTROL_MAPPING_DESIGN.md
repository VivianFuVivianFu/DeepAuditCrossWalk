# Unified Crosswalk Control Mapping Design

**Product**: DeepAuditCrossWalk  
**Domain**: Crosswalk Semantic Mapping Engine & Unified Control Hierarchy  
**Date**: November 2026  
**Status**: Formal Specification  

---

## 1. The Core Mapping Model

The Crosswalk architecture uses the **33 Unified Controls** (`UNIFIED_CONTROL_LIBRARY.json`) as a single authoritative pivot point between disparate external laws, proprietary enterprise standards, and questionnaire test items:

```
┌─────────────────────────────────┐                 ┌─────────────────────────────────┐
│  EXTERNAL REGULATORY OBLIGATION │                 │   ENTERPRISE POLICY CLAUSE      │
│  (e.g., APRA CPS 230 Para 42)   │                 │   (e.g., Board AI Risk Standard)│
└────────────────┬────────────────┘                 └────────────────┬────────────────┘
                 │                                                   │
                 │ Maps to                                           │ Maps to
                 ▼                                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          UNIFIED CONTROL (CTRL-*)                                   │
│            (e.g., CTRL-OPS-OUTSOURCING: Third-Party & Critical Service Provider)    │
│            Control Facets: [due_diligence, contingency_plan, exit_strategy]         │
└──────────────────────────────────────────┬──────────────────────────────────────────┘
                                           │
                                           │ Maps to
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    ENTERPRISE QUESTIONNAIRE TEST ITEM                               │
│                    (e.g., Question Q28: "Does the vendor maintain APRA-compliant    │
│                     tested exit plans and disaster recovery SLAs?")                 │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

This tri-partite architecture eliminates the exponential complexity of $N \times M$ direct mappings between hundreds of external regulations and thousands of internal questions.

---

## 2. Six-Tier Relationship Classification

To prevent false confidence caused by simple keyword similarity, every crosswalk relationship must be explicitly classified into one of six canonical relationship types:

| Relationship Type | Semantic Definition | System Treatment & Scoring |
|---|---|---|
| **Full Coverage** (`full`) | The policy requirement or questionnaire question completely satisfies all mandatory facets of the control without gaps or caveats. | Counted as **100% Covered** in automated scorecard. No gap generated. |
| **Partial Coverage** (`partial`) | The requirement or question tests some control facets, but omits critical operational details (e.g., tests existence of policy, but omits testing enforcement or threshold). | Counted as **Partial**. Generates a remediable `GAP_QUESTIONNAIRE` or `GAP_POLICY` highlighting missing facets. |
| **Related but Insufficient** (`related`) | Addresses the same conceptual topic (e.g., data security), but lacks legal, operational, or technical specificity to satisfy the obligation. | Flagged as **Insufficient**. Reviewer prompted to provide specific addendum. |
| **Not Equivalent** (`not_equivalent`) | Shared vocabulary exists (e.g., "model audit" vs "financial audit"), but substantive obligations are completely distinct. | Explicitly excluded. Prevents false positive matching. |
| **Missing Coverage** (`missing`) | No clause or question exists that addresses any facet of the Unified Control. | Scored as **0% Covered**. Triggers high-priority gap alert. |
| **Undetermined / Requires Review** (`undetermined`) | Algorithmic scoring identifies candidate lexical or semantic overlap, but confidence is below strict threshold. | Staged in review queue. Must be reviewed by Human SME before entering assessment baseline. |

---

## 3. Mandatory Mapping Metadata Schema

No relationship may exist as a bare tuple `(A, B)`. Every mapping record must preserve full provenance and auditability:

```python
class UnifiedCrosswalkMapping(BaseModel):
    mapping_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str  # Isolated per tenant for enterprise mappings; "global" for shared
    
    # Left side: Source Entity
    source_type: Literal["regulatory_obligation", "enterprise_clause", "unified_control"]
    source_id: str  # e.g., "AU-APRA-CPS230-042" or "POL-AI-01-CLAUSE-04"
    source_version: str
    original_clause_reference: str  # e.g., "Section 4.2(b)"
    
    # Right side: Target Entity
    target_type: Literal["unified_control", "questionnaire_item"]
    target_id: str  # e.g., "CTRL-OPS-OUTSOURCING" or "Q28"
    
    # Semantic facets
    relevant_control_facets: List[str]  # e.g., ["due_diligence", "exit_strategy"]
    relationship: Literal[
        "full",
        "partial",
        "related",
        "not_equivalent",
        "missing",
        "undetermined"
    ]
    
    # Qualitative rationale
    mapping_rationale: str
    applicability_conditions: List[str] = Field(default_factory=list)
    
    # Governance & Review
    review_status: Literal["proposed", "confirmed", "rejected"] = "proposed"
    reviewed_by: Optional[str] = None
    reviewer_role: Optional[Literal["legal", "compliance", "cyber", "data_sme"]] = None
    reviewed_at: Optional[datetime] = None
    reviewer_decision_notes: Optional[str] = None
    
    # Evidence verification
    supporting_evidence_references: List[str] = Field(default_factory=list)
```

---

## 4. Multi-Tenant Independence & Non-Interference Guarantees

1. **Global Immutable Baseline**:
   - The 33 Unified Controls in `UNIFIED_CONTROL_LIBRARY.json` and the 57 foundational mappings in `OBLIGATION_CONTROL_MAPPINGS.json` are seeded globally with `tenant_id = "global"`.
   - Read-only across all tenants.
2. **Tenant-Specific Overrides & Extensions**:
   - When Tenant A reviews and approves a mapping between an enterprise policy clause and a Unified Control, the record is stored in `clause_control_mappings` with `tenant_id = "tenant-a"`.
   - Under no circumstances is Tenant A's mapping queryable by, merged with, or visible to Tenant B.
3. **Many-to-Many Disambiguation**:
   - A single enterprise policy clause (e.g., *"All customer-facing AI agents must have prompt filtering and log transactions in Sydney data centers"*) may map to multiple Unified Controls:
     - `CTRL-SEC-GUARDRAILS` (Relationship: Full)
     - `CTRL-PRIV-CROSS-BORDER` (Relationship: Full)
     - `CTRL-OPS-LOGGING` (Relationship: Partial)
   - The mapping engine evaluates each facet link independently, ensuring granular and accurate gap tracking.

