import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertTriangle,
  BarChart3,
  Calculator,
  Check,
  FileDown,
  FileText,
  IndianRupee,
  Moon,
  Plus,
  Sun,
  Trash2,
  Upload,
  UserPlus,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import 'bootstrap/dist/css/bootstrap.min.css';
import './styles.css';

const API = 'http://127.0.0.1:8001/api';

function currency(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function roundMoney(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

function financialYearForDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const start = month >= 4 ? year : year - 1;
  return `FY ${start}-${String(start + 1).slice(-2)}`;
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="premium-tooltip">
        <div className="premium-tooltip-title">{label}</div>
        {payload.map((item, index) => {
          // Resolve actual color from gradient url if needed
          let markerColor = item.color || item.fill;
          if (markerColor.includes('url')) {
            const gradId = markerColor.replace('url(#', '').replace(')', '');
            const colors = {
              gradSalary: '#4f46e5',
              gradFreelance: '#10b981',
              gradExpenses: '#f43f5e',
              gradGst: '#06b6d4',
              gradPf: '#3b82f6',
              gradVpf: '#8b5cf6',
              gradTax: '#f43f5e',
              gradIncome: '#6366f1'
            };
            markerColor = colors[gradId] || '#6366f1';
          }
          return (
            <div className="premium-tooltip-item" key={index}>
              <div>
                <span className="premium-tooltip-marker" style={{ backgroundColor: markerColor }} />
                {item.name}:
              </div>
              <strong>{currency(item.value)}</strong>
            </div>
          );
        })}
      </div>
    );
  }
  return null;
};

async function api(path, options) {
  const response = await fetch(`${API}${path}`, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || response.statusText);
  }
  return response.json();
}

