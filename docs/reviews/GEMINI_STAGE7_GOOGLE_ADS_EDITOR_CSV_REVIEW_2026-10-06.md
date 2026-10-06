# Stage 7 Review Dossier: Consented Client Pilot Inspection & Google Ads Editor CSV Schema Repair

**Date:** 2026-10-06  
**Author:** Gemini CLI (Principal Architect & Reviewer)  
**Task ID:** `STAGE7-GOOGLE-ADS-EDITOR-CSV-REPAIR-2026-10-06`  
**Reference Directive:** [`docs/HARNESS_COMPLETION_DIRECTIVE_2026-10-05.md`](../HARNESS_COMPLETION_DIRECTIVE_2026-10-05.md)  
**Security & Containment:** ESTOP strictly engaged (`ESTOP = True`), model-free execution, zero network/live API calls, zero production workspace mutations.

---

## 1. Executive Summary

This dossier records the Stage 7 offline schema inspection and empirical remediation of Google Ads Editor bulk CSV exports, specifically validating the consented client package (`el-shaddai-coffee-katowice`).

Two critical defects in `orchestrator/campaign_builder.py` were discovered, remediated, and verified model-free:
1. **Header Row Precedence & Column Count Uniformity:** The unverified/draft campaign disclaimer row was previously placed on line 1 before the column headers, and only contained 21 columns instead of the required 25 columns. Google Ads Editor treats line 1 as the column header row, causing column mapping failures and ragged CSV parse errors.
2. **Mid-Word Slicing in Ad Copy:** Default headlines and descriptions used raw character slicing (`[:30]` and `[:90]`). For client display names with 24 characters (such as `"El Shaddai Indian Coffee"`), Polish ad copy was sliced mid-syllable, producing broken words (`"Onlin"`, `"int"`, `"profesjo"`, `"ora"`).

Both defects have been remediated in `orchestrator/campaign_builder.py`, verified with dedicated regression tests in `tests/test_campaign_builder_regression.py` (15/15 PASS), verified via model-free client package compilation in a disposable tempdir, and validated across the full test gate (**108/108 suites green, exit 0**).

All 299 monitored production artifacts in `workspace/clients/` remain strictly untouched and 100% hash-identical.

---

## 2. Deep Programmatic Inspection of Baseline Client Artifact

Programmatic inspection of `workspace/clients/el-shaddai-coffee-katowice/google_ads_editor_import.csv` identified:

| Row # | Content | Column Count | Issue |
| :--- | :--- | :--- | :--- |
| **Row 1** | `# SAMPLE CAMPAIGN - NOT VERIFIED FOR CLIENT USE,,,,,,,,,,,,,,,,,,,,` | 21 | Uneven column count (21 vs 25); precedes header row, breaking Google Ads Editor automatic column mapping |
| **Row 2** | `Campaign,Ad Group,Keyword,Criterion Type,Headline 1,...,Status` | 25 | Authoritative headers pushed to second line |
| **Rows 5, 8, 11, 14** (H13) | `El Shaddai Indian Coffee Onlin` | 25 | Mid-word slice: "Online" truncated to "Onlin" at character 30 |
| **Rows 5, 8, 11, 14** (D1) | `...na naszej oficjalnej stronie int` | 25 | Mid-word slice: "internetowej." truncated to "int" at character 90 |
| **Rows 5, 8, 11, 14** (D2) | `...szeroki asortyment i profesjo` | 25 | Mid-word slice: "profesjonalne podejscie." truncated to "profesjo" at character 90 |
| **Rows 5, 8, 11, 14** (D4) | `...katalog produktow ora` | 25 | Mid-word slice: "oraz kontakt." truncated to "ora" at character 90 |

---

## 3. Architectural Remediations in `campaign_builder.py`

### 3.1 Authoritative Row 1 Headers & Uniform 25-Column Layout
- In `export_google_ads_editor_csv()`, `writer.writerow(headers)` is now written **first** on line 1.
- When `not is_verified`, the sample warning disclaimer is written on line 2 with exactly `len(headers)` columns:
  ```python
  writer.writerow([
      "# SAMPLE CAMPAIGN - NOT VERIFIED FOR CLIENT USE",
  ] + [""] * (len(headers) - 1))
  ```
- Result: Every row across both sample and verified modes has exactly 25 columns. Any CSV parser calling `next(reader)` obtains valid, recognized Google Ads Editor headers.

### 3.2 Word-Boundary Truncation Helper
- Authored `truncate_to_word_boundary(text: str, max_length: int, ensure_punctuation: bool = False) -> str`:
  - When text exceeds `max_length`, splits at whitespace boundary without cutting words.
  - Strips dangling conjunctions and prepositions (`i`, `a`, `o`, `w`, `z`, `and`, `or`, `of`, etc.).
  - When `ensure_punctuation=True` (for descriptions), verifies terminal punctuation (`.`, `!`, `?`) and appends a period within the character limit.

