import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  ChevronDown,
  ChevronUp,
  Download,
  Edit,
  Eye,
  Plus,
  Printer,
  RefreshCw,
  Save,
  Send,
  Trash2,
  UserRoundCog,
  UsersRound,
  X,
} from 'lucide-react';


function money(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}


function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}


function rateText(value) {
  return Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}


function itemTaxBreakdown(item, treatment) {
  if (treatment === 'no_gst') return [];
  const taxable = Math.round(Number(item.amount || 0) * 100) / 100;
  const gstRate = Number(item.rate || 0);
  if (treatment === 'same_state') {
    const componentRate = gstRate / 2;
    return [
      { tax: 'CGST', rate: componentRate, amount: Math.round(taxable * componentRate) / 100 },
      { tax: 'SGST', rate: componentRate, amount: Math.round(taxable * componentRate) / 100 },
    ];
  }
  return [
    { tax: 'IGST', rate: gstRate, amount: Math.round(taxable * gstRate) / 100 },
  ];
}


function emptyItem() {
  return {
    description: '',
    hsn_sac: '998314',
    quantity: 1,
    unit: 'Nos',
    rate: 18,
    amount: '',
  };
}


function emptyInvoice(profiles, clients) {
  const defaultProfile = profiles.find((profile) => profile.is_default) || profiles[0];
  return {
    invoice_number: '',
    invoice_date: todayIso(),
    billable_period: '',
    seller_profile_id: defaultProfile?.id || '',
    client_id: clients[0]?.id || '',
    ledger_user_id: '',
    place_of_supply: '',
    gst_treatment: 'auto',
    payment_terms: '',
    due_date: '',
    delivery_note: '',
    reference_number: '',
    reference_date: '',
    other_references: '',
    buyer_order_number: '',
    buyer_order_date: '',
    dispatch_document_number: '',
    delivery_note_date: '',
    dispatched_through: '',
    destination: '',
    terms_of_delivery: '',
    ship_to_same_as_bill_to: true,
    ship_to_name: '',
    ship_to_address_line1: '',
    ship_to_address_line2: '',
    ship_to_city: '',
    ship_to_state_name: '',
    ship_to_state_code: '',
    ship_to_postal_code: '',
    ship_to_gstin: '',
    tds_rate: 0,
    notes: '',
    items: [emptyItem()],
  };
}


function invoiceToForm(invoice) {
  const fields = {
    ...emptyInvoice([], []),
    ...invoice,
    seller_profile_id: invoice.seller_profile_id || '',
    client_id: invoice.client_id || '',
    ledger_user_id: invoice.ledger_user_id || '',
    due_date: invoice.due_date || '',
    reference_date: invoice.reference_date || '',
    buyer_order_date: invoice.buyer_order_date || '',
    delivery_note_date: invoice.delivery_note_date || '',
    ship_to_same_as_bill_to: Boolean(invoice.ship_to_same_as_bill_to),
    items: (invoice.items || []).map((item) => ({
      description: item.description || '',
      hsn_sac: item.hsn_sac || '',
      quantity: item.quantity ?? 1,
      unit: item.unit || 'Nos',
      rate: item.gst_rate ?? item.rate ?? 0,
      amount: item.amount ?? item.taxable_amount ?? '',
    })),
  };
  return fields;
}


function calculatePreview(form, profiles, clients) {
  const seller = profiles.find((profile) => String(profile.id) === String(form.seller_profile_id));
  const client = clients.find((entry) => String(entry.id) === String(form.client_id));
  const supplyState = form.ship_to_same_as_bill_to ? client?.state_code : form.ship_to_state_code;
  const treatment = form.gst_treatment === 'no_gst'
    ? 'no_gst'
    : (seller?.state_code && supplyState && seller.state_code !== supplyState ? 'inter_state' : 'same_state');
  return form.items.reduce((totals, item) => {
    const taxable = Math.round(Number(item.amount || 0) * 100) / 100;
    totals.subtotal += taxable;
    for (const component of itemTaxBreakdown(item, treatment)) {
      totals.gst += component.amount;
      if (component.tax === 'CGST') totals.cgst += component.amount;
      if (component.tax === 'SGST') totals.sgst += component.amount;
      if (component.tax === 'IGST') totals.igst += component.amount;
      const existing = totals.breakdown.find(
        (entry) => entry.tax === component.tax && entry.rate === component.rate,
      );
      if (existing) {
        existing.amount += component.amount;
      } else {
        totals.breakdown.push({ ...component });
      }
    }
    return totals;
  }, {
    treatment,
    subtotal: 0,
    cgst: 0,
    sgst: 0,
    igst: 0,
    gst: 0,
    breakdown: [],
    grand: 0,
    tds: 0,
    net: 0,
  });
}


