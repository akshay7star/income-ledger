# Remaining Implementation Plan: Tax Statement Reconciliation Cleanup

## Summary

The Form 16 Part A/B and Form 26AS reconciliation feature has been implemented. Completed parser, schema, reconciliation, export, AI Advisor, and monthly mismatch details are archived in `project_context.md` session history.

The current active plan is limited to acceptance verification and future backlog. Tax reconciliation must remain advisory-only: it can show differences and source documents, but it must not update salary or freelance records directly.

## Current Behavior to Preserve

- Multiple Form 16 Part A/B documents are allowed for the same user and financial year.
- Only one Form 26AS is active for a user and financial year; superseded statements remain available for history until deleted.
- Monthly salary mismatch rows show the exact month, employer, salary/TDS values, and differences.
- Salary data changes only through the normal document review and manual confirmation flow.
- Tax document deletion removes the uploaded tax-statement PDF and parsed tax rows only; salary and freelance records are not changed.

## Remaining Acceptance Work

- Restart backend and frontend, then manually verify Reconcile for a user with salary slips, Form 16 Part A/B, and 26AS.
- Confirm no `Apply 26AS` button appears anywhere in Reconcile.
- Confirm monthly mismatch rows show `Open review` only when one linked payslip document can be reviewed; otherwise they show `Manual review`.
- Confirm Form 16 Part A, Form 16 Part B, active 26AS, and superseded 26AS documents can be deleted from the Reconcile tax-document table.
- Confirm deleting active 26AS refreshes Reconcile to show no active 26AS for that user/FY.
- Confirm manually correcting a salary slip in Review and pressing `Recheck` clears resolved mismatch rows.

## Verification Commands

- `C:\Users\aksha\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests\test_tax_documents.py -q --basetemp C:\tmp\income-ledger-pytest`
- `npm.cmd run build` from `frontend`

## Future Backlog

- Repair the workspace `.venv`/PATH Python setup and run the full backend test suite.
- Add a deterministic tax-document reparse endpoint only if users need parser reruns after template/parser changes.
- Add true non-salary Form 16A certificate support for freelance/professional TDS certificates.
- Add AIS parsing if the app needs broader government-statement reconciliation.
- Add official ITR JSON/export only after the advisory planner is stable enough for filing-prep workflows.
