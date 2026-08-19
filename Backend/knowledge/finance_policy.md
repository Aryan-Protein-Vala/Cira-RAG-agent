# Credit, Collections & Revenue Recognition Policy (v1.8)

Owner: Corporate Finance. Reviewed annually.

## Customer credit

- Every customer (OCRD, CardType = C) must have a credit limit recorded in the CreditLine field.
- Orders that push the outstanding balance above the credit limit are blocked until Finance releases them.
- Credit limits above INR 2,500,000 require CFO sign-off and an annual credit review.

## Collections

- Invoices (OINV) are due per the payment terms on the document; the standard term is 30 days.
- Dunning level 1 is issued at 7 days overdue, level 2 at 21 days, level 3 at 45 days.
- Accounts more than 60 days overdue are placed on delivery hold.
- Write-offs require CFO approval and a journal entry (OJDT) referencing the original invoice.

## Revenue recognition

- Revenue is recognised on delivery (ODLN posting), not on order entry.
- Service revenue is recognised over the contract period on a straight-line basis.
- Credit memos (ORIN) must reference the original invoice document number.

## Month-end close

- Sub-ledgers close on working day 2; the general ledger closes on working day 4.
- Open A/R and A/P ageing reports are circulated to the executive team on working day 5.