const PROFILE_FIELDS = [
  ['display_name', 'Display name', true],
  ['legal_name', 'Legal name'],
  ['address_line1', 'Address line 1'],
  ['address_line2', 'Address line 2'],
  ['city', 'City'],
  ['state_name', 'State'],
  ['state_code', 'State code'],
  ['postal_code', 'Postal code'],
  ['email', 'Email'],
  ['phone', 'Phone'],
  ['gstin', 'GSTIN'],
  ['pan', 'PAN'],
  ['bank_name', 'Bank name'],
  ['bank_account_name', 'Account name'],
  ['bank_account_number', 'Account number'],
  ['bank_ifsc', 'IFSC'],
  ['signature_label', 'Signature label'],
];

const CLIENT_FIELDS = [
  ['client_name', 'Client name', true],
  ['legal_name', 'Legal name'],
  ['address_line1', 'Address line 1'],
  ['address_line2', 'Address line 2'],
  ['city', 'City'],
  ['state_name', 'State'],
  ['state_code', 'State code'],
  ['postal_code', 'Postal code'],
  ['email', 'Email'],
  ['phone', 'Phone'],
  ['gstin', 'GSTIN'],
  ['pan', 'PAN'],
];


function emptyParty(type) {
  const fields = type === 'profile' ? PROFILE_FIELDS : CLIENT_FIELDS;
  const result = Object.fromEntries(fields.map(([name]) => [name, '']));
  if (type === 'profile') {
    result.signature_label = 'Authorised Signatory';
    result.is_default = false;
  }
  return result;
}


