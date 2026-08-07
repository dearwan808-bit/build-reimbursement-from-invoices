# Invoice extraction and workbook schema

Use one JSON object per invoice, ticket, or receipt in an `items` array. Keep monetary values as JSON numbers or decimal strings, never as currency-formatted text.

## Input JSON

```json
{
  "meta": {
    "claimant": "待确认",
    "department": "待确认",
    "project": "待确认",
    "purpose": "待确认"
  },
  "items": [
    {
      "source_file": "invoice-01.pdf",
      "source_locator": "invoice-01.pdf#page=1",
      "document_type": "增值税电子普通发票",
      "invoice_code": "",
      "invoice_number": "12345678",
      "ticket_number": "",
      "invoice_date": "2026-08-01",
      "seller_name": "示例供应商",
      "buyer_name": "示例公司",
      "description": "办公用品",
      "expense_category": "办公费",
      "project": "示例项目",
      "amount_excluding_tax": "94.34",
      "tax_amount": "5.66",
      "total_amount": "100.00",
      "currency": "CNY",
      "payment_path": "员工垫付",
      "verification_status": "已核验",
      "tax_authenticity_status": "未验真",
      "reimbursement_status": "可报销",
      "duplicate_status": "无重复",
      "notes": ""
    }
  ]
}
```

## Controlled values

- `verification_status`: `已核验`, `部分核验`, `未核验`
- `reimbursement_status`: `可报销`, `不可报销`, `待确认`
- `duplicate_status`: `无重复`, `待确认`, `非重复`, `保留`, `排除`
- `payment_path`: prefer `员工垫付`, `公对公`, `备用金`, `公司卡`, `待确认`; preserve another explicit source-backed value when needed
- `currency`: ISO code such as `CNY`, `USD`, or `EUR`

## Chinese workbook columns

| JSON field | Excel column |
|---|---|
| computed `row_number` | 序号 |
| `source_file` | 原文件 |
| `source_locator` | 来源定位 |
| `document_type` | 凭证类型 |
| `invoice_code` | 发票代码 |
| `invoice_number` | 发票号码 |
| `ticket_number` | 票据号码 |
| `invoice_date` | 开票/乘车日期 |
| `seller_name` | 销方/承运方 |
| `buyer_name` | 购买方 |
| `description` | 项目或服务名称 |
| `expense_category` | 费用类别 |
| `project` | 项目归属 |
| `amount_excluding_tax` | 不含税金额 |
| `tax_amount` | 税额 |
| `total_amount` | 价税合计/票面金额 |
| `currency` | 币种 |
| `payment_path` | 支付/资金路径 |
| `verification_status` | 金额核验状态 |
| `tax_authenticity_status` | 税务验真状态 |
| computed `duplicate_key` | 重复识别键 |
| computed `duplicate_status` | 重复状态 |
| `reimbursement_status` | 报销判断 |
| computed `eligible_amount` | 可报销金额 |
| computed `missing_fields` | 缺失字段 |
| `notes` | 备注 |

## Amount rules

- Parse amounts with decimal arithmetic and round to two decimal places.
- Require `total_amount >= 0`.
- Never derive an unreadable face amount from the filename.
- Treat an amount as verified only when `verification_status=已核验` and the amount is valid.
- Set eligible amount to the verified total only when the row is `可报销` and its duplicate status is resolved as `无重复`, `非重复`, or `保留`.
- Do not accept `可报销` while the payment path is `待确认`, `公对公`, `备用金`, or `公司卡`; resolve the payment or settlement status first.
- Exclude `不可报销`, `排除`, unverified, invalid, and unresolved rows from eligible subtotals.
- Finalize only after every row has a verified amount, every reimbursement decision is resolved, and every duplicate candidate is resolved.

## Duplicate rules

1. Prefer normalized `invoice_code + invoice_number`.
2. Otherwise use normalized `ticket_number`.
3. Otherwise use a fallback fingerprint from document type, date, seller, amount, and description.
4. A shared duplicate key is a candidate, not automatic proof. Keep both rows and request resolution.