### 3.3 Concise, Natural Polish & English Templates
- Default headlines and descriptions were reformulated to fit naturally within character limits:
  - **H13 (PL):** `f"{display_name} Online"` if `<= 30` chars, else `"Sprawdz Oferte Online"`.
  - **H14 (EN):** `f"{display_name} Online"` if `<= 30` chars, else `"Shop Online Today"`.
  - **D1 (PL):** `f"Poznaj oferte {display_name}. Sprawdz szczegoly na naszej oficjalnej stronie."` (87 chars for 24-char name).
  - **D2 (PL):** `f"Skontaktuj sie z {display_name}. Zapewniamy bogaty wybor i fachowe doradztwo."` (87 chars for 24-char name).
  - **D3 (PL):** `"Szukasz sprawdzonych rozwiazan? Dowiedz sie wiecej o ofercie dopasowanej do potrzeb."` (84 chars).
  - **D4 (PL):** `f"Odwiedz strone {display_name} i sprawdz nasz aktualny katalog produktow."` (82 chars for 24-char name).
- Deduplication: `deduplicate_preserve_order()` ensures all 15 headlines and 4 descriptions in RSA ads are strictly unique.
- Applied across both default templates and custom LLM research copies.

---

## 4. Empirical Verification Evidence

### 4.1 Disposable Tempdir Compilation of `el-shaddai-coffee-katowice`
Compiled via `client_reporter.compile_and_export_client_package("el-shaddai-coffee-katowice", allow_draft=True)` in an isolated temporary directory:
- **Total Rows:** 14 rows.
- **Row 1:** `Campaign,Ad Group,Keyword,...,Final URL,Status` (25 columns).
- **Row 2:** `# SAMPLE CAMPAIGN - NOT VERIFIED FOR CLIENT USE` (25 columns).
- **All Data Rows (Rows 3–14):** Exactly 25 columns each.
- **Status Column:** 100% of rows contain `"Paused"`.
- **Ad Group Headlines (15 unique, all <= 30 chars, zero mid-word truncation):**
  1. `El Shaddai Indian Coffee` (24 ch)
  2. `Oficjalna Strona` (16 ch)
  3. `Poznaj Nasza Oferte` (19 ch)
  4. `Skontaktuj Sie Z Nami` (21 ch)
  5. `Sprawdz Nasz Katalog` (20 ch)
  6. `Wysoka Jakosc Produktow` (23 ch)
  7. `Oferta Online` (13 ch)
  8. `Dowiedz Sie Wiecej` (18 ch)
  9. `Szeroki Wybor` (13 ch)
  10. `Zamow Online` (12 ch)
  11. `Oryginalne Produkty` (19 ch)
  12. `Sprawdz Szczegoly` (17 ch)
  13. `Sprawdz Oferte Online` (21 ch)
  14. `Kontakt I Informacje` (20 ch)
  15. `Zobacz Nowosci` (14 ch)
- **Ad Group Descriptions (4 unique, all <= 90 chars, complete Polish sentences with period):**
  1. `Poznaj oferte El Shaddai Indian Coffee. Sprawdz szczegoly na naszej oficjalnej stronie.` (87 ch)
  2. `Skontaktuj sie z El Shaddai Indian Coffee. Zapewniamy bogaty wybor i fachowe doradztwo.` (87 ch)
  3. `Szukasz sprawdzonych rozwiazan? Dowiedz sie wiecej o ofercie dopasowanej do potrzeb.` (84 ch)
  4. `Odwiedz strone El Shaddai Indian Coffee i sprawdz nasz aktualny katalog produktow.` (82 ch)

### 4.2 Unit & Regression Test Suite
- `tests/test_campaign_builder_regression.py`: **15/15 PASS** (zero skips):
  - `test_truncate_to_word_boundary_behavior`: PASS
  - `test_polish_defaults_character_bounds_and_naturalness`: PASS
  - `test_csv_uniform_25_columns_and_row1_headers`: PASS
- `tests/test_distribution_phase2.py`: **6/6 PASS**
- `tests/test_distribution_cli.py`: **11/11 PASS**
- `tests/test_vertical_slice.py`: **5/5 PASS**
- `tests/test_client_reporter.py`: **4/4 PASS**

### 4.3 Full Model-Free Test Gate
`python tests/run_all.py` executed across all tiers:
- **Result:** **108/108 suites green (exit 0)** (90 unit, 8 containment, 10 integration).

### 4.4 Monitored Production Artifact Integrity
- `git status workspace/`: completely clean.
- Monitored files: All 299 files in `workspace/clients/`, `workspace/backups/`, `workspace/verifications/`, and `workspace/outbound_pitches/` remain 100% hash-identical.