function App() {
  const initialSelectedUser = (() => {
    try {
      return sessionStorage.getItem('income-ledger-selected-user') || 'all';
    } catch {
      return 'all';
    }
  })();
  const [users, setUsers] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [years, setYears] = useState([]);
  const [selectedUser, setSelectedUser] = useState(initialSelectedUser);
  const [selectedYear, setSelectedYear] = useState('');
  const [dashboard, setDashboard] = useState(null);
  const [reviewDoc, setReviewDoc] = useState(null);
  const [status, setStatus] = useState('');
  const [uploadJobs, setUploadJobs] = useState([]);
  const [theme, setTheme] = useState(() => localStorage.getItem('income-ledger-theme') || 'light');
  const selectedUserRef = useRef(selectedUser);
  const selectedYearRef = useRef(selectedYear);

  async function refresh() {
    const [userData, docData, yearData] = await Promise.all([
      api('/users'),
      api('/documents'),
      api('/financial-years'),
    ]);
    setUsers(userData);
    setDocuments(docData);
    setYears(yearData);
    if (!selectedYearRef.current && yearData.length) setSelectedYear(yearData[0]);
    const year = selectedYearRef.current || yearData[0];
    let dashboardData = null;
    if (year) {
      dashboardData = await api(`/dashboard/${selectedUserRef.current}/${encodeURIComponent(year)}`);
      setDashboard(dashboardData);
    }
    return { users: userData, documents: docData, years: yearData, dashboard: dashboardData };
  }

  useEffect(() => {
    refresh().catch((error) => setStatus(error.message));
  }, []);

  useEffect(() => {
    selectedUserRef.current = selectedUser;
    try {
      sessionStorage.setItem('income-ledger-selected-user', selectedUser);
    } catch {}
  }, [selectedUser]);

  useEffect(() => {
    selectedYearRef.current = selectedYear;
  }, [selectedYear]);

  useEffect(() => {
    if (selectedUser === 'all') return;
    if (users.some((user) => String(user.id) === String(selectedUser))) return;
    setSelectedUser('all');
  }, [users, selectedUser]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('income-ledger-theme', theme);
  }, [theme]);

  useEffect(() => {
    if (!selectedYear) return;
    api(`/dashboard/${selectedUser}/${encodeURIComponent(selectedYear)}`)
      .then(setDashboard)
      .catch((error) => setStatus(error.message));
  }, [selectedUser, selectedYear]);

  const filteredDocuments = useMemo(() => documents.filter((doc) => {
    const extracted = doc.extracted || {};
    const docUser = extracted.user_id || doc.detected_user_id;
    const docDate = extracted.record_date;
    const docYear = financialYearForDate(docDate);
    const userMatches = selectedUser === 'all' || String(docUser || '') === String(selectedUser);
    const yearMatches = !selectedYear || docYear === selectedYear || (!docDate && doc.status !== 'confirmed');
    return userMatches && yearMatches;
  }), [documents, selectedUser, selectedYear]);
  const pendingDocs = useMemo(() => filteredDocuments.filter((doc) => doc.status !== 'confirmed'), [filteredDocuments]);

  async function handleUpload(event) {
    const files = Array.from(event.target.files || []);
    if (files.length === 0) return;
    event.target.value = '';
    const jobs = files.map((file, index) => ({ id: `${Date.now()}-${index}`, name: file.name, state: 'queued' }));
    setUploadJobs((current) => [...jobs, ...current].slice(0, 8));
    setStatus(`Queued ${files.length} PDF${files.length > 1 ? 's' : ''}. You can keep using the dashboard.`);
    void processUploadQueue(files, jobs);
  }

  function updateUploadJob(jobId, patch) {
    setUploadJobs((current) => current.map((job) => (job.id === jobId ? { ...job, ...patch } : job)));
  }

  async function processUploadQueue(files, jobs) {
    const uploadedDocs = [];
    try {
      for (const [index, file] of files.entries()) {
        const job = jobs[index];
        const form = new FormData();
        form.append('file', file);
        if (selectedUserRef.current !== 'all') form.append('user_id', selectedUserRef.current);
        setStatus(`Extracting ${index + 1} of ${files.length}: ${file.name}`);
        updateUploadJob(job.id, { state: 'extracting' });
        const uploaded = await api('/documents/upload', { method: 'POST', body: form });
        uploadedDocs.push(uploaded);
        await refresh();
        if (uploaded.status !== 'confirmed') {
          updateUploadJob(job.id, { state: 'needs review' });
          setReviewDoc(uploaded);
          setStatus(`${file.name} needs review. Continuing with the next PDF.`);
        } else {
          updateUploadJob(job.id, { state: 'saved' });
        }
      }
      setStatus(`${uploadedDocs.length} PDF${uploadedDocs.length > 1 ? 's' : ''} extracted and saved.`);
    } catch (error) {
      const activeJob = jobs.find((job) => job.state !== 'saved');
      if (activeJob) updateUploadJob(activeJob.id, { state: 'failed' });
      setStatus(error.message);
    }
  }

  async function exportCsv() {
    if (!dashboard) return;
    const rows = [
      ['Date', 'Period', 'Type', 'Employer / Company', 'Gross', 'Net', 'TDS', 'Other deductions', 'PF', 'VPF', 'GST'],
      ...dashboard.records.map((record) => [
        record.record_date,
        record.period_label,
        record.income_type,
        record.payer || '',
        record.gross_amount,
        record.net_amount,
        record.tds_amount,
        record.deductions_amount,
        record.pf_amount || 0,
        record.vpf_amount || 0,
        record.gst_amount || 0,
      ]),
    ];
    const csv = rows.map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `income-ledger-${selectedYear}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="shell container-fluid">
      <header className="topbar shadow-sm">
        <div>
          <h1>Income Ledger</h1>
          <p>Salary, freelance income, TDS, GST, and Indian FY tax estimates.</p>
        </div>
        <div className="actions">
          <label className="btn btn-primary" title="Upload PDFs">
            <Upload size={18} />
            Upload PDFs
            <input className="d-none" type="file" accept="application/pdf" multiple onChange={handleUpload} />
          </label>
          <button className="btn btn-outline-primary" title="Export CSV" onClick={exportCsv}>
            <FileDown size={18} />
            Export
          </button>
          <button className="btn btn-outline-secondary" type="button" title="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      {status && <div className="alert alert-info status">{status}</div>}
      {uploadJobs.length > 0 && <UploadQueue jobs={uploadJobs} />}

      <section className="toolbar shadow-sm">
        <select className="form-select" value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)}>
          <option value="all">All users</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>{user.name}</option>
          ))}
        </select>
        <select className="form-select" value={selectedYear} onChange={(event) => setSelectedYear(event.target.value)}>
          {years.map((year) => (
            <option key={year} value={year}>{year}</option>
          ))}
        </select>
        <NewUserForm onCreated={refresh} />
        <ExpenseForm users={users} selectedUser={selectedUser} onCreated={refresh} />
      </section>

      <Dashboard dashboard={dashboard} />

      <section className="contentGrid">
        <DocumentPanel documents={filteredDocuments} pendingDocs={pendingDocs} onReview={setReviewDoc} onDeleted={refresh} />
        <RecordsPanel records={dashboard?.records || []} onDeleted={refresh} />
        <ExpensesPanel expenses={dashboard?.expenses || []} users={users} onDeleted={refresh} />
      </section>

      {reviewDoc && (
        <ReviewModal
          key={reviewDoc.id}
          document={reviewDoc}
          users={users}
          onClose={() => setReviewDoc(null)}
          onSaved={async () => {
            const refreshed = await refresh();
            const nextPending = refreshed.documents.find((doc) => doc.status !== 'confirmed' && doc.id !== reviewDoc.id);
            setReviewDoc(nextPending || null);
          }}
        />
      )}
    </main>
  );
}

function UploadQueue({ jobs }) {
  return (
    <section className="uploadQueue shadow-sm">
      {jobs.map((job) => (
        <span key={job.id} className={`uploadJob ${job.state.replace(' ', '-')}`}>
          {job.name}: {job.state}
        </span>
      ))}
    </section>
  );
}

function NewUserForm({ onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', pan: '', aliases: '', profile_hints: '' });

  async function submit(event) {
    event.preventDefault();
    await api('/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    setForm({ name: '', pan: '', aliases: '', profile_hints: '' });
    setOpen(false);
    onCreated();
  }

  if (!open) {
    return <button className="btn btn-dark" onClick={() => setOpen(true)}><UserPlus size={16} /> User</button>;
  }

  return (
    <form className="inlineForm" onSubmit={submit}>
      <input className="form-control" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
      <input className="form-control" placeholder="PAN" value={form.pan} onChange={(e) => setForm({ ...form, pan: e.target.value })} />
      <input className="form-control" placeholder="Aliases" value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} />
      <input className="form-control" placeholder="Employer/client hints" value={form.profile_hints} onChange={(e) => setForm({ ...form, profile_hints: e.target.value })} />
      <button className="btn btn-success" type="submit"><Check size={16} /></button>
    </form>
  );
}

function ExpenseForm({ users, selectedUser, onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ user_id: selectedUser === 'all' ? '' : selectedUser, expense_date: '', category: '', amount: '', gst_amount: '', notes: '' });

  useEffect(() => {
    if (!open && selectedUser !== 'all') setForm((current) => ({ ...current, user_id: selectedUser }));
  }, [open, selectedUser]);

  async function submit(event) {
    event.preventDefault();
    await api('/expenses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, amount: Number(form.amount), gst_amount: Number(form.gst_amount || 0) }),
    });
    setForm({ user_id: selectedUser === 'all' ? '' : selectedUser, expense_date: '', category: '', amount: '', gst_amount: '', notes: '' });
    setOpen(false);
    await onCreated();
  }

  if (!open) {
    return <button className="btn btn-dark" onClick={() => setOpen(true)}><Plus size={16} /> Expense</button>;
  }

  return (
    <form className="inlineForm" onSubmit={submit}>
      <select className="form-select" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} required>
        <option value="">User</option>
        {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
      </select>
      <input className="form-control" type="date" value={form.expense_date} onChange={(e) => setForm({ ...form, expense_date: e.target.value })} required />
      <input className="form-control" placeholder="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required />
      <input className="form-control" type="number" placeholder="Amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required />
      <input className="form-control" type="number" placeholder="GST claim" value={form.gst_amount} onChange={(e) => setForm({ ...form, gst_amount: e.target.value })} />
      <input className="form-control" placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      <button className="btn btn-success" type="submit"><Check size={16} /></button>
    </form>
  );
}

function Dashboard({ dashboard }) {
  if (!dashboard) {
    return <section className="empty">No dashboard data yet.</section>;
  }
  const { summary, tax } = dashboard;
  return (
    <>
      <section className="metricGrid">
        <Metric icon={<IndianRupee />} label="Salary income" value={currency(summary.salary_income)} />
        <Metric icon={<IndianRupee />} label="Freelance income" value={currency(summary.freelance_income)} />
        <Metric icon={<BarChart3 />} label="Current total income" value={currency(summary.total_income)} />
        <Metric icon={<IndianRupee />} label="Total expenses" value={currency(summary.total_expenses || summary.freelance_expenses)} />
        <Metric icon={<IndianRupee />} label="GST input claims" value={currency(summary.expense_gst_claims)} />
        <Metric icon={<IndianRupee />} label="Salary standard deduction" value={currency(summary.salary_standard_deduction)} />
        <Metric icon={<BarChart3 />} label="Taxable income" value={currency(summary.taxable_income)} />
        <Metric icon={<IndianRupee />} label={`Estimated tax (${tax.regime})`} value={currency(tax.total_tax)} />
        <Metric icon={<Calculator />} label="Projected annual income" value={currency(tax.predicted_annual_income)} />
        <Metric icon={<Calculator />} label="Projected annual tax" value={currency(tax.predicted_total_tax)} />
        <Metric icon={<Calculator />} label="Quarterly advance tax" value={currency(tax.quarterly_advance_tax?.per_quarter)} />
        <Metric icon={<IndianRupee />} label="TDS paid" value={currency(tax.tds_paid)} />
        <Metric icon={<IndianRupee />} label="PF" value={currency(summary.pf_total)} />
        <Metric icon={<IndianRupee />} label="VPF" value={currency(summary.vpf_total)} />
        <Metric icon={<AlertTriangle />} label="Remaining tax" value={currency(tax.remaining_tax)} />
      </section>

      <section className="chartGrid">
        <div className="panel">
          <h2>Income trend</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={dashboard.monthly} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="gradSalary" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.85}/>
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0.2}/>
                </linearGradient>
                <linearGradient id="gradFreelance" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.85}/>
                  <stop offset="95%" stopColor="#059669" stopOpacity={0.2}/>
                </linearGradient>
                <linearGradient id="gradExpenses" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f97316" stopOpacity={0.85}/>
                  <stop offset="95%" stopColor="#ea580c" stopOpacity={0.2}/>
                </linearGradient>
                <linearGradient id="gradGst" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.85}/>
                  <stop offset="95%" stopColor="#0891b2" stopOpacity={0.2}/>
                </linearGradient>
                <linearGradient id="gradPf" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.85}/>
                  <stop offset="95%" stopColor="#2563eb" stopOpacity={0.2}/>
                </linearGradient>
                <linearGradient id="gradVpf" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a855f7" stopOpacity={0.85}/>
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.2}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="5 5" vertical={false} />
              <XAxis dataKey="month" tickLine={false} />
              <YAxis tickLine={false} axisLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Legend iconType="circle" iconSize={8} />
              <Bar name="Salary" dataKey="salary" fill="url(#gradSalary)" radius={[5, 5, 0, 0]} />
              <Bar name="Freelance" dataKey="freelance" fill="url(#gradFreelance)" radius={[5, 5, 0, 0]} />
              <Bar name="Expenses" dataKey="expenses" fill="url(#gradExpenses)" radius={[5, 5, 0, 0]} />
              <Bar name="GST" dataKey="expense_gst" fill="url(#gradGst)" radius={[5, 5, 0, 0]} />
              <Bar name="PF" dataKey="pf" fill="url(#gradPf)" radius={[5, 5, 0, 0]} />
              <Bar name="VPF" dataKey="vpf" fill="url(#gradVpf)" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="panel">
          <h2>Tax prediction <span>{tax.assessment_year}</span></h2>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={[
              { name: 'Current', tax: tax.total_tax, income: summary.taxable_income },
              { name: 'Predicted year end', tax: tax.predicted_total_tax, income: tax.predicted_taxable_income },
            ]} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="gradIncome" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.9}/>
                  <stop offset="95%" stopColor="#4f46e5" stopOpacity={0.3}/>
                </linearGradient>
                <linearGradient id="gradTax" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.9}/>
                  <stop offset="95%" stopColor="#e11d48" stopOpacity={0.3}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="5 5" vertical={false} />
              <XAxis dataKey="name" tickLine={false} />
              <YAxis tickLine={false} axisLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Legend iconType="circle" iconSize={8} />
              <Line name="Taxable Income" type="monotone" dataKey="income" stroke="url(#gradIncome)" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
              <Line name="Estimated Tax" type="monotone" dataKey="tax" stroke="url(#gradTax)" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
          <TaxComparison tax={tax} />
          <AdvanceTaxSchedule tax={tax} />
        </div>
      </section>
    </>
  );
}

function TaxComparison({ tax }) {
  const rows = Object.values(tax.options || {});
  if (rows.length === 0) return null;
  return (
    <div className="taxCompare">
      {rows.map((row) => (
        <div key={row.regime}>
          <span>{row.regime === 'old' ? 'Old regime' : 'New regime'}{row.is_default_regime ? ' (default)' : ''}</span>
          <strong>{currency(row.total_tax)}</strong>
          <small>Taxable {currency(row.taxable_income)} · Deduction {currency(row.salary_standard_deduction)}</small>
        </div>
      ))}
    </div>
  );
}

function AdvanceTaxSchedule({ tax }) {
  const rows = tax.quarterly_advance_tax?.schedule || [];
  if (rows.length === 0) return null;
  return (
    <div className="advanceTax">
      <h3>Equal quarterly advance tax</h3>
      <div>
        {rows.map((row) => (
          <span key={row.quarter}>Q{row.quarter} {currency(row.amount)}</span>
        ))}
      </div>
    </div>
  );
}

function Metric({ icon, label, value }) {
  return (
    <div className="metric">
      <div className="metricIcon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DocumentPanel({ documents, pendingDocs, onReview, onDeleted }) {
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  function requestDelete(event, document) {
    event.stopPropagation();
    setDeleteError('');
    setDeleteTarget(document);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setIsDeleting(true);
    setDeleteError('');
    try {
      await api(`/documents/${deleteTarget.id}`, { method: 'DELETE' });
      setDeleteTarget(null);
      await onDeleted();
    } catch (error) {
      setDeleteError(error.message);
    } finally {
      setIsDeleting(false);
    }
  }

  function closeDeleteModal() {
    if (isDeleting) return;
    setDeleteTarget(null);
    setDeleteError('');
  }

  function openForReview(event, document) {
    if (event.target.closest('a, button, .rowActions')) return;
    onReview(document);
  }

  function handleRowKeyDown(event, document) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onReview(document);
  }

  return (
    <section className="panel shadow-sm">
      <h2><FileText size={18} /> Documents <span className="badge text-bg-warning">{pendingDocs.length} pending</span></h2>
      <div className="list">
        {documents.map((doc) => (
          <div className="documentRow" key={doc.id} role="button" tabIndex={0} onClick={(event) => openForReview(event, doc)} onKeyDown={(event) => handleRowKeyDown(event, doc)}>
            <div>
              <strong>{doc.original_name}</strong>
              <span>{doc.document_type} · {doc.status} · confidence {Math.round((doc.confidence || 0) * 100)}%</span>
              <a href={`${API}/documents/${doc.id}/file`} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                Open source PDF
              </a>
            </div>
            <div className="rowActions" onClick={(event) => event.stopPropagation()}>
              {doc.warnings?.length > 0 && <AlertTriangle size={16} className="text-warning" />}
              <button className="btn btn-sm btn-outline-danger" type="button" title="Delete document" onClick={(event) => requestDelete(event, doc)}>
                <Trash2 size={15} />
              </button>
            </div>
          </div>
        ))}
        {documents.length === 0 && <p className="muted">Upload a PDF to begin.</p>}
      </div>
      {deleteTarget && (
        <div className="modalBackdrop" onClick={closeDeleteModal}>
          <div className="modal deleteConfirmModal shadow-lg" role="dialog" aria-modal="true" aria-labelledby="delete-document-title" onClick={(event) => event.stopPropagation()}>
            <h2 id="delete-document-title"><Trash2 size={18} /> Delete document?</h2>
            <p>This removes the PDF and any linked income or expense data from the dashboard.</p>
            <div className="deleteSummary">
              <strong>{deleteTarget.original_name}</strong>
              <span>{deleteTarget.document_type} | {deleteTarget.status}</span>
            </div>
            {deleteError && <div className="alert alert-danger">{deleteError}</div>}
            <div className="modalActions">
              <button className="btn btn-outline-secondary" type="button" onClick={closeDeleteModal} disabled={isDeleting}>Cancel</button>
              <button className="btn btn-danger" type="button" onClick={confirmDelete} disabled={isDeleting}>
                <Trash2 size={16} /> {isDeleting ? 'Deleting...' : 'Delete document'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function RecordsPanel({ records, onDeleted }) {
  async function deleteRecord(record) {
    if (!window.confirm(`Delete ${record.income_type} record for ${record.record_date}?`)) return;
    await api(`/records/${record.id}`, { method: 'DELETE' });
    onDeleted();
  }

  return (
    <section className="panel shadow-sm">
      <h2>Confirmed records</h2>
      <div className="tableWrap">
        <table className="table table-hover align-middle">
          <thead>
            <tr>
              <th>Date</th>
              <th>Type</th>
              <th>Employer / Company</th>
              <th>Gross</th>
              <th>Net</th>
              <th>TDS</th>
              <th>Other deductions</th>
              <th>PF</th>
              <th>VPF</th>
              <th>GST</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id}>
                <td>{record.record_date}</td>
                <td>{record.income_type}</td>
                <td>
                  {record.payer}
                  {record.validation_warnings?.length > 0 && (
                    <span className="recordWarning">{record.validation_warnings.join(' ')}</span>
                  )}
                </td>
                <td>{currency(record.gross_amount)}</td>
                <td>{currency(record.net_amount)}</td>
                <td>{currency(record.tds_amount)}</td>
                <td>{currency(record.deductions_amount)}</td>
                <td>{currency(record.pf_amount || 0)}</td>
                <td>{currency(record.vpf_amount || 0)}</td>
                <td>{currency(record.gst_amount || 0)}</td>
                <td>
                  <button className="btn btn-sm btn-outline-danger" type="button" title="Delete record" onClick={() => deleteRecord(record)}>
                    <Trash2 size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ExpensesPanel({ expenses, users, onDeleted }) {
  const userNames = useMemo(() => Object.fromEntries(users.map((user) => [String(user.id), user.name])), [users]);

  async function deleteExpense(expense) {
    if (!window.confirm(`Delete expense ${currency(expense.amount)} for ${expense.expense_date}?`)) return;
    await api(`/expenses/${expense.id}`, { method: 'DELETE' });
    await onDeleted();
  }

  return (
    <section className="panel shadow-sm expensesPanel">
      <h2>Expenses <span className="badge text-bg-secondary">{expenses.length}</span></h2>
      <div className="tableWrap">
        <table className="table table-hover align-middle">
          <thead>
            <tr>
              <th>Date</th>
              <th>User</th>
              <th>Category</th>
              <th>Amount</th>
              <th>GST claim</th>
              <th>Notes</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {expenses.map((expense) => (
              <tr key={expense.id}>
                <td>{expense.expense_date}</td>
                <td>{userNames[String(expense.user_id)] || expense.user_id}</td>
                <td>{expense.category}</td>
                <td>{currency(expense.amount)}</td>
                <td>{currency(expense.gst_amount || 0)}</td>
                <td>{expense.notes}</td>
                <td>
                  <button className="btn btn-sm btn-outline-danger" type="button" title="Delete expense" onClick={() => deleteExpense(expense)}>
                    <Trash2 size={15} />
                  </button>
                </td>
              </tr>
            ))}
            {expenses.length === 0 && (
              <tr>
                <td colSpan="7" className="muted">No expenses recorded for this selection.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ReviewModal({ document, users, onClose, onSaved }) {
  const extracted = document.extracted || {};
  const extractedType = extracted.document_type === 'salary' ? 'salary' : 'freelance_invoice';
  const initialGross = Number(extracted.gross_amount || 0);
  const initialNet = Number(extracted.net_amount || 0);
  const initialTds = Number(extracted.tds_amount || 0);
  const initialGst = Number(extracted.gst_amount || 0);
  const [form, setForm] = useState({
    user_id: document.detected_user_id || '',
    income_type: extractedType,
    record_date: extracted.record_date || '',
    payer: extracted.payer || '',
    gross_amount: initialGross,
    net_amount: initialNet,
    tds_amount: extractedType === 'freelance_invoice' && initialTds === 0 ? roundMoney(initialGross * 0.1) : initialTds,
    deductions_amount: extracted.deductions_amount || 0,
    pf_amount: extractedType === 'salary' ? extracted.pf_amount || 0 : 0,
    vpf_amount: extractedType === 'salary' ? extracted.vpf_amount || 0 : 0,
    gst_amount: extractedType === 'freelance_invoice' && initialGst === 0 ? roundMoney(Math.max(0, initialNet - initialGross)) : initialGst,
  });
  const isFreelance = form.income_type === 'freelance_invoice';

  function applyIncomeType(nextType) {
    setForm((current) => ({
      ...current,
      income_type: nextType,
      tds_amount: nextType === 'freelance_invoice' && Number(current.tds_amount || 0) === 0
        ? roundMoney(Number(current.gross_amount || 0) * 0.1)
        : current.tds_amount,
      gst_amount: nextType === 'freelance_invoice'
        ? roundMoney(Math.max(0, Number(current.net_amount || 0) - Number(current.gross_amount || 0)))
        : 0,
      pf_amount: nextType === 'salary' ? current.pf_amount : 0,
      vpf_amount: nextType === 'salary' ? current.vpf_amount : 0,
    }));
  }

  function updateMoneyField(key, value) {
    const numericValue = Number(value);
    setForm((current) => {
      const next = { ...current, [key]: numericValue };
      if (next.income_type === 'freelance_invoice') {
        const gross = Number(next.gross_amount || 0);
        const net = Number(next.net_amount || 0);
        if (key === 'gross_amount' || Number(current.tds_amount || 0) === 0) {
          next.tds_amount = roundMoney(gross * 0.1);
        }
        if (key === 'gross_amount' || key === 'net_amount') {
          next.gst_amount = roundMoney(Math.max(0, net - gross));
        }
      }
      return next;
    });
  }

  async function submit(event) {
    event.preventDefault();
    await api(`/extractions/${document.id}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, user_id: Number(form.user_id) }),
    });
    onSaved();
  }

  return (
    <div className="modalBackdrop">
      <form className="modal shadow-lg" onSubmit={submit}>
        <h2>Review extraction</h2>
        <p>{document.original_name}</p>
        <div className="reviewGrid">
          <label>User<select className="form-select" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} required>
            <option value="">Select user</option>
            {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
          </select></label>
          <label>Type<select className="form-select" value={form.income_type} onChange={(e) => applyIncomeType(e.target.value)}>
            <option value="salary">Salary</option>
            <option value="freelance_invoice">Freelance invoice</option>
          </select></label>
          <label>Date<input className="form-control" type="date" value={form.record_date} onChange={(e) => setForm({ ...form, record_date: e.target.value })} /></label>
          <label>Employer / Company<input className="form-control" value={form.payer || ''} onChange={(e) => setForm({ ...form, payer: e.target.value })} /></label>
          <label>Gross<input className="form-control" type="number" value={form.gross_amount} onChange={(e) => updateMoneyField('gross_amount', e.target.value)} /></label>
          <label>Net<input className="form-control" type="number" value={form.net_amount} onChange={(e) => updateMoneyField('net_amount', e.target.value)} /></label>
          <label>TDS<input className="form-control" type="number" value={form.tds_amount} onChange={(e) => updateMoneyField('tds_amount', e.target.value)} /></label>
          {isFreelance ? (
            <label>GST<input className="form-control" type="number" value={form.gst_amount} onChange={(e) => updateMoneyField('gst_amount', e.target.value)} /></label>
          ) : (
            <>
              <label>Other deductions<input className="form-control" type="number" value={form.deductions_amount} onChange={(e) => updateMoneyField('deductions_amount', e.target.value)} /></label>
              <label>PF<input className="form-control" type="number" value={form.pf_amount} onChange={(e) => updateMoneyField('pf_amount', e.target.value)} /></label>
              <label>VPF<input className="form-control" type="number" value={form.vpf_amount} onChange={(e) => updateMoneyField('vpf_amount', e.target.value)} /></label>
            </>
          )}
        </div>
        {extracted.warnings?.length > 0 && (
          <div className="warnings">
            {extracted.warnings.map((warning) => <span key={warning}>{warning}</span>)}
          </div>
        )}
        <div className="modalActions">
          <button className="btn btn-outline-secondary" type="button" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" type="submit"><Check size={16} /> Save record</button>
        </div>
      </form>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
