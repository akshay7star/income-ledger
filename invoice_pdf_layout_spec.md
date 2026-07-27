# Invoice PDF Layout and Preview Specification

## Reference Files

- Filled reference: `4.1 GenAQ July 2026.pdf`
- Blank reference: `Template Invoice.pdf`

These are private local references and must not be copied into Git.

The filled Gen Aquarius invoice is the canonical V1 visual target. The blank template is a secondary reference only: it uses a simpler non-tax layout, different party labels, and does not contain the GST summary required by the filled tax invoice.

## Document Geometry

- Page: US Letter, portrait
- PDF size: 612 x 792 points
- Main content bounds: x = 36 to 504 points
- Main content width: 468 points
- Title baseline area: approximately y = 18 to 32 points
- Main bordered invoice area: approximately y = 44 to 686 points
- Footer: centered below the border at approximately y = 692 points
- Border/table stroke: approximately 0.375 points
- Typeface: compact sans-serif equivalent to Arial/Helvetica
- Typical body size: 8.4 to 10 points
- Title: bold, 12 points

V1 should preserve these proportions so a generated invoice looks like the reference when printed at 100%.

## Canonical Page Structure

### 1. Title

- Centered `Tax Invoice`
- Bold, 12 point
- No logo in V1

### 2. Party and Invoice Header

Overall area: x = 36 to 504, y = 44 to 316.

Left side: x = 36 to 274.

- Seller block: y = 44 to 120
  - Seller display/legal name in bold
  - Address
  - Email and phone
  - GSTIN
  - State name and code
- Consignee / Ship To block: y = 120 to 218
  - Ship-to name
  - Shipping address
  - GSTIN
  - State name and code
- Buyer / Bill To block: y = 218 to 316
  - Client legal name
  - Billing address
  - GSTIN
  - State name and code

The editor must support `Ship To same as Bill To`, enabled by default. When disabled, the invoice stores separate ship-to name, address, GSTIN, and state fields.

Right side: x = 274 to 504, split near x = 389.

The filled reference uses compact two-column cells for:

- Invoice number
- Invoice date
- Delivery note
- Payment terms / mode of payment
- Reference number and date
- Other references
- Buyer's order number and date
- Dispatch document number
- Delivery note date
- Dispatched through
- Destination
- Terms of delivery

Only invoice number and date are required. The remaining cells stay visible but blank when unused, preserving the reference layout.

### 3. Service Line Table

Header starts near y = 316. The filled single-item reference ends the service area near y = 471.

Column boundaries:

| Column | Start x | End x | Width |
| --- | ---: | ---: | ---: |
| Sl. No. | 36.00 | 50.16 | 14.16 |
| Particulars | 50.16 | 273.36 | 223.20 |
| HSN/SAC | 273.36 | 320.52 | 47.16 |
| Quantity | 320.52 | 367.68 | 47.16 |
| Rate | 367.68 | 414.84 | 47.16 |
| Per | 414.84 | 435.60 | 20.76 |
| Amount | 435.60 | 503.88 | 68.28 |

Behavior:

- Descriptions wrap within the Particulars column.
- `Rate` is the line's total GST slab; for example, an entered 18% is split into the applicable tax-component rows in the PDF.
- `Amount` is entered separately and is the taxable value for the line. Quantity does not multiply this amount.
- Monetary values are right-aligned with Indian digit grouping and two decimals.
- HSN/SAC is centered or left-aligned consistently.
- Tax rows appear beneath the service lines with the tax name, component rate in the Rate column, `%` in the Per column, and the component amount.
- A same-state 18% GST slab is displayed as separate `Output-CGST-9%` and `Output-SGST-9%` rows; the combined 18% is not printed as a service-row rate.
- An inter-state 18% slab is displayed as one `Output-IGST-18%` row.
- Multiple line items expand vertically.
- If content exceeds one page, repeat the title/header/table headings and continue line items on subsequent pages.

### 4. Invoice Total and Amount in Words

- A compact total row follows the service area.
- Grand total includes GST and is right-aligned in bold.
- Use the rupee symbol when the selected PDF font embeds it reliably; otherwise use `INR`.
- Show `Amount Chargeable (in words)`.
- Show `E. & O.E` at the right.
- Amount words use the Indian numbering system and include paise.

### 5. GST Summary

The filled reference contains:

- HSN/SAC
- Taxable value
- CGST rate and amount
- SGST/UTGST rate and amount
- Total tax amount
- A bold totals row
- Tax amount in words

Conditional variants:

- Same-state supply: CGST + SGST/UTGST columns.
- Inter-state supply: replace split-tax columns with IGST rate and amount.
- No-GST supply: omit the GST summary or render a compact zero-tax summary; use one consistent behavior across preview and final PDF.

### 6. Signature and Footer

- Keep the lower section open and uncluttered.
- Right-aligned signature box.
- `for <seller legal/display name>` in bold.
- Optional signature image may be added later; V1 uses the configured signature label.
- Bottom-right `Authorised Signatory`.
- Centered footer: `This is a Computer Generated Invoice`.

## Data Required Beyond the Original Plan

Add these invoice-level fields or store them in validated structured metadata:

- `ship_to_same_as_bill_to`
- Ship-to name/legal name
- Ship-to address lines, city, state name/code, postal code
- Ship-to GSTIN
- Delivery note
- Reference number and reference date
- Buyer's order number and order date
- Dispatch document number
- Delivery note date
- Dispatched through
- Destination
- Terms of delivery
- Other references

These fields are optional except for the Bill To client and the state data required by GST calculations.

## Preview-First Output Workflow

The preview must use the same ReportLab renderer, page size, fonts, calculations, and layout code as the issued/downloaded PDF.

1. User creates or edits an invoice draft.
2. User saves the draft.
3. User selects `Preview`.
4. Backend recalculates totals and generates a fresh draft PDF.
5. Frontend opens the PDF in a large preview modal using a blob/object URL.
6. Draft preview displays a visible diagonal `DRAFT` watermark.
7. The modal shows:
   - Back to edit
   - Refresh preview
   - Issue invoice
   - Close
8. After issue, the modal refreshes with the final non-watermarked PDF.
9. `Print` and `Download PDF` actions are shown for the final PDF inside the preview modal.

Rules:

- App-level print/download actions remain disabled until a preview has loaded successfully.
- Any draft edit invalidates the previous preview.
- The preview shows the server-calculated values, not frontend-only calculations.
- The preview endpoint must not change invoice status or create a ledger record.
- Issuing regenerates the PDF from persisted draft data and captures the issue snapshot.
- The final downloaded/printed bytes must match the final preview bytes.
- Missing PDF, rendering errors, and validation errors keep the user in edit/preview state and must never issue the invoice.

## Visual Verification Checklist

- Page is 612 x 792 points and prints at 100% without clipping.
- Main frame and table align to the specified bounds.
- Seller, Ship To, and Bill To sections do not overlap.
- Optional reference cells remain aligned when blank.
- Long party names, addresses, and descriptions wrap safely.
- Same-state PDF shows CGST and SGST.
- Inter-state PDF shows IGST and no CGST/SGST.
- Grand total equals taxable value plus GST.
- Amount words and tax words match numeric totals.
- Draft watermark is visible but does not obscure critical values.
- Final PDF contains no draft watermark.
- Signature block and footer remain on the final page.
- Preview, downloaded PDF, and printed output use identical content.
- Expected TDS is entered as a percentage and calculated only on taxable value, excluding GST.
- Negative quantity, amount, GST rate, or TDS rate is rejected; percentage rates cannot exceed 100 and quantity must be greater than zero.