function PartyManager({ type, records, api, onClose, onChanged }) {
  const isProfile = type === 'profile';
  const endpoint = isProfile ? '/invoice-profiles' : '/invoice-clients';
  const title = isProfile ? 'Seller Profiles' : 'Invoice Clients';
  const fields = isProfile ? PROFILE_FIELDS : CLIENT_FIELDS;
  const [form, setForm] = useState(emptyParty(type));
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  function edit(record) {
    setEditingId(record.id);
    setForm({ ...emptyParty(type), ...record, is_default: Boolean(record.is_default) });
    setError('');
  }

  function reset() {
    setEditingId(null);
    setForm(emptyParty(type));
    setError('');
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api(editingId ? `${endpoint}/${editingId}` : endpoint, {
        method: editingId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      reset();
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(record) {
    if (!window.confirm(`Delete ${isProfile ? record.display_name : record.client_name}?`)) return;
    setError('');
    try {
      await api(`${endpoint}/${record.id}`, { method: 'DELETE' });
      if (editingId === record.id) reset();
      await onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="ledger-modal-backdrop invoiceModalBackdrop" role="presentation">
      <div className="ledger-modal invoicePartyModal shadow-lg" role="dialog" aria-modal="true" aria-labelledby="party-manager-title">
        <div className="invoiceModalHeader">
          <div>
            <h2 id="party-manager-title">{title}</h2>
            <p>Create reusable details for invoice generation.</p>
          </div>
          <button className="btn btn-outline-secondary" type="button" onClick={onClose} aria-label="Close party manager"><X size={18} /></button>
        </div>
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        <div className="invoicePartyLayout">
          <form onSubmit={submit} className="invoicePartyForm">
            <h3>{editingId ? 'Edit record' : 'New record'}</h3>
            <div className="invoiceFieldGrid">
              {fields.map(([name, label, required]) => (
                <label key={name}>
                  <span>{label}</span>
                  <input
                    className="form-control"
                    value={form[name] || ''}
                    onChange={(event) => setForm({ ...form, [name]: event.target.value })}
                    required={Boolean(required)}
                  />
                </label>
              ))}
              {isProfile && (
                <label className="invoiceCheckbox">
                  <input type="checkbox" checked={Boolean(form.is_default)} onChange={(event) => setForm({ ...form, is_default: event.target.checked })} />
                  <span>Default seller</span>
                </label>
              )}
            </div>
            <div className="invoiceFormActions">
              {editingId && <button className="btn btn-outline-secondary" type="button" onClick={reset}>Cancel edit</button>}
              <button className="btn btn-primary" type="submit" disabled={busy}><Save size={16} /> {busy ? 'Saving...' : 'Save'}</button>
            </div>
          </form>
          <div className="invoicePartyList">
            <h3>Saved records</h3>
            {records.length === 0 && <p className="muted">No records yet.</p>}
            {records.map((record) => (
              <article key={record.id} className="invoicePartyCard">
                <div>
                  <strong>{isProfile ? record.display_name : record.client_name}</strong>
                  <small>{record.legal_name || ''}</small>
                  <small>{[record.state_name, record.state_code].filter(Boolean).join(' - ') || 'State not set'}</small>
                  <small>{record.gstin || 'GSTIN not set'}</small>
                </div>
                <div className="invoiceInlineActions">
                  <button className="btn btn-sm btn-outline-secondary" type="button" onClick={() => edit(record)} aria-label="Edit"><Edit size={15} /></button>
                  <button className="btn btn-sm btn-outline-danger" type="button" onClick={() => remove(record)} aria-label="Delete"><Trash2 size={15} /></button>
                </div>
              </article>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}


function InvoiceEditor({ invoice, profiles, clients, api, onClose, onSaved, onManageProfiles, onManageClients }) {
  const [form, setForm] = useState(() => invoice ? invoiceToForm(invoice) : emptyInvoice(profiles, clients));
  const [advanced, setAdvanced] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const totals = useMemo(() => {
    const calculated = calculatePreview(form, profiles, clients);
    calculated.grand = calculated.subtotal + calculated.gst;
    calculated.tds = Math.round(
      calculated.subtotal * Number(form.tds_rate || 0),
    ) / 100;
    calculated.net = calculated.grand - calculated.tds;
    return calculated;
  }, [form, profiles, clients]);

  function updateItem(index, field, value) {
    setForm({
      ...form,
      items: form.items.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item),
    });
  }

  function moveItem(index, direction) {
    const target = index + direction;
    if (target < 0 || target >= form.items.length) return;
    const items = [...form.items];
    [items[index], items[target]] = [items[target], items[index]];
    setForm({ ...form, items });
  }

  function removeItem(index) {
    if (form.items.length === 1) return;
    setForm({ ...form, items: form.items.filter((_, itemIndex) => itemIndex !== index) });
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const payload = {
        ...form,
        seller_profile_id: Number(form.seller_profile_id),
        client_id: Number(form.client_id),
        ledger_user_id: form.ledger_user_id ? Number(form.ledger_user_id) : null,
        tds_rate: Number(form.tds_rate || 0),
        tds_amount: undefined,
        due_date: form.due_date || null,
        reference_date: form.reference_date || null,
        buyer_order_date: form.buyer_order_date || null,
        delivery_note_date: form.delivery_note_date || null,
        items: form.items.map((item) => ({
          ...item,
          quantity: Number(item.quantity || 0),
          rate: Number(item.rate || 0),
          amount: Number(item.amount || 0),
          gst_rate: undefined,
        })),
      };
      const saved = await api(invoice ? `/invoices/${invoice.id}` : '/invoices', {
        method: invoice ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      await onSaved(saved);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ledger-modal-backdrop invoiceModalBackdrop" role="presentation">
      <form className="ledger-modal invoiceEditorModal shadow-lg" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="invoice-editor-title">
        <div className="invoiceModalHeader">
          <div>
            <h2 id="invoice-editor-title">{invoice ? `Edit ${invoice.invoice_number}` : 'Create Invoice Draft'}</h2>
            <p>Save the draft before opening the print-accurate PDF preview.</p>
          </div>
          <button className="btn btn-outline-secondary" type="button" onClick={onClose} aria-label="Close invoice editor"><X size={18} /></button>
        </div>
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        {(profiles.length === 0 || clients.length === 0) && (
          <div className="alert alert-warning">
            Create at least one seller profile and client before saving an invoice.
          </div>
        )}
        <div className="invoiceEditorScroll">
          <section className="invoiceEditorSection">
            <div className="invoiceSectionTitle">
              <h3>Invoice parties</h3>
              <div className="invoiceInlineActions">
                <button className="btn btn-sm btn-outline-secondary" type="button" onClick={onManageProfiles}><UserRoundCog size={15} /> Sellers</button>
                <button className="btn btn-sm btn-outline-secondary" type="button" onClick={onManageClients}><UsersRound size={15} /> Clients</button>
              </div>
            </div>
            <div className="invoiceFieldGrid invoiceFieldGridFour">
              <label>
                <span>Seller profile</span>
                <select className="form-select" value={form.seller_profile_id} onChange={(event) => setForm({ ...form, seller_profile_id: event.target.value })} required>
                  <option value="">Select seller</option>
                  {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name}{profile.is_default ? ' (default)' : ''}</option>)}
                </select>
              </label>
              <label>
                <span>Bill To client</span>
                <select className="form-select" value={form.client_id} onChange={(event) => setForm({ ...form, client_id: event.target.value })} required>
                  <option value="">Select client</option>
                  {clients.map((client) => <option key={client.id} value={client.id}>{client.client_name}</option>)}
                </select>
              </label>
              <label>
                <span>Invoice number</span>
                <input className="form-control" value={form.invoice_number} onChange={(event) => setForm({ ...form, invoice_number: event.target.value })} placeholder="004/2026-27" required />
              </label>
              <label>
                <span>Invoice date</span>
                <input className="form-control" type="date" value={form.invoice_date} onChange={(event) => setForm({ ...form, invoice_date: event.target.value })} required />
              </label>
              <label>
                <span>Billable period</span>
                <input className="form-control" value={form.billable_period} onChange={(event) => setForm({ ...form, billable_period: event.target.value })} placeholder="July 2026" />
              </label>
              <label>
                <span>Place of supply</span>
                <input className="form-control" value={form.place_of_supply} onChange={(event) => setForm({ ...form, place_of_supply: event.target.value })} />
              </label>
              <label>
                <span>GST treatment</span>
                <select className="form-select" value={form.gst_treatment} onChange={(event) => setForm({ ...form, gst_treatment: event.target.value })}>
                  <option value="auto">Automatic from state codes</option>
                  <option value="same_state">Same-state CGST/SGST</option>
                  <option value="inter_state">Inter-state IGST</option>
                  <option value="no_gst">No GST</option>
                </select>
              </label>
              <label>
                <span>Payment terms</span>
                <input className="form-control" value={form.payment_terms} onChange={(event) => setForm({ ...form, payment_terms: event.target.value })} />
              </label>
            </div>
            <label className="invoiceCheckbox invoiceShipToggle">
              <input type="checkbox" checked={form.ship_to_same_as_bill_to} onChange={(event) => setForm({ ...form, ship_to_same_as_bill_to: event.target.checked })} />
              <span>Ship To is the same as Bill To</span>
            </label>
            {!form.ship_to_same_as_bill_to && (
              <div className="invoiceFieldGrid invoiceFieldGridFour invoiceShipFields">
                {[
                  ['ship_to_name', 'Ship To name'],
                  ['ship_to_address_line1', 'Address line 1'],
                  ['ship_to_address_line2', 'Address line 2'],
                  ['ship_to_city', 'City'],
                  ['ship_to_state_name', 'State'],
                  ['ship_to_state_code', 'State code'],
                  ['ship_to_postal_code', 'Postal code'],
                  ['ship_to_gstin', 'GSTIN'],
                ].map(([field, label]) => (
                  <label key={field}>
                    <span>{label}</span>
                    <input className="form-control" value={form[field]} onChange={(event) => setForm({ ...form, [field]: event.target.value })} required={field === 'ship_to_name'} />
                  </label>
                ))}
              </div>
            )}
          </section>

          <section className="invoiceEditorSection">
            <div className="invoiceSectionTitle">
              <h3>Service line items</h3>
              <button className="btn btn-sm btn-outline-primary" type="button" onClick={() => setForm({ ...form, items: [...form.items, emptyItem()] })}><Plus size={15} /> Add line</button>
            </div>
            <div className="invoiceLineTableWrap">
              <table className="table invoiceLineTable">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Particulars</th>
                    <th>HSN/SAC</th>
                    <th>Qty</th>
                    <th>Unit</th>
                    <th>Rate (GST %)</th>
                    <th>Amount</th>
                    <th>GST breakdown</th>
                    <th aria-label="Actions"></th>
                  </tr>
                </thead>
                <tbody>
                  {form.items.map((item, index) => (
                    <tr key={index}>
                      <td>{index + 1}</td>
                      <td><textarea className="form-control" rows="2" value={item.description} onChange={(event) => updateItem(index, 'description', event.target.value)} required /></td>
                      <td><input className="form-control" value={item.hsn_sac} onChange={(event) => updateItem(index, 'hsn_sac', event.target.value)} /></td>
                      <td><input className="form-control" type="number" min="0.01" step="any" value={item.quantity} onChange={(event) => updateItem(index, 'quantity', event.target.value)} required /></td>
                      <td><input className="form-control" value={item.unit} onChange={(event) => updateItem(index, 'unit', event.target.value)} /></td>
                      <td><input className="form-control" type="number" min="0" max="100" step="any" value={item.rate} onChange={(event) => updateItem(index, 'rate', event.target.value)} required /></td>
                      <td><input className="form-control" type="number" min="0" step="0.01" value={item.amount} onChange={(event) => updateItem(index, 'amount', event.target.value)} required /></td>
                      <td className="invoiceTaxBreakdownCell">
                        {itemTaxBreakdown(item, totals.treatment).map((component) => (
                          <span key={component.tax}>
                            {component.tax} {rateText(component.rate)}%: <strong>{money(component.amount)}</strong>
                          </span>
                        ))}
                        {totals.treatment === 'no_gst' && <span>No GST</span>}
                      </td>
                      <td>
                        <div className="invoiceLineActions">
                          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => moveItem(index, -1)} disabled={index === 0} aria-label="Move line up"><ChevronUp size={14} /></button>
                          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => moveItem(index, 1)} disabled={index === form.items.length - 1} aria-label="Move line down"><ChevronDown size={14} /></button>
                          <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => removeItem(index)} disabled={form.items.length === 1} aria-label="Remove line"><Trash2 size={14} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="invoiceEditorSection invoiceTotalsSection">
            <div>
              <button className="btn btn-outline-secondary" type="button" onClick={() => setAdvanced(!advanced)}>
                {advanced ? 'Hide' : 'Show'} reference and delivery fields
              </button>
              {advanced && (
                <div className="invoiceFieldGrid invoiceFieldGridFour invoiceAdvancedFields">
                  {[
                    ['delivery_note', 'Delivery note'],
                    ['reference_number', 'Reference number'],
                    ['reference_date', 'Reference date', 'date'],
                    ['other_references', 'Other references'],
                    ['buyer_order_number', "Buyer's order number"],
                    ['buyer_order_date', "Buyer's order date", 'date'],
                    ['dispatch_document_number', 'Dispatch document number'],
                    ['delivery_note_date', 'Delivery note date', 'date'],
                    ['dispatched_through', 'Dispatched through'],
                    ['destination', 'Destination'],
                    ['terms_of_delivery', 'Terms of delivery'],
                    ['due_date', 'Due date', 'date'],
                  ].map(([field, label, type]) => (
                    <label key={field}>
                      <span>{label}</span>
                      <input className="form-control" type={type || 'text'} value={form[field]} onChange={(event) => setForm({ ...form, [field]: event.target.value })} />
                    </label>
                  ))}
                </div>
              )}
              <div className="invoiceFieldGrid invoiceNotesGrid">
                <label>
                  <span>Expected TDS %</span>
                  <input className="form-control" type="number" min="0" max="100" step="any" value={form.tds_rate} onChange={(event) => setForm({ ...form, tds_rate: event.target.value })} />
                </label>
                <label>
                  <span>Notes</span>
                  <textarea className="form-control" rows="2" value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
                </label>
              </div>
            </div>
            <dl className="invoiceTotalsCard">
              <div><dt>Tax treatment</dt><dd>{totals.treatment.replace('_', ' ')}</dd></div>
              <div><dt>Taxable value</dt><dd>{money(totals.subtotal)}</dd></div>
              {totals.breakdown.map((component) => (
                <div key={`${component.tax}-${component.rate}`}>
                  <dt>{component.tax} @ {rateText(component.rate)}%</dt>
                  <dd>{money(component.amount)}</dd>
                </div>
              ))}
              <div><dt>Total GST</dt><dd>{money(totals.gst)}</dd></div>
              <div className="invoiceGrandTotal"><dt>Grand total</dt><dd>{money(totals.grand)}</dd></div>
              <div><dt>Expected TDS ({rateText(form.tds_rate)}%)</dt><dd>{money(totals.tds)}</dd></div>
              <div><dt>Net receivable after TDS</dt><dd>{money(totals.net)}</dd></div>
            </dl>
          </section>
        </div>
        <div className="invoiceFormActions invoiceEditorActions">
          <button className="btn btn-outline-secondary" type="button" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" type="submit" disabled={busy || profiles.length === 0 || clients.length === 0}>
            <Save size={16} /> {busy ? 'Saving draft...' : 'Save draft'}
          </button>
        </div>
      </form>
    </div>
  );
}


function InvoicePreviewModal({ invoice, url, blob, users, api, apiBlob, onClose, onChanged }) {
  const frameRef = useRef(null);
  const [linkIncome, setLinkIncome] = useState(false);
  const [ledgerUserId, setLedgerUserId] = useState(invoice.ledger_user_id || '');
  const [issuing, setIssuing] = useState(false);
  const [error, setError] = useState('');
  const [currentInvoice, setCurrentInvoice] = useState(invoice);
  const [currentUrl, setCurrentUrl] = useState(url);
  const [currentBlob, setCurrentBlob] = useState(blob);

  useEffect(() => () => {
    if (currentUrl && currentUrl !== url) URL.revokeObjectURL(currentUrl);
  }, [currentUrl, url]);

  function download() {
    const link = document.createElement('a');
    link.href = currentUrl;
    link.download = currentInvoice.pdf_filename || `invoice-${currentInvoice.invoice_number.replace(/[^A-Za-z0-9]+/g, '-')}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function printPdf() {
    frameRef.current?.contentWindow?.focus();
    frameRef.current?.contentWindow?.print();
  }

  async function issue() {
    setIssuing(true);
    setError('');
    try {
      const issued = await api(`/invoices/${currentInvoice.id}/issue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          create_income_record: linkIncome,
          ledger_user_id: linkIncome ? Number(ledgerUserId) : null,
        }),
      });
      const finalBlob = await apiBlob(`/invoices/${issued.id}/pdf`);
      const finalUrl = URL.createObjectURL(finalBlob);
      if (currentUrl) URL.revokeObjectURL(currentUrl);
      setCurrentInvoice(issued);
      setCurrentBlob(finalBlob);
      setCurrentUrl(finalUrl);
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setIssuing(false);
    }
  }

  return (
    <div className="ledger-modal-backdrop invoiceModalBackdrop" role="presentation">
      <div className="ledger-modal invoicePreviewModal shadow-lg" role="dialog" aria-modal="true" aria-labelledby="invoice-preview-title">
        <div className="invoiceModalHeader">
          <div>
            <h2 id="invoice-preview-title">{currentInvoice.status === 'draft' ? 'Draft PDF Preview' : 'Invoice PDF Preview'}</h2>
            <p>{currentInvoice.invoice_number} - review the exact output before printing or downloading.</p>
          </div>
          <button className="btn btn-outline-secondary" type="button" onClick={onClose} aria-label="Close invoice preview"><X size={18} /></button>
        </div>
        {error && <div className="alert alert-danger" role="alert">{error}</div>}
        <div className="invoicePreviewFrameWrap">
          <iframe ref={frameRef} className="invoicePreviewFrame" title={`Invoice ${currentInvoice.invoice_number} PDF preview`} src={`${currentUrl}#toolbar=0&navpanes=0`} />
        </div>
        <div className="invoicePreviewFooter">
          {currentInvoice.status === 'draft' && (
            <div className="invoiceIssueOptions">
              <label className="invoiceCheckbox">
                <input type="checkbox" checked={linkIncome} onChange={(event) => setLinkIncome(event.target.checked)} />
                <span>Create a linked freelance income record</span>
              </label>
              {linkIncome && (
                <select className="form-select" value={ledgerUserId} onChange={(event) => setLedgerUserId(event.target.value)} required>
                  <option value="">Select ledger user</option>
                  {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
                </select>
              )}
            </div>
          )}
          <div className="invoicePreviewActions">
            <button className="btn btn-outline-secondary" type="button" onClick={onClose}>Back</button>
            <button className="btn btn-outline-primary" type="button" onClick={printPdf} disabled={!currentBlob}><Printer size={16} /> Print</button>
            <button className="btn btn-outline-primary" type="button" onClick={download} disabled={!currentBlob}><Download size={16} /> {currentInvoice.status === 'draft' ? 'Download draft' : 'Download PDF'}</button>
            {currentInvoice.status === 'draft' && (
              <button className="btn btn-primary" type="button" onClick={issue} disabled={issuing || (linkIncome && !ledgerUserId)}>
                <Send size={16} /> {issuing ? 'Issuing...' : 'Issue invoice'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


function CancelInvoiceModal({ invoice, api, onClose, onCancelled }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api(`/invoices/${invoice.id}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      await onCancelled();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ledger-modal-backdrop invoiceModalBackdrop">
      <form className="ledger-modal invoiceCancelModal shadow-lg" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="cancel-invoice-title">
        <div className="invoiceModalHeader">
          <div>
            <h2 id="cancel-invoice-title">Cancel Invoice</h2>
            <p>{invoice.invoice_number} will remain in the audit history.</p>
          </div>
          <button className="btn btn-outline-secondary" type="button" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        {invoice.linked_income && <div className="alert alert-warning">The linked income record will not be deleted automatically. Correct it separately if needed.</div>}
        {error && <div className="alert alert-danger">{error}</div>}
        <label>
          <span>Cancellation reason</span>
          <textarea className="form-control" rows="3" value={reason} onChange={(event) => setReason(event.target.value)} required autoFocus />
        </label>
        <div className="invoiceFormActions">
          <button className="btn btn-outline-secondary" type="button" onClick={onClose}>Keep invoice</button>
          <button className="btn btn-danger" type="submit" disabled={busy || !reason.trim()}>{busy ? 'Cancelling...' : 'Cancel invoice'}</button>
        </div>
      </form>
    </div>
  );
}


export default function InvoicesView({ api, apiBlob, users, selectedYear }) {
  const [invoices, setInvoices] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [clientFilter, setClientFilter] = useState('');
  const [editorInvoice, setEditorInvoice] = useState(undefined);
  const [partyManager, setPartyManager] = useState('');
  const [preview, setPreview] = useState(null);
  const [cancelTarget, setCancelTarget] = useState(null);

  async function refresh() {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (selectedYear) params.set('financial_year', selectedYear);
      if (statusFilter) params.set('status', statusFilter);
      if (clientFilter) params.set('client_id', clientFilter);
      const [invoiceRows, profileRows, clientRows] = await Promise.all([
        api(`/invoices?${params.toString()}`),
        api('/invoice-profiles'),
        api('/invoice-clients'),
      ]);
      setInvoices(invoiceRows);
      setProfiles(profileRows);
      setClients(clientRows);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [selectedYear, statusFilter, clientFilter]);

  useEffect(() => () => {
    if (preview?.url) URL.revokeObjectURL(preview.url);
  }, [preview]);

  async function edit(invoice) {
    setError('');
    try {
      const detail = await api(`/invoices/${invoice.id}`);
      setEditorInvoice(detail);
    } catch (err) {
      setError(err.message);
    }
  }

  async function remove(invoice) {
    if (!window.confirm(`Delete draft ${invoice.invoice_number}?`)) return;
    setError('');
    try {
      await api(`/invoices/${invoice.id}`, { method: 'DELETE' });
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  async function openPreview(invoice) {
    setError('');
    try {
      const detail = await api(`/invoices/${invoice.id}`);
      const blob = await apiBlob(
        detail.status === 'draft' ? `/invoices/${detail.id}/preview` : `/invoices/${detail.id}/pdf`,
        detail.status === 'draft' ? { method: 'POST' } : {},
      );
      const url = URL.createObjectURL(blob);
      setPreview({ invoice: { ...detail, pdf_filename: detail.pdf_filename || `invoice-${detail.invoice_number}.pdf` }, blob, url });
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  function closePreview() {
    if (preview?.url) URL.revokeObjectURL(preview.url);
    setPreview(null);
  }

  return (
    <section className="invoicesView" aria-labelledby="invoices-title">
      <div className="invoicesHeader">
        <div>
          <h2 id="invoices-title">Invoices</h2>
          <p>Create, preview, issue, and download GST service invoices.</p>
        </div>
        <div className="invoiceHeaderActions">
          <button className="btn btn-outline-secondary" type="button" onClick={() => setPartyManager('profile')}><UserRoundCog size={16} /> Sellers</button>
          <button className="btn btn-outline-secondary" type="button" onClick={() => setPartyManager('client')}><UsersRound size={16} /> Clients</button>
          <button className="btn btn-outline-secondary" type="button" onClick={refresh} disabled={loading}><RefreshCw size={16} /> Refresh</button>
          <button className="btn btn-primary" type="button" onClick={() => setEditorInvoice(null)}><Plus size={16} /> New invoice</button>
        </div>
      </div>

      <div className="invoiceFilters">
        <label>
          <span>Status</span>
          <select className="form-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="issued">Issued</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
        <label>
          <span>Client</span>
          <select className="form-select" value={clientFilter} onChange={(event) => setClientFilter(event.target.value)}>
            <option value="">All clients</option>
            {clients.map((client) => <option key={client.id} value={client.id}>{client.client_name}</option>)}
          </select>
        </label>
        <div className="invoiceFilterYear">
          <span>Financial year</span>
          <strong>{selectedYear || 'All years'}</strong>
        </div>
      </div>

      {error && <div className="alert alert-danger" role="alert">{error}</div>}
      <div className="invoiceListPanel shadow-sm">
        {loading ? (
          <div className="invoiceEmptyState">Loading invoices...</div>
        ) : invoices.length === 0 ? (
          <div className="invoiceEmptyState">
            <Eye size={30} />
            <h3>No invoices found</h3>
            <p>Create a draft, then preview the exact PDF before issuing it.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table align-middle invoiceListTable">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Date</th>
                  <th>Client</th>
                  <th>Status</th>
                  <th>Taxable</th>
                  <th>GST</th>
                  <th>Grand total</th>
                  <th>Ledger</th>
                  <th className="text-end">Actions</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id}>
                    <td><strong>{invoice.invoice_number}</strong><small>{invoice.billable_period || invoice.financial_year}</small></td>
                    <td>{invoice.invoice_date}</td>
                    <td>{invoice.client_name}</td>
                    <td><span className={`invoiceStatus invoiceStatus-${invoice.status}`}>{invoice.status}</span></td>
                    <td>{money(invoice.subtotal_amount)}</td>
                    <td>{money(invoice.gst_amount)}</td>
                    <td><strong>{money(invoice.grand_total_amount)}</strong></td>
                    <td>{invoice.linked_income ? <span title={`Income record ${invoice.income_record_id}`}><Check size={16} /> Linked</span> : <span className="muted">Not linked</span>}</td>
                    <td>
                      <div className="invoiceRowActions">
                        {invoice.status === 'draft' && <button className="btn btn-sm btn-outline-secondary" type="button" onClick={() => edit(invoice)} title="Edit draft"><Edit size={15} /></button>}
                        <button className="btn btn-sm btn-outline-primary" type="button" onClick={() => openPreview(invoice)} title="Preview PDF"><Eye size={15} /></button>
                        {invoice.status === 'draft' && <button className="btn btn-sm btn-outline-danger" type="button" onClick={() => remove(invoice)} title="Delete draft"><Trash2 size={15} /></button>}
                        {invoice.status === 'issued' && <button className="btn btn-sm btn-outline-danger" type="button" onClick={() => setCancelTarget(invoice)} title="Cancel invoice"><X size={15} /></button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editorInvoice !== undefined && (
        <InvoiceEditor
          invoice={editorInvoice}
          profiles={profiles}
          clients={clients}
          api={api}
          onClose={() => setEditorInvoice(undefined)}
          onManageProfiles={() => setPartyManager('profile')}
          onManageClients={() => setPartyManager('client')}
          onSaved={async (saved) => {
            setEditorInvoice(undefined);
            await refresh();
            await openPreview(saved);
          }}
        />
      )}
      {partyManager && (
        <PartyManager
          type={partyManager}
          records={partyManager === 'profile' ? profiles : clients}
          api={api}
          onClose={() => setPartyManager('')}
          onChanged={refresh}
        />
      )}
      {preview && (
        <InvoicePreviewModal
          invoice={preview.invoice}
          url={preview.url}
          blob={preview.blob}
          users={users}
          api={api}
          apiBlob={apiBlob}
          onClose={closePreview}
          onChanged={refresh}
        />
      )}
      {cancelTarget && (
        <CancelInvoiceModal
          invoice={cancelTarget}
          api={api}
          onClose={() => setCancelTarget(null)}
          onCancelled={async () => {
            setCancelTarget(null);
            await refresh();
          }}
        />
      )}
    </section>
  );
}
