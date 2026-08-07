#!/usr/bin/env python3
"""Validate extracted reimbursement rows and compute auditable control totals."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


VERIFICATION_VALUES = {"已核验", "部分核验", "未核验"}
REIMBURSEMENT_VALUES = {"可报销", "不可报销", "待确认"}
DUPLICATE_VALUES = {"无重复", "待确认", "非重复", "保留", "排除"}
RESOLVED_DUPLICATE_VALUES = {"无重复", "非重复", "保留", "排除"}
REQUIRED_VISIBLE_FIELDS = ("source_file", "document_type", "total_amount")
TWOPLACES = Decimal("0.01")


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def parse_amount(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("¥", "").replace("￥", "")
    if not text:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if amount < 0:
        return None
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def money_text(value: Decimal) -> str:
    return format(value.quantize(TWOPLACES, rounding=ROUND_HALF_UP), "f")


def duplicate_key(item: dict, amount: Decimal | None) -> str:
    invoice_number = normalize_text(item.get("invoice_number"))
    invoice_code = normalize_text(item.get("invoice_code"))
    if invoice_number:
        return f"INVOICE:{invoice_code}:{invoice_number}"
    ticket_number = normalize_text(item.get("ticket_number"))
    if ticket_number:
        return f"TICKET:{ticket_number}"
    fingerprint_parts = (
        normalize_text(item.get("document_type")),
        normalize_text(item.get("invoice_date")),
        normalize_text(item.get("seller_name")),
        money_text(amount) if amount is not None else "INVALID",
        normalize_text(item.get("description")),
    )
    return "FINGERPRINT:" + "|".join(fingerprint_parts)


def load_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Input must be a JSON object containing an items array.")
    if not all(isinstance(item, dict) for item in payload["items"]):
        raise ValueError("Every items entry must be a JSON object.")
    return payload


def validate(payload: dict) -> dict:
    prepared = []
    keys = []
    for index, source in enumerate(payload["items"], start=1):
        item = dict(source)
        amount = parse_amount(item.get("total_amount"))
        key = duplicate_key(item, amount)
        keys.append(key)
        item["row_number"] = index
        item["currency"] = normalize_text(item.get("currency")) or "CNY"
        item["total_amount"] = money_text(amount) if amount is not None else None
        item["duplicate_key"] = key
        item["_valid_amount"] = amount is not None
        prepared.append(item)

    key_counts = Counter(keys)
    currency_totals = defaultdict(lambda: {
        "verified_face_amount_subtotal": Decimal("0.00"),
        "eligible_amount_subtotal": Decimal("0.00"),
    })
    warning_rows = []
    unresolved_duplicate_count = 0
    unverified_amount_count = 0
    pending_reimbursement_count = 0
    invalid_amount_count = 0
    missing_required_count = 0

    for item in prepared:
        missing = [field for field in REQUIRED_VISIBLE_FIELDS if item.get(field) in (None, "")]
        verification_status = str(item.get("verification_status") or "未核验")
        reimbursement_status = str(item.get("reimbursement_status") or "待确认")
        duplicate_status = str(item.get("duplicate_status") or "无重复")
        payment_path = str(item.get("payment_path") or "待确认")
        warnings = []

        if missing:
            missing_required_count += 1

        if verification_status not in VERIFICATION_VALUES:
            warnings.append("金额核验状态值无效")
            verification_status = "未核验"
        if reimbursement_status not in REIMBURSEMENT_VALUES:
            warnings.append("报销判断值无效")
            reimbursement_status = "待确认"
        if duplicate_status not in DUPLICATE_VALUES:
            warnings.append("重复状态值无效")
            duplicate_status = "待确认"

        if reimbursement_status == "可报销" and payment_path in {"待确认", "公对公", "备用金", "公司卡"}:
            warnings.append("支付或资金路径与员工报销不一致，需确认")
            reimbursement_status = "待确认"

        if key_counts[item["duplicate_key"]] > 1 and duplicate_status == "无重复":
            duplicate_status = "待确认"
            warnings.append("发现相同重复识别键，需人工确认")

        amount = parse_amount(item.get("total_amount"))
        if amount is None:
            invalid_amount_count += 1
            warnings.append("票面金额缺失、无效或为负数")
        verified = verification_status == "已核验" and amount is not None
        if not verified:
            unverified_amount_count += 1
        else:
            currency_totals[item["currency"]]["verified_face_amount_subtotal"] += amount

        if reimbursement_status == "待确认":
            pending_reimbursement_count += 1
        if duplicate_status not in RESOLVED_DUPLICATE_VALUES:
            unresolved_duplicate_count += 1

        eligible = (
            amount
            if verified
            and reimbursement_status == "可报销"
            and duplicate_status in {"无重复", "非重复", "保留"}
            else Decimal("0.00")
        )
        currency_totals[item["currency"]]["eligible_amount_subtotal"] += eligible

        item["verification_status"] = verification_status
        item["reimbursement_status"] = reimbursement_status
        item["duplicate_status"] = duplicate_status
        item["eligible_amount"] = money_text(eligible)
        item["missing_fields"] = missing
        item["warnings"] = warnings
        item.pop("_valid_amount", None)
        if missing or warnings:
            warning_rows.append(item["row_number"])

    ready = (
        bool(prepared)
        and unverified_amount_count == 0
        and invalid_amount_count == 0
        and missing_required_count == 0
        and pending_reimbursement_count == 0
        and unresolved_duplicate_count == 0
    )
    totals = {
        currency: {key: money_text(value) for key, value in values.items()}
        for currency, values in sorted(currency_totals.items())
    }
    final_totals = (
        {currency: values["eligible_amount_subtotal"] for currency, values in totals.items()}
        if ready
        else None
    )

    return {
        "meta": payload.get("meta", {}),
        "items": prepared,
        "summary": {
            "item_count": len(prepared),
            "currency_totals": totals,
            "unverified_amount_count": unverified_amount_count,
            "invalid_amount_count": invalid_amount_count,
            "missing_required_count": missing_required_count,
            "pending_reimbursement_count": pending_reimbursement_count,
            "unresolved_duplicate_count": unresolved_duplicate_count,
            "warning_rows": warning_rows,
            "ready_for_final_total": ready,
            "final_reimbursement_totals": final_totals,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Input UTF-8 JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Output UTF-8 JSON file")
    args = parser.parse_args()
    try:
        result = validate(load_payload(args.input))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
