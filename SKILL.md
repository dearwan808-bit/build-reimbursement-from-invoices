---
name: build-reimbursement-from-invoices
description: Turn uploaded invoice, receipt, ticket, and expense-support files into an auditable reimbursement workbook with line-item details, duplicate and payment-path checks, verified subtotals, and a final reimbursable total only when every amount is verified. Use for PDF/image/scan/ZIP invoice batches, expense reimbursement forms, invoice summaries, receipt consolidation, or requests such as “上传发票生成报销单、列明细和合计”.
---

# Build Reimbursement From Invoices

## Objective

Convert uploaded expense evidence into one traceable Excel reimbursement package. Preserve every source file, expose unresolved items, and never present an unverified amount as the final reimbursement total.

## Required coordination

1. Read and follow the installed `pdf` skill for PDF extraction, rendering, and visual checks.
2. Read and follow the installed `spreadsheets` skill for workbook creation, formulas, export, inspection, and visual verification.
3. Read [invoice-schema.md](references/invoice-schema.md) before defining extraction rows or workbook columns.
4. Run [validate_reimbursement_rows.py](scripts/validate_reimbursement_rows.py) after extraction and again after any manual correction.

## Workflow

### 1. Inventory the evidence

- Enumerate every uploaded PDF, image, scan, spreadsheet, and archive member before extracting values.
- Assign one source ID per file or ticket. For a multi-invoice PDF, assign one source locator per invoice, such as `file.pdf#page=3`.
- Keep original filenames. Treat filenames as clues, never as proof of amount, date, or invoice number.
- Record unreadable, encrypted, truncated, or unsupported files in the exception list instead of silently skipping them.

### 2. Extract and visually verify

- Extract the fields in [invoice-schema.md](references/invoice-schema.md).
- Prefer the visible face amount marked “价税合计（小写）”, ticket fare, or receipt total. Do not add line items again when the document already provides a total.
- Compare extracted key fields against the rendered source: invoice/ticket number, date, seller, total amount, and source locator.
- Set `verification_status` to `已核验` only after visual confirmation of the amount. Use `部分核验` or `未核验` when any key amount is ambiguous.
- For text-layer failures, render the relevant page and inspect it visually. If it remains unreadable, keep the amount unresolved.
- Distinguish document review from tax-platform authenticity verification. Set `tax_authenticity_status` to `未验真` unless an official verification result was actually obtained.

### 3. Classify reimbursement eligibility

- Set `reimbursement_status` to one of `可报销`, `不可报销`, or `待确认`.
- Do not treat public-to-public paid expenses, already reimbursed items, or petty-cash-settled items as employee reimbursement. Mark them `不可报销` or `待确认` until the payment path is confirmed.
- Keep missing-invoice or nonstandard evidence visible, but do not auto-approve it. Flag it for finance review.
- Do not infer company policy, cost center, project, claimant, or business purpose when the source does not establish it.

### 4. Detect duplicates and reconcile totals

- Use invoice code plus invoice number as the primary duplicate key.
- For tickets or receipts without invoice numbers, use the available ticket number; otherwise use a fingerprint of type, date, seller, amount, and description.
- Resolve every duplicate candidate as `非重复`, `保留`, or `排除`. Leave unresolved candidates as `待确认`.
- Save extracted rows as UTF-8 JSON following [invoice-schema.md](references/invoice-schema.md), then run:

```bash
python3 scripts/validate_reimbursement_rows.py --input extracted.json --output validated.json
```

- Use the script summary as the numeric control total. Re-run it after corrections; do not hand-edit its computed fields.
- If `ready_for_final_total` is false, report only the verified or eligible subtotal with a clear “待核验/待确认” label. Do not provide a final reimbursement total.

### 5. Build the Excel reimbursement package

Create one `.xlsx` file with these sheets:

1. `报销单`: claimant, department/project, purpose, period, evidence count, verified subtotal, eligible subtotal, unresolved counts, final status, and final reimbursement total.
2. `发票明细`: one row per invoice/ticket/receipt using the Chinese column mapping in [invoice-schema.md](references/invoice-schema.md).
3. `核验清单`: unreadable files, missing fields, duplicate candidates, payment-path issues, authenticity status, and required follow-up.

Workbook rules:

- Keep extracted inputs as typed values and all totals/counts as formulas.
- Make `最终报销合计` blank while any amount, duplicate, payment path, or eligibility decision is unresolved. Show a separate status cell explaining the blocker.
- Keep `已核验票面小计` and `已确认可报销小计` separate.
- Use currency/date/percentage types, freeze the detail header, add filters, and apply visible status formatting.
- Add the source filename and locator to every detail row so each number can be traced back.
- Do not mix currencies into one numeric total. Separate totals by currency unless an explicit conversion rule and source are supplied.
- Save the final workbook under `outputs/<unique-id>/发票报销单_<date>.xlsx` without overwriting source files.

### 6. Verify before delivery

- Confirm inventory count equals detail-row count plus explicitly documented exclusions.
- Reconcile workbook subtotals to the validator summary by currency.
- Inspect the key workbook ranges and scan for formula errors.
- Render and visually inspect all three sheets; fix clipped headers, unreadable amounts, missing status labels, or broken formulas.
- Reopen the persisted workbook and confirm the key totals and unresolved counts.

## Response contract

Return:

- the completed workbook;
- invoice/evidence count and currency;
- final reimbursement total only when `ready_for_final_total=true`;
- otherwise the verified subtotal plus a concise blocker list;
- the number of unreadable, duplicate, and payment-path exceptions.

Never claim completion when an uploaded item is absent from both the detail sheet and the exception list.
