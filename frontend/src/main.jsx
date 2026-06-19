import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertTriangle,
  Activity,
  BarChart3,
  Calculator,
  Check,
  ClipboardCheck,
  Edit,
  FileDown,
  FileText,
  IndianRupee,
  KeyRound,
  Link,
  ListChecks,
  Moon,
  Plus,
  RefreshCw,
  MessageSquare,
  Settings as SettingsIcon,
  Sun,
  Trash2,
  Upload,
  UserPlus,
  X,
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
const AUTH_TOKEN_KEY = 'income-ledger-auth-token';

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

const TAX_DOCUMENT_TYPES = new Set(['form16_part_a', 'form16_part_b', 'form26as', 'tax_statement_unknown']);

function isTaxDocumentType(type) {
  return TAX_DOCUMENT_TYPES.has(type || '');
}

function taxDocumentLabel(type) {
  const labels = {
    form16_part_a: 'Form 16 Part A',
    form16_part_b: 'Form 16 Part B',
    form26as: 'Form 26AS',
    tax_statement_unknown: 'Tax statement',
  };
  return labels[type] || type || 'Tax document';
}

function formatDisplayDate(value) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString();
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
              gradIncome: '#6366f1',
              gradOldRegime: '#8b5cf6',
              gradNewRegime: '#10b981'
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

function getAuthToken() {
  try {
    return sessionStorage.getItem(AUTH_TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

function setAuthToken(token) {
  try {
    sessionStorage.setItem(AUTH_TOKEN_KEY, token);
  } catch {}
}

function clearAuthToken() {
  try {
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {}
}

async function api(path, options = {}) {
  const { skipAuth, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers || {});
  if (!skipAuth) {
    const token = getAuthToken();
    if (token) headers.set('X-Income-Ledger-Token', token);
  }
  const response = await fetch(`${API}${path}`, { ...fetchOptions, headers });
  if (!response.ok) {
    const body = await response.text();
    let message = body || response.statusText;
    try {
      const parsed = JSON.parse(body);
      message = parsed.detail || message;
    } catch {}
    if (response.status === 401 && !skipAuth) {
      clearAuthToken();
      window.dispatchEvent(new CustomEvent('income-ledger-auth-required'));
    }
    throw new Error(message || response.statusText);
  }
  return response.json();
}

async function apiBlob(path, options = {}) {
  const { skipAuth, ...fetchOptions } = options;
  const headers = new Headers();
  if (!skipAuth) {
    const token = getAuthToken();
    if (token) headers.set('X-Income-Ledger-Token', token);
  }
  const response = await fetch(`${API}${path}`, { ...fetchOptions, headers });
  if (!response.ok) {
    if (response.status === 401) {
      clearAuthToken();
      window.dispatchEvent(new CustomEvent('income-ledger-auth-required'));
    }
    const body = await response.text();
    let message = body || response.statusText;
    try {
      const parsed = JSON.parse(body);
      message = parsed.detail || message;
    } catch {}
    throw new Error(message || response.statusText);
  }
  return response.blob();
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function getRealWarnings(warnings) {
  if (!warnings) return [];
  const warningsArray = Array.isArray(warnings)
    ? warnings
    : (typeof warnings === 'string'
        ? (() => {
            try {
              return JSON.parse(warnings);
            } catch {
              return [warnings];
            }
          })()
        : []);
  return warningsArray.filter((w) => {
    if (typeof w !== 'string') return false;
    const lowered = w.toLowerCase();
    return !(
      lowered.includes("used model") ||
      lowered.includes("trying local ai") ||
      lowered.includes("successfully extracted using") ||
      lowered.includes("extracted using ocr fallback") ||
      lowered.includes("no embedded pdf text found")
    );
  });
}

function summarizeStageFailure(response, error) {
  if (response?.detail) return response.detail;
  if (response?.warnings?.length) return response.warnings.slice(-2).join(' ');
  if (response?.reason) return response.reason;
  if (error?.message) return error.message;
  return 'No detailed error was returned.';
}

function aiAdvisorConversationKey(userId, financialYear) {
  return `${userId || 'all'}:${financialYear || 'none'}`;
}

function aiAdvisorSessionStorageKey(userId, financialYear) {
  return `income-ledger-ai-advisor-session:${aiAdvisorConversationKey(userId, financialYear)}`;
}

function aiAdvisorTokenStorageKey(userId, financialYear) {
  return `income-ledger-ai-advisor-tokens:${userId || 'all'}:${financialYear || 'none'}`;
}

function normalizeAiAdvisorMessages(messages) {
  if (!Array.isArray(messages)) return [];
  return messages
    .filter((message) => message && typeof message.content === 'string')
    .map((message) => ({
      role: message.role === 'user' ? 'user' : 'assistant',
      content: message.content,
    }));
}

function readAiAdvisorSession(userId, financialYear) {
  const empty = { error: '', busy: '', analysis: '', messages: [], input: '', tokenCount: 0 };
  try {
    const saved = JSON.parse(localStorage.getItem(aiAdvisorSessionStorageKey(userId, financialYear)) || '{}');
    const savedTokenCount = localStorage.getItem(aiAdvisorTokenStorageKey(userId, financialYear));
    return {
      ...empty,
      analysis: typeof saved.analysis === 'string' ? saved.analysis : '',
      messages: normalizeAiAdvisorMessages(saved.messages),
      input: typeof saved.input === 'string' ? saved.input : '',
      tokenCount: Math.max(0, Number(saved.tokenCount ?? savedTokenCount ?? 0) || 0),
    };
  } catch {
    return empty;
  }
}

function writeAiAdvisorSession(userId, financialYear, session) {
  try {
    const tokenCount = Math.max(0, Number(session.tokenCount || 0));
    localStorage.setItem(
      aiAdvisorSessionStorageKey(userId, financialYear),
      JSON.stringify({
        analysis: session.analysis || '',
        messages: normalizeAiAdvisorMessages(session.messages),
        input: session.input || '',
        tokenCount,
      }),
    );
    localStorage.setItem(aiAdvisorTokenStorageKey(userId, financialYear), String(tokenCount));
  } catch {}
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
  const [reviewQueue, setReviewQueue] = useState([]);
  const [editUser, setEditUser] = useState(null);
  const [newIncomeOpen, setNewIncomeOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [deleteTargetDoc, setDeleteTargetDoc] = useState(null);
  const [isDeletingDoc, setIsDeletingDoc] = useState(false);
  const [deleteDocError, setDeleteDocError] = useState('');
  const [activeView, setActiveView] = useState('dashboard');
  const [dashboardMode, setDashboardMode] = useState('summary');
  const [drilldown, setDrilldown] = useState(null);
  const [dataVersion, setDataVersion] = useState(0);
  const [authChecked, setAuthChecked] = useState(false);
  const [setupRequired, setSetupRequired] = useState(false);
  const [unlocked, setUnlocked] = useState(() => Boolean(getAuthToken()));
  const [status, setStatus] = useState(() => {
    try {
      return sessionStorage.getItem('income-ledger-status') || '';
    } catch {
      return '';
    }
  });
  const [uploadJobs, setUploadJobs] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem('income-ledger-upload-jobs')) || [];
    } catch {
      return [];
    }
  });
  const [theme, setTheme] = useState(() => localStorage.getItem('income-ledger-theme') || 'light');
  const [aiAdvisorSessions, setAiAdvisorSessions] = useState({});
  const selectedUserRef = useRef(selectedUser);
  const selectedYearRef = useRef(selectedYear);
  const activeAiAdvisorUser = selectedUser || 'all';
  const activeAiAdvisorYear = selectedYear || '';
  const activeAiAdvisorKey = aiAdvisorConversationKey(activeAiAdvisorUser, activeAiAdvisorYear);
  const activeAiAdvisorState = aiAdvisorSessions[activeAiAdvisorKey] || readAiAdvisorSession(activeAiAdvisorUser, activeAiAdvisorYear);

  function updateAiAdvisorSession(userId, financialYear, updater) {
    const key = aiAdvisorConversationKey(userId, financialYear);
    setAiAdvisorSessions((current) => {
      const previous = current[key] || readAiAdvisorSession(userId, financialYear);
      const patch = typeof updater === 'function' ? updater(previous) : updater;
      const next = { ...previous, ...patch };
      writeAiAdvisorSession(userId, financialYear, next);
      return { ...current, [key]: next };
    });
  }

  function setAiAdvisorInput(value) {
    updateAiAdvisorSession(activeAiAdvisorUser, activeAiAdvisorYear, { input: value });
  }

  function clearAiAdvisorTokenCount() {
    updateAiAdvisorSession(activeAiAdvisorUser, activeAiAdvisorYear, { tokenCount: 0 });
  }

  async function runAiAdvisorAnalysis() {
    const userId = activeAiAdvisorUser;
    const financialYear = activeAiAdvisorYear;
    if (!financialYear) return;
    updateAiAdvisorSession(userId, financialYear, { busy: 'analysis', error: '' });
    try {
      const response = await api(`/tax-planning/${userId}/${encodeURIComponent(financialYear)}/ai-analysis`, { method: 'POST' });
      updateAiAdvisorSession(userId, financialYear, (previous) => {
        const tokenCount = Math.max(0, Number(previous.tokenCount || 0) + Number(response.total_tokens || 0));
        return {
          busy: '',
          error: '',
          analysis: response.analysis || '',
          messages: response.analysis ? [{ role: 'assistant', content: response.analysis }] : previous.messages,
          tokenCount,
        };
      });
    } catch (analysisError) {
      updateAiAdvisorSession(userId, financialYear, { busy: '', error: analysisError.message });
    }
  }

  async function sendAiAdvisorMessage() {
    const userId = activeAiAdvisorUser;
    const financialYear = activeAiAdvisorYear;
    if (!financialYear) return;
    const key = aiAdvisorConversationKey(userId, financialYear);
    const previous = aiAdvisorSessions[key] || readAiAdvisorSession(userId, financialYear);
    const content = previous.input.trim();
    if (!content || previous.busy) return;
    const requestMessages = [...previous.messages, { role: 'user', content }];
    const requestTokenCount = previous.tokenCount;
    updateAiAdvisorSession(userId, financialYear, {
      busy: 'chat',
      error: '',
      input: '',
      messages: requestMessages,
    });
    try {
      const response = await api(`/tax-planning/${userId}/${encodeURIComponent(financialYear)}/ai-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: requestMessages, total_tokens: requestTokenCount }),
      });
      updateAiAdvisorSession(userId, financialYear, {
        busy: '',
        error: '',
        messages: [...requestMessages, { role: 'assistant', content: response.message || '' }],
        tokenCount: Math.max(0, Number(response.total_tokens || requestTokenCount)),
      });
    } catch (chatError) {
      updateAiAdvisorSession(userId, financialYear, {
        busy: '',
        error: chatError.message,
        messages: requestMessages,
      });
    }
  }

  useEffect(() => {
    function lockApp() {
      setUnlocked(false);
      setDashboard(null);
      setDocuments([]);
      setUsers([]);
      setYears([]);
    }
    window.addEventListener('income-ledger-auth-required', lockApp);
    return () => window.removeEventListener('income-ledger-auth-required', lockApp);
  }, []);

  useEffect(() => {
    api('/auth/status', { skipAuth: true })
      .then((data) => {
        setSetupRequired(Boolean(data.setup_required));
        setUnlocked(Boolean(getAuthToken()) && !data.setup_required);
      })
      .catch((error) => setStatus(error.message))
      .finally(() => setAuthChecked(true));
  }, []);

  async function refresh() {
    const [userData, docData] = await Promise.all([
      api('/users'),
      api('/documents'),
    ]);
    setUsers(userData);
    setDocuments(docData);

    const yearData = await api(`/financial-years?user_id=${selectedUserRef.current}`);
    const finalYears = yearData.length ? yearData : [financialYearForDate(new Date())];
    setYears(finalYears);

    let year = selectedYearRef.current;
    if (!finalYears.includes(year)) {
      year = finalYears[0];
      setSelectedYear(year);
    }

    let dashboardData = null;
    if (year) {
      dashboardData = await api(`/dashboard/${selectedUserRef.current}/${encodeURIComponent(year)}`);
      setDashboard(dashboardData);
    }

    setUploadJobs((currentJobs) => {
      let loadedJobs = currentJobs;
      if (loadedJobs.length === 0) {
        try {
          loadedJobs = JSON.parse(sessionStorage.getItem('income-ledger-upload-jobs')) || [];
        } catch {
          loadedJobs = [];
        }
      }
      if (loadedJobs.length === 0) return [];

      const updated = loadedJobs.map((job) => {
        if (job.state === 'queued' || job.state === 'extracting' || job.state === 'needs review') {
          const matchingDoc = docData.find((d) => d.original_name === job.name);
          if (matchingDoc) {
            const nextState = matchingDoc.status === 'confirmed' ? 'saved' : 'needs review';
            if (nextState === 'saved' && job.state !== 'saved') {
              setTimeout(() => {
                setUploadJobs((curr) => curr.filter((j) => j.id !== job.id));
              }, 5000);
            }
            return {
              ...job,
              state: nextState
            };
          } else {
            return {
              ...job,
              state: 'failed'
            };
          }
        }
        return job;
      });
      return updated;
    });

    setDataVersion((version) => version + 1);
    return { users: userData, documents: docData, years: finalYears, dashboard: dashboardData };
  }

  useEffect(() => {
    if (!unlocked) return;
    refresh().catch((error) => setStatus(error.message));

    // Clear initial 'saved' jobs loaded from sessionStorage after 5 seconds
    try {
      const initialJobs = JSON.parse(sessionStorage.getItem('income-ledger-upload-jobs')) || [];
      const savedJobs = initialJobs.filter((job) => job.state === 'saved');
      savedJobs.forEach((job) => {
        setTimeout(() => {
          setUploadJobs((curr) => curr.filter((j) => j.id !== job.id));
        }, 5000);
      });
    } catch {}
  }, [unlocked]);

  useEffect(() => {
    if (reviewDoc) {
      const stillExists = documents.some((d) => d.id === reviewDoc.id);
      if (!stillExists) {
        setReviewDoc(null);
      }
    }
  }, [documents, reviewDoc]);

  useEffect(() => {
    try {
      if (status) {
        sessionStorage.setItem('income-ledger-status', status);
      } else {
        sessionStorage.removeItem('income-ledger-status');
      }
    } catch {}
  }, [status]);

  useEffect(() => {
    try {
      sessionStorage.setItem('income-ledger-upload-jobs', JSON.stringify(uploadJobs));
    } catch {}
  }, [uploadJobs]);

  useEffect(() => {
    if (!unlocked) return;
    selectedUserRef.current = selectedUser;
    try {
      sessionStorage.setItem('income-ledger-selected-user', selectedUser);
    } catch {}

    api(`/financial-years?user_id=${selectedUser}`)
      .then((yearData) => {
        const finalYears = yearData.length ? yearData : [financialYearForDate(new Date())];
        setYears(finalYears);
        
        setSelectedYear((currentYear) => {
          if (finalYears.includes(currentYear)) {
            return currentYear;
          }
          return finalYears[0];
        });
      })
      .catch((error) => setStatus(error.message));
  }, [selectedUser, unlocked]);

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
    if (!unlocked || !selectedYear) return;
    api(`/dashboard/${selectedUser}/${encodeURIComponent(selectedYear)}`)
      .then(setDashboard)
      .catch((error) => setStatus(error.message));
  }, [selectedUser, selectedYear, unlocked]);

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
    if (patch.state === 'saved') {
      setTimeout(() => {
        setUploadJobs((current) => current.filter((job) => job.id !== jobId));
      }, 5000);
    }
  }

  async function processUploadQueue(files, jobs) {
    const uploadedDocs = [];
    try {
      for (const [index, file] of files.entries()) {
        const job = jobs[index];
        const form = new FormData();
        form.append('file', file);
        form.append('stage', 'local');
        if (selectedUserRef.current !== 'all') form.append('user_id', selectedUserRef.current);
        
        setStatus(`Extracting ${index + 1} of ${files.length}: ${file.name}`);
        updateUploadJob(job.id, { state: 'extracting' });
        
        let doc = null;
        let localSuccess = false;
        let isScanned = false;
        let isDuplicate = false;
        let isTaxStatement = false;
        
        // Stage 1: Try Local Python Parser
        try {
          const response1 = await api('/documents/upload', { method: 'POST', body: form });
          doc = response1.document || response1;
          localSuccess = response1.success !== false;
          isScanned = response1.is_scanned === true;
          isDuplicate = response1.duplicate === true;
          isTaxStatement = response1.tax_statement === true || isTaxDocumentType(doc.document_type);
        } catch (error) {
          console.error("Local Python stage failed:", error);
          localSuccess = false;
          isScanned = true;
        }
        
        if (!localSuccess) {
          if (isScanned) {
            setStatus("Scanned image PDF detected. Please manually check and fill details.");
            await new Promise(resolve => setTimeout(resolve, 2000));
          } else {
            setStatus("Local Python extraction needs help. Moving to Local Hosted LM Studio AI.");
            await new Promise(resolve => setTimeout(resolve, 2000));

            let localAiSuccess = false;
            let localAiFailure = '';
            // Stage 2: Try Local Hosted AI (LM Studio)
            try {
              if (doc && doc.id) {
                const form2 = new FormData();
                form2.append('ai_provider', 'local');
                if (selectedUserRef.current !== 'all') form2.append('user_id', selectedUserRef.current);

                const response2 = await api(`/documents/${doc.id}/re-extract`, { method: 'POST', body: form2 });
                doc = response2.document || doc;
                localAiSuccess = response2.success !== false;
                isDuplicate = response2.duplicate === true;
                isTaxStatement = response2.tax_statement === true || isTaxDocumentType(doc.document_type);
                if (!localAiSuccess) localAiFailure = summarizeStageFailure(response2);
              } else {
                const form2 = new FormData();
                form2.append('file', file);
                form2.append('ai_provider', 'local');
                if (selectedUserRef.current !== 'all') form2.append('user_id', selectedUserRef.current);

                const response2 = await api('/documents/upload', { method: 'POST', body: form2 });
                doc = response2.document || response2;
                localAiSuccess = response2.success !== false;
                isDuplicate = response2.duplicate === true;
                isTaxStatement = response2.tax_statement === true || isTaxDocumentType(doc.document_type);
                if (!localAiSuccess) localAiFailure = summarizeStageFailure(response2);
              }
            } catch (error) {
              console.error("Local AI stage failed:", error);
              localAiFailure = summarizeStageFailure(null, error);
              localAiSuccess = false;
            }

            if (!localAiSuccess) {
              setStatus(`Please manually check and fill details. Local Hosted LM Studio AI failed: ${localAiFailure}`);
              await new Promise(resolve => setTimeout(resolve, 2000));
            }
          }
        }
        
        if (!doc) {
          throw new Error("Failed to process document. Please check server connections and logs.");
        }
        
        uploadedDocs.push({ ...doc, duplicate: isDuplicate || doc.duplicate === true });
        await refresh();
        
        if (isTaxStatement) {
          updateUploadJob(job.id, { state: doc.status === 'confirmed' ? 'saved' : 'needs reconcile' });
          setStatus(doc.status === 'confirmed' ? `${file.name} tax statement saved.` : `${file.name} tax statement needs attention in Reconcile.`);
        } else if (doc.status !== 'confirmed') {
          updateUploadJob(job.id, { state: 'needs review' });
          setStatus(`${file.name} needs review. Continuing with the next PDF.`);
        } else {
          updateUploadJob(job.id, { state: 'saved' });
        }
      }
      const pendingReview = uploadedDocs.filter((d) => d.status !== 'confirmed' && !isTaxDocumentType(d.document_type));
      const duplicateCount = uploadedDocs.filter((d) => d.duplicate).length;
      if (pendingReview.length === 0) {
        setStatus(duplicateCount > 0 ? `${duplicateCount} duplicate confirmed PDF${duplicateCount > 1 ? 's were' : ' was'} already saved.` : '');
        setUploadJobs([]);
      } else {
        setReviewQueue((prev) => {
          const nextQueue = [...prev, ...pendingReview];
          setReviewDoc((curr) => curr || nextQueue[0]);
          return nextQueue;
        });
        setStatus(`${uploadedDocs.length} PDF${uploadedDocs.length > 1 ? 's' : ''} processed. Some files need review.`);
      }
    } catch (error) {
      const activeJob = jobs.find((job) => job.state !== 'saved');
      if (activeJob) updateUploadJob(activeJob.id, { state: 'failed' });
      setStatus(error.message);
    }
  }

  async function handleDeleteUser() {
    if (selectedUser === 'all') return;
    const user = users.find((u) => String(u.id) === String(selectedUser));
    if (!user) return;
    if (window.confirm(`Are you absolutely sure you want to delete the user "${user.name}"? This will permanently delete all database records and physical PDF files stored on disk for this user.`)) {
      try {
        await api(`/users/${selectedUser}`, {
          method: 'DELETE',
        });
        setSelectedUser('all');
        await refresh();
        setStatus(`User "${user.name}" and all associated records and files have been successfully deleted.`);
      } catch (err) {
        setStatus(err.message);
      }
    }
  }

  async function confirmDeleteDoc() {
    if (!deleteTargetDoc) return;
    setIsDeletingDoc(true);
    setDeleteDocError('');
    try {
      await api(`/documents/${deleteTargetDoc.id}`, { method: 'DELETE' });
      const deletedName = deleteTargetDoc.original_name;
      setDeleteTargetDoc(null);
      setStatus((currentStatus) => {
        if (currentStatus && currentStatus.includes(deletedName)) {
          return '';
        }
        return currentStatus;
      });
      await refresh();
    } catch (error) {
      setDeleteDocError(error.message);
    } finally {
      setIsDeletingDoc(false);
    }
  }

  async function logoutApp() {
    try {
      await api('/auth/logout', { method: 'POST' });
    } catch {}
    clearAuthToken();
    setUnlocked(false);
    setStatus('');
  }

  if (!authChecked) {
    return (
      <main className="shell container-fluid">
        <div className="authShell shadow-sm">Checking app lock...</div>
      </main>
    );
  }

  if (!unlocked) {
    return (
      <AuthScreen
        setupRequired={setupRequired}
        onUnlocked={(token) => {
          setAuthToken(token);
          setSetupRequired(false);
          setUnlocked(true);
          setStatus('');
        }}
      />
    );
  }


  return (
    <main className="shell container-fluid">
      <header className="topbar shadow-sm">
        <div>
          <h1>Income Ledger</h1>
          <p>Salary, freelance income, TDS, GST, and Indian FY tax estimates.</p>
        </div>
        <div className="actions topActions">
          <label className="btn btn-primary" title="Upload PDFs">
            <Upload size={18} />
            Upload PDFs
            <input className="d-none" type="file" accept="application/pdf" multiple onChange={handleUpload} />
          </label>
          <button className="btn btn-outline-primary" title="Export Excel workbook" onClick={() => setExportOpen(true)}>
            <FileDown size={18} />
            Export
          </button>
          <button className="btn btn-outline-secondary" type="button" title="Toggle theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button className="btn btn-outline-secondary" type="button" title="Lock app" onClick={logoutApp}>
            <X size={18} />
            Lock
          </button>
        </div>
      </header>

      <nav className="viewNav shadow-sm" aria-label="Primary views">
        <button className={`viewNavButton ${activeView === 'dashboard' ? 'active' : ''}`} type="button" onClick={() => setActiveView('dashboard')}>
          <BarChart3 size={18} />
          Dashboard
        </button>
        <button className={`viewNavButton ${activeView === 'tax-planner' ? 'active' : ''}`} type="button" onClick={() => setActiveView('tax-planner')}>
          <Calculator size={18} />
          Tax Planner
        </button>
        <button className={`viewNavButton ${activeView === 'ai-advisor' ? 'active' : ''}`} type="button" onClick={() => setActiveView('ai-advisor')}>
          <MessageSquare size={18} />
          AI Advisor
        </button>
        <button className={`viewNavButton ${activeView === 'activity' ? 'active' : ''}`} type="button" onClick={() => setActiveView('activity')}>
          <Activity size={18} />
          Activity
        </button>
        <button className={`viewNavButton ${activeView === 'reconciliation' ? 'active' : ''}`} type="button" onClick={() => setActiveView('reconciliation')}>
          <Link size={18} />
          Reconcile
        </button>
        <button className={`viewNavButton ${activeView === 'validation' ? 'active' : ''}`} type="button" onClick={() => setActiveView('validation')}>
          <ClipboardCheck size={18} />
          Validate
        </button>
        <button className={`viewNavButton ${activeView === 'settings' ? 'active' : ''}`} type="button" onClick={() => setActiveView('settings')}>
          <SettingsIcon size={18} />
          Settings
        </button>
      </nav>

      {status && (
        <div className="alert alert-info status d-flex justify-content-between align-items-center">
          <span>{status}</span>
          <button type="button" className="btn-close" aria-label="Close" onClick={() => setStatus('')}></button>
        </div>
      )}
      {uploadJobs.length > 0 && (
        <UploadQueue
          jobs={uploadJobs}
          documents={documents}
          onJobClick={(doc) => {
            if (doc) {
              setReviewDoc(doc);
            }
          }}
          onClear={() => setUploadJobs([])}
        />
      )}

      <section className="toolbar shadow-sm">
        <select className="form-select" value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)}>
          <option value="all">All users</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>{user.name}</option>
          ))}
        </select>
        {selectedUser !== 'all' && (
          <button
            className="btn btn-outline-secondary"
            title="Edit user profile"
            type="button"
            onClick={() => setEditUser(users.find((u) => String(u.id) === String(selectedUser)))}
            style={{ padding: '10px 14px' }}
          >
            <Edit size={16} />
          </button>
        )}
        {selectedUser !== 'all' && (
          <button
            className="btn btn-outline-danger"
            title="Delete user and all data"
            type="button"
            onClick={handleDeleteUser}
            style={{ padding: '10px 14px' }}
          >
            <Trash2 size={16} />
          </button>
        )}
        <select className="form-select" value={selectedYear} onChange={(event) => setSelectedYear(event.target.value)}>
          {years.map((year) => (
            <option key={year} value={year}>{year}</option>
          ))}
        </select>
        <NewUserForm onCreated={refresh} />
        <button className="btn btn-dark" type="button" onClick={() => setNewIncomeOpen(true)}>
          <Plus size={16} /> Income
        </button>
        <ExpenseForm users={users} selectedUser={selectedUser} onCreated={refresh} />
      </section>

      {activeView === 'settings' ? (
        <SettingsPanel
          users={users}
          years={years}
          selectedUser={selectedUser}
          selectedYear={selectedYear}
          onApplyPreferences={(settings) => {
            if (settings.default_user_id) setSelectedUser(settings.default_user_id);
            if (settings.default_financial_year) setSelectedYear(settings.default_financial_year);
          }}
          onLocked={logoutApp}
        />
      ) : activeView === 'activity' ? (
        <ActivityLogView selectedUser={selectedUser} />
      ) : activeView === 'reconciliation' ? (
        <ReconciliationView
          selectedUser={selectedUser}
          selectedYear={selectedYear}
          dataVersion={dataVersion}
          documents={documents}
          onReview={setReviewDoc}
          onRequestDelete={setDeleteTargetDoc}
        />
      ) : activeView === 'validation' ? (
        <ValidationReportView selectedUser={selectedUser} selectedYear={selectedYear} />
      ) : activeView === 'tax-planner' ? (
        <TaxPlannerPanel userId={selectedUser || 'all'} financialYear={selectedYear} />
      ) : activeView === 'ai-advisor' ? (
        <AiAdvisorPanel
          userId={activeAiAdvisorUser}
          financialYear={activeAiAdvisorYear}
          advisor={activeAiAdvisorState}
          onInputChange={setAiAdvisorInput}
          onClearTokenCount={clearAiAdvisorTokenCount}
          onRunAnalysis={runAiAdvisorAnalysis}
          onSendMessage={sendAiAdvisorMessage}
        />
      ) : (
        <>
          <Dashboard
            dashboard={dashboard}
            selectedUser={selectedUser}
            mode={dashboardMode}
            onModeChange={setDashboardMode}
            onDrilldown={setDrilldown}
          />
          {drilldown && (
            <DrilldownPanel
              type={drilldown}
              dashboard={dashboard}
              users={users}
              onClose={() => setDrilldown(null)}
              onDeleted={refresh}
            />
          )}

          <section className="contentGrid">
            <DocumentPanel documents={filteredDocuments} pendingDocs={pendingDocs} onReview={setReviewDoc} onRequestDelete={setDeleteTargetDoc} />
            <RecordsPanel records={dashboard?.records || []} onDeleted={refresh} />
            <ExpensesPanel expenses={dashboard?.expenses || []} users={users} onDeleted={refresh} />
          </section>
        </>
      )}

      {reviewDoc && (
        <ReviewModal
          key={reviewDoc.id}
          document={reviewDoc}
          users={users}
          onClose={() => {
            setReviewQueue((prev) => {
              const nextQueue = prev.filter((d) => d.id !== reviewDoc.id);
              setReviewDoc(nextQueue[0] || null);
              return nextQueue;
            });
          }}
          onSaved={async () => {
            await refresh();
            setReviewQueue((prev) => {
              const nextQueue = prev.filter((d) => d.id !== reviewDoc.id);
              setReviewDoc(nextQueue[0] || null);
              return nextQueue;
            });
          }}
        />
      )}

      {editUser && (
        <EditUserModal
          user={editUser}
          onClose={() => setEditUser(null)}
          onSaved={refresh}
        />
      )}

      {newIncomeOpen && (
        <NewIncomeModal
          users={users}
          selectedUser={selectedUser}
          onClose={() => setNewIncomeOpen(false)}
          onCreated={refresh}
        />
      )}

      {exportOpen && (
        <ExportWorkbookModal
          users={users}
          years={years}
          selectedUser={selectedUser}
          selectedYear={selectedYear}
          onClose={() => setExportOpen(false)}
        />
      )}

      {deleteTargetDoc && (
        <div className="ledger-modal-backdrop" onClick={() => !isDeletingDoc && setDeleteTargetDoc(null)}>
          <div className="ledger-modal deleteConfirmModal shadow-lg" role="dialog" aria-modal="true" aria-labelledby="delete-document-title" onClick={(event) => event.stopPropagation()}>
            <h2 id="delete-document-title"><Trash2 size={18} /> Delete document?</h2>
            {isTaxDocumentType(deleteTargetDoc.document_type) ? (
              <p>This removes the uploaded tax statement PDF and parsed Form 16/26AS rows. Salary and freelance records are not changed.</p>
            ) : (
              <p>This removes the PDF and any linked income or expense data from the dashboard.</p>
            )}
            <div className="deleteSummary">
              <strong>{deleteTargetDoc.original_name}</strong>
              <span>{deleteTargetDoc.document_type} | {deleteTargetDoc.status}</span>
            </div>
            {deleteDocError && <div className="alert alert-danger">{deleteDocError}</div>}
            <div className="modalActions">
              <button className="btn btn-outline-secondary" type="button" onClick={() => setDeleteTargetDoc(null)} disabled={isDeletingDoc}>Cancel</button>
              <button className="btn btn-danger" type="button" onClick={confirmDeleteDoc} disabled={isDeletingDoc}>
                <Trash2 size={16} /> {isDeletingDoc ? 'Deleting...' : 'Delete document'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function AuthScreen({ setupRequired, onUnlocked }) {
  const [pin, setPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError('');
    if (setupRequired && pin !== confirmPin) {
      setError('PIN entries do not match.');
      return;
    }
    setBusy(true);
    try {
      const response = await api(setupRequired ? '/auth/setup' : '/auth/login', {
        method: 'POST',
        skipAuth: true,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin }),
      });
      onUnlocked(response.token);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell container-fluid authPage">
      <form className="authShell shadow-sm" onSubmit={submit}>
        <h1>{setupRequired ? 'Create App PIN' : 'Unlock Income Ledger'}</h1>
        <p>{setupRequired ? 'Protect this local ledger with a PIN or password.' : 'Enter your App PIN to continue.'}</p>
        {error && <div className="alert alert-danger">{error}</div>}
        <label>
          App PIN
          <input
            className="form-control"
            type="password"
            minLength={4}
            maxLength={128}
            value={pin}
            onChange={(event) => setPin(event.target.value)}
            required
            autoFocus
          />
        </label>
        {setupRequired && (
          <label>
            Confirm App PIN
            <input
              className="form-control"
              type="password"
              minLength={4}
              maxLength={128}
              value={confirmPin}
              onChange={(event) => setConfirmPin(event.target.value)}
              required
            />
          </label>
        )}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          <Check size={16} /> {busy ? 'Please wait...' : (setupRequired ? 'Create and unlock' : 'Unlock')}
        </button>
      </form>
    </main>
  );
}

function ExportWorkbookModal({ users, years, selectedUser, selectedYear, onClose }) {
  const initialUsers = selectedUser === 'all' ? ['all'] : [String(selectedUser)];
  const [selectedUsers, setSelectedUsers] = useState(initialUsers);
  const [selectedYears, setSelectedYears] = useState(selectedYear ? [selectedYear] : years.slice(0, 1));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function toggleUser(value) {
    setSelectedUsers((current) => {
      if (value === 'all') return current.includes('all') ? [] : ['all'];
      const withoutAll = current.filter((item) => item !== 'all');
      return withoutAll.includes(value) ? withoutAll.filter((item) => item !== value) : [...withoutAll, value];
    });
  }

  function toggleYear(value) {
    setSelectedYears((current) => (
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value]
    ));
  }

  async function exportWorkbook(event) {
    event.preventDefault();
    if (selectedUsers.length === 0 || selectedYears.length === 0) {
      setError('Select at least one user and one financial year.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const params = new URLSearchParams({
        user_ids: selectedUsers.includes('all') ? 'all' : selectedUsers.join(','),
        financial_years: selectedYears.join(','),
      });
      const blob = await apiBlob(`/export/workbook?${params.toString()}`);
      const yearLabel = selectedYears.length > 1 ? 'multi-year' : selectedYears[0].replaceAll(' ', '-');
      triggerBlobDownload(blob, `income-ledger-${yearLabel}.xlsx`);
      onClose();
    } catch (exportError) {
      setError(exportError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ledger-modal-backdrop" onClick={() => !busy && onClose()}>
      <form className="ledger-modal exportModal shadow-lg" onSubmit={exportWorkbook} role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <h2><FileDown size={18} /> Export Excel workbook</h2>
        <p>Select the users and financial years to include. The workbook includes income, expenses, monthly GST, tax, documents, and a debit-credit freelance balance sheet.</p>
        {error && <div className="alert alert-danger py-2">{error}</div>}
        <div className="exportSelectionGrid">
          <div>
            <h3>Users</h3>
            <label className="choiceRow">
              <input type="checkbox" checked={selectedUsers.includes('all')} onChange={() => toggleUser('all')} />
              All users
            </label>
            {users.map((user) => (
              <label className="choiceRow" key={user.id}>
                <input type="checkbox" checked={selectedUsers.includes(String(user.id))} disabled={selectedUsers.includes('all')} onChange={() => toggleUser(String(user.id))} />
                {user.name}
              </label>
            ))}
          </div>
          <div>
            <h3>Financial years</h3>
            {years.map((year) => (
              <label className="choiceRow" key={year}>
                <input type="checkbox" checked={selectedYears.includes(year)} onChange={() => toggleYear(year)} />
                {year}
              </label>
            ))}
          </div>
        </div>
        <div className="modalActions">
          <button className="btn btn-outline-secondary" type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" type="submit" disabled={busy}><FileDown size={16} /> {busy ? 'Exporting...' : 'Export workbook'}</button>
        </div>
      </form>
    </div>
  );
}

function SettingsPanel({ users, years, selectedUser, selectedYear, onApplyPreferences, onLocked }) {
  const [settings, setSettings] = useState({
    default_user_id: selectedUser || 'all',
    default_financial_year: selectedYear || '',
    local_ai_base_url: '',
    local_ai_model: '',
    local_ai_timeout_seconds: 120,
    local_ai_rendered_pages: 1,
    cloud_ai_base_url: '',
    cloud_ai_model: '',
    cloud_ai_api_key: '',
    cloud_ai_api_key_set: 'false',
  });
  const [pinForm, setPinForm] = useState({ current_pin: '', new_pin: '', confirm_pin: '' });
  const [history, setHistory] = useState([]);
  const [importErrors, setImportErrors] = useState([]);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [taxRuleYear, setTaxRuleYear] = useState(selectedYear || '');
  const [taxRuleDraft, setTaxRuleDraft] = useState(null);
  const [taxRulePin, setTaxRulePin] = useState('');

  async function loadSettings() {
    const [settingsData, historyData] = await Promise.all([
      api('/settings'),
      api('/backup/history'),
    ]);
    setSettings(settingsData);
    setHistory(historyData);
  }

  useEffect(() => {
    loadSettings().catch((loadError) => setError(loadError.message));
  }, []);

  useEffect(() => {
    if (!taxRuleYear && selectedYear) setTaxRuleYear(selectedYear);
  }, [selectedYear, taxRuleYear]);

  function setSetting(key, value) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  async function saveSettings(event) {
    event.preventDefault();
    setBusy('settings');
    setError('');
    setMessage('');
    try {
      const payload = { ...settings };
      delete payload.cloud_ai_api_key_set;
      if (!payload.cloud_ai_api_key) delete payload.cloud_ai_api_key;
      const updated = await api('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      setSettings({ ...updated, cloud_ai_api_key: '' });
      onApplyPreferences(updated);
      setMessage('Settings saved.');
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy('');
    }
  }

  async function clearCloudAiKey() {
    if (!window.confirm('Remove the saved Cloud AI API key from this app?')) return;
    setBusy('clear-cloud-ai');
    setError('');
    setMessage('');
    try {
      const updated = await api('/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clear_cloud_ai_api_key: true }),
      });
      setSettings({ ...updated, cloud_ai_api_key: '' });
      setMessage('Cloud AI API key cleared.');
    } catch (clearError) {
      setError(clearError.message);
    } finally {
      setBusy('');
    }
  }

  async function draftTaxRuleUpdate() {
    const financialYear = taxRuleYear.trim();
    if (!financialYear) {
      setError('Financial year is required for tax slab update check.');
      return;
    }
    setBusy('tax-rule-draft');
    setError('');
    setMessage('');
    try {
      const response = await api('/tax-rules/ai-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ financial_year: financialYear }),
      });
      setTaxRuleDraft(response.draft);
      setTaxRulePin('');
      const usedTokens = Number(response.usage?.total_tokens || 0);
      setMessage(`Cloud AI drafted tax slabs for ${response.draft.financial_year}.${usedTokens ? ` Tokens: ${usedTokens}.` : ''}`);
    } catch (draftError) {
      setTaxRuleDraft(null);
      setError(draftError.message);
    } finally {
      setBusy('');
    }
  }

  async function applyTaxRuleUpdate(event) {
    event.preventDefault();
    if (!taxRuleDraft) {
      setError('Run a Cloud AI slab check before applying an update.');
      return;
    }
    if (!taxRulePin.trim()) {
      setError('Enter the App PIN to apply tax slab updates.');
      return;
    }
    if (!window.confirm(`Apply the reviewed tax slabs for ${taxRuleDraft.financial_year}?`)) return;
    setBusy('tax-rule-apply');
    setError('');
    setMessage('');
    try {
      const result = await api('/tax-rules/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ draft: taxRuleDraft, app_pin: taxRulePin }),
      });
      setTaxRuleDraft(null);
      setTaxRulePin('');
      setTaxRuleYear(result.financial_year);
      setMessage(`Tax slabs updated for ${result.financial_year}. Applied regimes: ${result.regimes.join(', ')}.`);
    } catch (applyError) {
      setError(applyError.message);
    } finally {
      setBusy('');
    }
  }

  async function exportBackup() {
    setBusy('backup');
    setError('');
    setMessage('');
    try {
      const blob = await apiBlob('/backup/export', { method: 'POST' });
      const url = URL.createObjectURL(blob);
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      const link = document.createElement('a');
      link.href = url;
      link.download = `income-ledger-backup-${stamp}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      const historyData = await api('/backup/history');
      setHistory(historyData);
      setMessage('Backup exported.');
    } catch (backupError) {
      setError(backupError.message);
    } finally {
      setBusy('');
    }
  }

  async function downloadBlob(path, filename, options = {}) {
    const blob = await apiBlob(path, options);
    triggerBlobDownload(blob, filename);
  }

  async function downloadTemplate() {
    setBusy('template');
    setError('');
    setMessage('');
    try {
      await downloadBlob('/import/template', 'income-ledger-import-template.xlsx');
      setMessage('Import template downloaded.');
    } catch (templateError) {
      setError(templateError.message);
    } finally {
      setBusy('');
    }
  }

  async function restoreBackup(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!window.confirm('Restore this backup? Current data will be replaced after a safety backup is created.')) return;
    setBusy('restore');
    setError('');
    setMessage('');
    try {
      const form = new FormData();
      form.append('file', file);
      const result = await api('/backup/restore', { method: 'POST', body: form });
      const historyData = await api('/backup/history');
      setHistory(historyData);
      setMessage(`Backup restored. Safety backup: ${result.safety_backup?.filename || 'created'}.`);
    } catch (restoreError) {
      setError(restoreError.message);
    } finally {
      setBusy('');
    }
  }

  async function importWorkbook(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setBusy('workbook-import');
    setError('');
    setMessage('');
    setImportErrors([]);
    try {
      const form = new FormData();
      form.append('file', file);
      const result = await api('/import/workbook', { method: 'POST', body: form });
      setImportErrors(result.errors || []);
      setMessage(`Imported ${result.created?.income || 0} income rows and ${result.created?.expenses || 0} expense rows.`);
    } catch (importError) {
      setError(importError.message);
    } finally {
      setBusy('');
    }
  }

  async function changeAppPin(event) {
    event.preventDefault();
    setError('');
    setMessage('');
    if (pinForm.new_pin !== pinForm.confirm_pin) {
      setError('New PIN confirmation does not match.');
      return;
    }
    setBusy('pin');
    try {
      await api('/auth/change-pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_pin: pinForm.current_pin, new_pin: pinForm.new_pin }),
      });
      setMessage('App PIN changed. Unlock again with the new PIN.');
      onLocked();
    } catch (pinError) {
      setError(pinError.message);
    } finally {
      setBusy('');
    }
  }

  function sizeLabel(bytes) {
    const value = Number(bytes || 0);
    if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
    if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${value} B`;
  }

  return (
    <section className="settingsGrid">
      <div className="panel shadow-sm settingsPanel">
        <h2><SettingsIcon size={18} /> Settings</h2>
        {message && <div className="alert alert-success py-2">{message}</div>}
        {error && <div className="alert alert-danger py-2">{error}</div>}
        <form className="settingsForm" onSubmit={saveSettings}>
          <label>Default user
            <select className="form-select" value={settings.default_user_id || 'all'} onChange={(event) => setSetting('default_user_id', event.target.value)}>
              <option value="all">All users</option>
              {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
            </select>
          </label>
          <label>Default financial year
            <select className="form-select" value={settings.default_financial_year || ''} onChange={(event) => setSetting('default_financial_year', event.target.value)}>
              <option value="">Current selection</option>
              {years.map((year) => <option key={year} value={year}>{year}</option>)}
            </select>
          </label>
          <label>Local AI URL
            <input className="form-control" value={settings.local_ai_base_url || ''} onChange={(event) => setSetting('local_ai_base_url', event.target.value)} />
          </label>
          <label>Local AI model
            <input className="form-control" value={settings.local_ai_model || ''} onChange={(event) => setSetting('local_ai_model', event.target.value)} />
          </label>
          <label>AI timeout seconds (extraction + advisor)
            <input className="form-control" type="number" min="1" value={settings.local_ai_timeout_seconds || 120} onChange={(event) => setSetting('local_ai_timeout_seconds', Number(event.target.value))} />
          </label>
          <label>Rendered pages
            <input className="form-control" type="number" min="1" value={settings.local_ai_rendered_pages || 1} onChange={(event) => setSetting('local_ai_rendered_pages', Number(event.target.value))} />
          </label>
          <label>Cloud AI URL
            <input className="form-control" value={settings.cloud_ai_base_url || ''} onChange={(event) => setSetting('cloud_ai_base_url', event.target.value)} placeholder="https://api.openai.com/v1" />
          </label>
          <label>Cloud AI model
            <input className="form-control" value={settings.cloud_ai_model || ''} onChange={(event) => setSetting('cloud_ai_model', event.target.value)} placeholder="Enter model name" />
          </label>
          <label>Cloud AI API key
            <input
              className="form-control"
              type="password"
              value={settings.cloud_ai_api_key || ''}
              onChange={(event) => setSetting('cloud_ai_api_key', event.target.value)}
              placeholder={settings.cloud_ai_api_key_set === 'true' ? 'Saved - leave blank to keep' : 'Paste API key'}
            />
          </label>
          <div className="settingsActions">
            <button className="btn btn-primary" type="submit" disabled={busy === 'settings'}>
              <Check size={16} /> {busy === 'settings' ? 'Saving...' : 'Save settings'}
            </button>
            <button
              className="btn btn-outline-danger"
              type="button"
              onClick={clearCloudAiKey}
              disabled={busy === 'clear-cloud-ai' || settings.cloud_ai_api_key_set !== 'true'}
              title="Remove saved Cloud AI API key"
            >
              <X size={16} /> {busy === 'clear-cloud-ai' ? 'Clearing...' : 'Clear Cloud AI key'}
            </button>
          </div>
        </form>
      </div>

      <div className="panel shadow-sm settingsPanel">
        <h2><Calculator size={18} /> Tax Slab Updates</h2>
        <div className="taxRuleControls">
          <label>Financial year
            <input
              className="form-control"
              value={taxRuleYear}
              onChange={(event) => setTaxRuleYear(event.target.value)}
              placeholder="FY 2027-28"
            />
          </label>
          <button className="btn btn-outline-primary" type="button" onClick={draftTaxRuleUpdate} disabled={busy === 'tax-rule-draft' || !taxRuleYear.trim()}>
            <Calculator size={16} /> {busy === 'tax-rule-draft' ? 'Checking...' : 'Check slabs'}
          </button>
        </div>
        {taxRuleDraft && (
          <div className="taxRuleDraft">
            <div className="taxRuleDraftMeta">
              <strong>{taxRuleDraft.financial_year}</strong>
              <span>Confidence: {taxRuleDraft.confidence || 'review_required'}</span>
              {taxRuleDraft.source_summary && <span>{taxRuleDraft.source_summary}</span>}
            </div>
            {taxRuleDraft.warnings?.length > 0 && (
              <div className="warnings taxRuleWarnings">
                {taxRuleDraft.warnings.map((warning, index) => <div key={index}>{warning}</div>)}
              </div>
            )}
            <div className="taxRuleRegimeList">
              {Object.entries(taxRuleDraft.regimes || {}).map(([regime, rule]) => (
                <div className="taxRuleRegime" key={regime}>
                  <strong>{regime.toUpperCase()} regime {rule.is_default ? <span className="badge text-bg-primary">Default</span> : null}</strong>
                  <span>{rule.assessment_year || 'No assessment year'} - {(rule.slabs || []).length} slabs - cess {Math.round(Number(rule.cess_rate || 0) * 100)}%</span>
                  <span>Rebate {currency(rule.rebate_threshold)} / {currency(rule.rebate_max)} - standard deduction {currency(rule.salary_standard_deduction)}</span>
                </div>
              ))}
            </div>
            <details>
              <summary>Raw draft JSON</summary>
              <pre className="taxRuleDraftPreview">{JSON.stringify(taxRuleDraft, null, 2)}</pre>
            </details>
            <form className="taxRuleApplyForm" onSubmit={applyTaxRuleUpdate}>
              <label>Confirm App PIN
                <input
                  className="form-control"
                  type="password"
                  value={taxRulePin}
                  onChange={(event) => setTaxRulePin(event.target.value)}
                  minLength={4}
                  placeholder="Required before applying"
                />
              </label>
              <button className="btn btn-primary" type="submit" disabled={busy === 'tax-rule-apply' || !taxRulePin.trim()}>
                <Check size={16} /> {busy === 'tax-rule-apply' ? 'Applying...' : 'Apply slabs'}
              </button>
            </form>
          </div>
        )}
      </div>

      <div className="panel shadow-sm settingsPanel">
        <h2><FileDown size={18} /> Backup</h2>
        <div className="settingsActions">
          <button className="btn btn-primary" type="button" onClick={exportBackup} disabled={busy === 'backup'}>
            <FileDown size={16} /> {busy === 'backup' ? 'Exporting...' : 'Export ZIP backup'}
          </button>
          <label className="btn btn-outline-danger" title="Restore ZIP backup">
            {busy === 'restore' ? 'Restoring...' : 'Restore ZIP'}
            <input className="d-none" type="file" accept=".zip,application/zip" onChange={restoreBackup} disabled={busy === 'restore'} />
          </label>
        </div>
        <div className="backupHistory">
          <h3>Recent backups</h3>
          {history.map((item) => (
            <div className="backupHistoryRow" key={item.filename}>
              <div>
                <strong>{item.filename}</strong>
                <span>{new Date(item.created_at).toLocaleString()} - {item.upload_count} uploads</span>
              </div>
              <span>{sizeLabel(item.size_bytes)}</span>
            </div>
          ))}
          {history.length === 0 && <p className="muted">No backups exported yet.</p>}
        </div>
      </div>

      <div className="panel shadow-sm settingsPanel">
        <h2><FileDown size={18} /> Excel Import</h2>
        <div className="settingsActions">
          <button className="btn btn-outline-secondary" type="button" onClick={downloadTemplate} disabled={busy === 'template'}>
            Template
          </button>
          <label className="btn btn-outline-primary">
            {busy === 'workbook-import' ? 'Importing...' : 'Import workbook'}
            <input className="d-none" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={importWorkbook} disabled={busy === 'workbook-import'} />
          </label>
        </div>
        {importErrors.length > 0 && (
          <div className="warnings">
            {importErrors.slice(0, 8).map((item, index) => (
              <div key={index}>{item.sheet} row {item.row}: {item.error}</div>
            ))}
          </div>
        )}
      </div>

      <div className="panel shadow-sm settingsPanel">
        <h2><KeyRound size={18} /> App PIN</h2>
        <form className="settingsForm" onSubmit={changeAppPin}>
          <label>Current PIN
            <input className="form-control" type="password" value={pinForm.current_pin} onChange={(event) => setPinForm({ ...pinForm, current_pin: event.target.value })} required minLength={4} />
          </label>
          <label>New PIN
            <input className="form-control" type="password" value={pinForm.new_pin} onChange={(event) => setPinForm({ ...pinForm, new_pin: event.target.value })} required minLength={4} />
          </label>
          <label>Confirm new PIN
            <input className="form-control" type="password" value={pinForm.confirm_pin} onChange={(event) => setPinForm({ ...pinForm, confirm_pin: event.target.value })} required minLength={4} />
          </label>
          <div className="settingsActions">
            <button className="btn btn-outline-primary" type="submit" disabled={busy === 'pin'}>
              <KeyRound size={16} /> {busy === 'pin' ? 'Changing...' : 'Change PIN'}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}

function ActivityLogView({ selectedUser }) {
  const [data, setData] = useState({ items: [], total: 0 });
  const [filters, setFilters] = useState({ event_type: '', date_from: '', date_to: '' });
  const [error, setError] = useState('');

  async function loadActivity() {
    const params = new URLSearchParams();
    if (selectedUser) params.set('user_id', selectedUser);
    if (filters.event_type) params.set('event_type', filters.event_type);
    if (filters.date_from) params.set('date_from', filters.date_from);
    if (filters.date_to) params.set('date_to', filters.date_to);
    params.set('limit', '100');
    const response = await api(`/audit-events?${params.toString()}`);
    setData(response);
  }

  useEffect(() => {
    loadActivity().catch((loadError) => setError(loadError.message));
  }, [selectedUser]);

  function summarizeEvent(event) {
    const after = event.after || {};
    const before = event.before || {};
    const target = event.document_name || after.payer || before.payer || after.category || before.category || 'Ledger item';
    return `${event.event_type.replaceAll('_', ' ')} - ${target}`;
  }

  return (
    <section className="panel shadow-sm reviewPanel">
      <h2><Activity size={18} /> Activity Log <span>{data.total} events</span></h2>
      {error && <div className="alert alert-danger py-2">{error}</div>}
      <form className="reviewFilters" onSubmit={(event) => { event.preventDefault(); loadActivity().catch((loadError) => setError(loadError.message)); }}>
        <input className="form-control" placeholder="Event type" value={filters.event_type} onChange={(event) => setFilters({ ...filters, event_type: event.target.value })} />
        <input className="form-control" type="date" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} />
        <input className="form-control" type="date" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} />
        <button className="btn btn-primary" type="submit"><ListChecks size={16} /> Filter</button>
      </form>
      <div className="reviewList">
        {data.items.map((event) => (
          <div className="reviewRow" key={event.id}>
            <div>
              <strong>{summarizeEvent(event)}</strong>
              <span>{event.user_name || 'No user'} - {new Date(event.created_at).toLocaleString()}</span>
            </div>
            <span className="badge text-bg-secondary">{event.event_type}</span>
          </div>
        ))}
        {data.items.length === 0 && <p className="muted">No audit events found.</p>}
      </div>
    </section>
  );
}

function ReconciliationView({ selectedUser, selectedYear, dataVersion, documents = [], onReview, onRequestDelete }) {
  const [report, setReport] = useState(null);
  const [taxReport, setTaxReport] = useState(null);
  const [error, setError] = useState('');
  const [taxError, setTaxError] = useState('');
  const [isChecking, setIsChecking] = useState(false);
  const [lastChecked, setLastChecked] = useState('');

  async function loadReport() {
    setIsChecking(true);
    setError('');
    setTaxError('');
    const params = new URLSearchParams();
    if (selectedUser) params.set('user_id', selectedUser);
    if (selectedYear) params.set('financial_year', selectedYear);
    try {
      const [baseReport, taxReconciliation] = await Promise.all([
        api(`/reconciliation?${params.toString()}`),
        selectedYear
          ? api(`/tax-reconciliation/${selectedUser || 'all'}/${encodeURIComponent(selectedYear)}`)
          : Promise.resolve(null),
      ]);
      setReport(baseReport);
      setTaxReport(taxReconciliation);
      setLastChecked(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setIsChecking(false);
    }
  }

  useEffect(() => {
    loadReport();
  }, [selectedUser, selectedYear, dataVersion]);

  const summary = report?.summary || {};
  const taxSummary = taxReport?.summary || {};
  return (
    <section className="reviewToolsGrid">
      <div className="panel shadow-sm reviewPanel">
        <div className="reconcileHeader">
          <h2><Link size={18} /> Reconciliation</h2>
          <div className="reconcileActions">
            {lastChecked && <span className="reconcileLastChecked">Checked {lastChecked}</span>}
            <button className="btn btn-sm btn-outline-primary" type="button" onClick={loadReport} disabled={isChecking}>
              <RefreshCw size={15} /> {isChecking ? 'Checking...' : 'Recheck'}
            </button>
          </div>
        </div>
        {error && <div className="alert alert-danger py-2">{error}</div>}
        {taxError && <div className="alert alert-danger py-2">{taxError}</div>}
        <div className="reviewSummary">
          <Metric icon={<AlertTriangle />} label="Needs review" value={summary.needs_review || 0} />
          <Metric icon={<FileText />} label="Missing PDFs" value={summary.missing_files || 0} />
          <Metric icon={<Link />} label="Linked docs" value={summary.linked_documents || 0} />
          <Metric icon={<FileText />} label="Unlinked docs" value={summary.unlinked_documents || 0} />
          <Metric icon={<ClipboardCheck />} label="Active 26AS" value={taxSummary.active_26as || 0} />
          <Metric icon={<FileText />} label="Form 16 employers" value={taxSummary.form16_employers || 0} />
          <Metric icon={<AlertTriangle />} label="Monthly salary mismatches" value={taxSummary.monthly_salary_mismatches || 0} />
          <Metric icon={<AlertTriangle />} label="Tax findings" value={taxSummary.findings || 0} />
        </div>
      </div>
      <TaxReconciliationSection report={taxReport} documents={documents} onReview={onReview} onRequestDelete={onRequestDelete} />
      <DocumentReviewList title="Needs review" documents={report?.needs_review || []} onReview={onReview} />
      <DocumentReviewList title="Missing source PDFs" documents={report?.missing_files || []} onReview={onReview} />
      <DocumentReviewList title="Unlinked documents" documents={report?.unlinked_documents || []} onReview={onReview} />
      <DocumentReviewList title="Linked documents" documents={report?.linked_documents || []} onReview={onReview} />
    </section>
  );
}

function TaxReconciliationSection({ report, documents = [], onReview, onRequestDelete }) {
  const active26as = report?.active_26as;
  const taxDocuments = report?.tax_documents || [];
  const form16Sets = report?.form16_sets || [];
  const employerRows = report?.employer_comparisons || [];
  const monthlyRows = report?.monthly_salary_comparisons || [];
  const monthlyMismatchRows = monthlyRows.filter((row) => row.status !== 'matched');
  const freelanceRows = report?.freelance_comparisons || [];
  const findings = report?.findings || [];
  const documentsById = useMemo(() => {
    const byId = new Map();
    documents.forEach((document) => byId.set(Number(document.id), document));
    return byId;
  }, [documents]);

  function documentFromTaxRow(row) {
    const documentId = Number(row.document_id);
    return documentsById.get(documentId) || {
      id: documentId,
      original_name: row.document_name || taxDocumentLabel(row.source_type),
      document_type: row.source_type,
      status: row.document_status || (row.source_type === 'form26as' && Number(row.is_active || 0) === 0 ? 'superseded' : 'confirmed'),
    };
  }

  function reviewActionForMonthlyRow(row) {
    const documentIds = (row.document_ids || []).filter(Boolean);
    if (documentIds.length === 1) {
      const document = documentsById.get(Number(documentIds[0]));
      if (document && !isTaxDocumentType(document.document_type)) {
        return (
          <button className="btn btn-sm btn-outline-primary" type="button" onClick={() => onReview?.(document)}>
            Open review
          </button>
        );
      }
    }
    return <span className="muted">Manual review</span>;
  }

  return (
    <section className="panel shadow-sm reviewPanel taxReconPanel">
      <h2><ClipboardCheck size={18} /> Form 16 and 26AS <span>{report?.financial_year || ''}</span></h2>
      {!report ? (
        <p className="muted">No tax reconciliation loaded.</p>
      ) : (
        <>
          <div className="taxReconGrid">
            <div className={`taxReconStatus ${active26as ? 'matched' : 'missing'}`}>
              <strong>Active 26AS</strong>
              <span>{active26as ? active26as.document_name : 'Not uploaded for this user and year'}</span>
              {active26as && <small>{active26as.pan || 'PAN unavailable'} · {active26as.financial_year}</small>}
            </div>
            <div className="taxReconStatus">
              <strong>Form 16 employers</strong>
              <span>{form16Sets.length}</span>
              <small>Multiple employers in one FY are supported.</small>
            </div>
            <div className="taxReconStatus">
              <strong>Superseded 26AS</strong>
              <span>{report.superseded_26as?.length || 0}</span>
              <small>Kept for audit history.</small>
            </div>
          </div>

          <div className="taxReconSubsection">
            <h3>Tax Documents</h3>
            <TaxReconTable
              emptyText="No Form 16 or 26AS documents uploaded for this user and year."
              columns={['Document', 'Type', 'Status', 'PAN', 'TAN', 'Uploaded', 'Action']}
              rows={taxDocuments.map((row) => {
                const document = documentFromTaxRow(row);
                const status = row.source_type === 'form26as'
                  ? (Number(row.is_active || 0) === 1 ? 'active' : 'superseded')
                  : (row.document_status || 'saved');
                return [
                  row.document_name || document.original_name,
                  taxDocumentLabel(row.source_type),
                  status,
                  row.pan || '-',
                  row.tan || '-',
                  formatDisplayDate(row.uploaded_at),
                  document.id ? (
                    <button className="btn btn-sm btn-outline-danger" type="button" onClick={() => onRequestDelete?.(document)}>
                      <Trash2 size={15} /> Delete
                    </button>
                  ) : (
                    <span className="muted">Unavailable</span>
                  ),
                ];
              })}
            />
          </div>

          <div className="taxReconSubsection">
            <h3>Employer Salary Match</h3>
            <TaxReconTable
              emptyText="No employer comparison rows."
              columns={['Employer', 'TAN', 'Ledger Salary', 'Form 16 Salary', '26AS Amount', 'Ledger TDS', '26AS TDS', 'Status']}
              rows={employerRows.map((row) => [
                row.employer || 'Employer',
                row.tan || '-',
                currency(row.ledger_salary),
                currency(row.form16_salary),
                currency(row.form26as_amount),
                currency(row.ledger_tds),
                currency(row.form26as_tds),
                row.status,
              ])}
            />
          </div>

          <div className="taxReconSubsection">
            <h3>Monthly Salary Mismatches</h3>
            <TaxReconTable
              emptyText="No month-level salary mismatches between salary slips and 26AS."
              columns={['Month', 'Employer', 'Ledger Salary', '26AS Amount', 'Ledger TDS', '26AS TDS', 'Amount Diff', 'TDS Diff', 'Status', 'Action']}
              rows={monthlyMismatchRows.map((row) => [
                row.month || '-',
                row.employer || row.tan || 'Employer',
                currency(row.ledger_salary),
                currency(row.form26as_amount),
                currency(row.ledger_tds),
                currency(row.form26as_tds),
                currency(row.amount_difference),
                currency(row.tds_difference),
                (row.issues || []).join(', ') || row.status,
                reviewActionForMonthlyRow(row),
              ])}
            />
          </div>

          <div className="taxReconSubsection">
            <h3>Freelance and Professional TDS</h3>
            <TaxReconTable
              emptyText="No freelance/professional 26AS rows."
              columns={['Deductor', 'Section', 'Ledger Receipts', '26AS Amount', 'Ledger TDS', '26AS TDS', 'Status']}
              rows={freelanceRows.map((row) => [
                row.deductor_name || row.tan || 'Deductor',
                (row.sections || []).join(', ') || '-',
                currency(row.ledger_receipts),
                currency(row.form26as_amount),
                currency(row.ledger_tds),
                currency(row.form26as_tds),
                row.status,
              ])}
            />
          </div>

          <div className="taxReconSubsection">
            <h3>Tax Findings</h3>
            <div className="reviewList">
              {findings.map((finding, index) => (
                <div className="reviewRow" key={`${finding.type}-${index}`}>
                  <div>
                    <strong>{finding.message}</strong>
                    <span>{finding.type.replaceAll('_', ' ')}{finding.tan ? ` · ${finding.tan}` : ''}</span>
                  </div>
                  <span className={`badge ${finding.severity === 'warning' ? 'text-bg-warning' : 'text-bg-secondary'}`}>{finding.severity}</span>
                </div>
              ))}
              {findings.length === 0 && <p className="muted">No tax reconciliation findings.</p>}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function TaxReconTable({ columns, rows, emptyText }) {
  if (!rows.length) return <p className="muted">{emptyText}</p>;
  return (
    <div className="taxReconTableWrap">
      <table className="taxReconTable">
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentReviewList({ title, documents, onReview }) {
  return (
    <section className="panel shadow-sm reviewPanel">
      <h2>{title} <span>{documents.length}</span></h2>
      <div className="reviewList">
        {documents.map((doc) => {
          const taxDoc = isTaxDocumentType(doc.document_type);
          return (
            <div className="reviewRow" key={`${title}-${doc.id}`}>
              <div>
                <strong>{doc.original_name}</strong>
                <span>{doc.document_type} - {doc.status}</span>
              </div>
              {taxDoc ? (
                <span className="badge text-bg-secondary">Tax doc</span>
              ) : (
                <button className="btn btn-outline-primary btn-sm" type="button" onClick={() => onReview(doc)}>
                  Review
                </button>
              )}
            </div>
          );
        })}
        {documents.length === 0 && <p className="muted">No items.</p>}
      </div>
    </section>
  );
}

function ValidationReportView({ selectedUser, selectedYear }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!selectedYear) return;
    const params = new URLSearchParams({ user_id: selectedUser || 'all', financial_year: selectedYear });
    api(`/validation-report?${params.toString()}`)
      .then(setReport)
      .catch((loadError) => setError(loadError.message));
  }, [selectedUser, selectedYear]);

  const summary = report?.summary || {};
  return (
    <section className="panel shadow-sm reviewPanel">
      <h2><ClipboardCheck size={18} /> Validation Report <span>{selectedYear}</span></h2>
      {error && <div className="alert alert-danger py-2">{error}</div>}
      <div className="reviewSummary">
        <Metric icon={<ClipboardCheck />} label="Findings" value={summary.total || 0} />
        <Metric icon={<AlertTriangle />} label="Warnings" value={summary.warnings || 0} />
        <Metric icon={<FileText />} label="Info" value={summary.info || 0} />
      </div>
      <div className="reviewList">
        {(report?.findings || []).map((finding, index) => (
          <div className="reviewRow" key={`${finding.type}-${index}`}>
            <div>
              <strong>{finding.message}</strong>
              <span>{finding.type.replaceAll('_', ' ')}{finding.record_date ? ` - ${finding.record_date}` : ''}</span>
            </div>
            <span className={`badge ${finding.severity === 'warning' ? 'text-bg-warning' : 'text-bg-secondary'}`}>{finding.severity}</span>
          </div>
        ))}
        {(report?.findings || []).length === 0 && <p className="muted">No validation findings.</p>}
      </div>
    </section>
  );
}

function UploadQueue({ jobs, documents, onJobClick }) {
  return (
    <section className="uploadQueue shadow-sm">
      {jobs.map((job) => {
        const matchingDoc = documents.find((d) => d.original_name === job.name);
        const isInteractive = job.state === 'needs review' && matchingDoc;
        return (
          <span
            key={job.id}
            className={`uploadJob ${job.state.replace(' ', '-')} ${isInteractive ? 'interactive' : ''}`}
            style={isInteractive ? { cursor: 'pointer' } : undefined}
            title={isInteractive ? "Click to review and fill data manually" : undefined}
            onClick={isInteractive ? () => onJobClick(matchingDoc) : undefined}
            role={isInteractive ? "button" : undefined}
            tabIndex={isInteractive ? 0 : undefined}
          >
            {job.name}: {job.state}
          </span>
        );
      })}
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
      <div className="d-flex gap-2">
        <button className="btn btn-success" type="submit"><Check size={16} /></button>
        <button className="btn btn-outline-secondary" type="button" title="Cancel" onClick={() => { setForm({ name: '', pan: '', aliases: '', profile_hints: '' }); setOpen(false); }}><X size={16} /></button>
      </div>
    </form>
  );
}

function ExpenseForm({ users, selectedUser, onCreated }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ user_id: selectedUser === 'all' ? '' : selectedUser, expense_date: '', category: '', amount: '', gst_amount: '', notes: '' });
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open && selectedUser !== 'all') setForm((current) => ({ ...current, user_id: selectedUser }));
  }, [open, selectedUser]);

  async function submit(event) {
    event.preventDefault();
    setError('');
    try {
      await api('/expenses', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, amount: Number(form.amount), gst_amount: Number(form.gst_amount || 0) }),
      });
      setForm({ user_id: selectedUser === 'all' ? '' : selectedUser, expense_date: '', category: '', amount: '', gst_amount: '', notes: '' });
      setOpen(false);
      await onCreated();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!open) {
    return <button className="btn btn-dark" onClick={() => setOpen(true)}><Plus size={16} /> Expense</button>;
  }

  return (
    <form className="inlineForm" onSubmit={submit}>
      {error && <div className="alert alert-danger py-2">{error}</div>}
      <select className="form-select" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} required>
        <option value="">User</option>
        {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
      </select>
      <input className="form-control" type="date" value={form.expense_date} onChange={(e) => setForm({ ...form, expense_date: e.target.value })} required />
      <input className="form-control" placeholder="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required />
      <input className="form-control" type="number" placeholder="Amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required />
      <input className="form-control" type="number" placeholder="GST claim" value={form.gst_amount} onChange={(e) => setForm({ ...form, gst_amount: e.target.value })} />
      <input className="form-control" placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      <div className="d-flex gap-2">
        <button className="btn btn-success" type="submit"><Check size={16} /></button>
        <button className="btn btn-outline-secondary" type="button" title="Cancel" onClick={() => { setForm({ user_id: selectedUser === 'all' ? '' : selectedUser, expense_date: '', category: '', amount: '', gst_amount: '', notes: '' }); setOpen(false); }}><X size={16} /></button>
      </div>
    </form>
  );
}

function Dashboard({ dashboard, selectedUser, mode, onModeChange, onDrilldown }) {
  if (!dashboard) {
    return <section className="empty">No dashboard data yet.</section>;
  }
  const { summary, tax } = dashboard;
  const allMetrics = [
    { key: 'salary', icon: <IndianRupee />, label: 'Salary income', value: currency(summary.salary_income), onClick: () => onDrilldown('salary') },
    { key: 'freelance', icon: <IndianRupee />, label: 'Freelance income', value: currency(summary.freelance_income), onClick: () => onDrilldown('freelance') },
    { key: 'total-income', icon: <BarChart3 />, label: 'Current total income', value: currency(summary.total_income) },
    { key: 'expenses', icon: <IndianRupee />, label: 'Total expenses', value: currency(summary.total_expenses || summary.freelance_expenses), onClick: () => onDrilldown('expenses') },
    { key: 'gst-input', icon: <IndianRupee />, label: 'GST input claims', value: currency(summary.expense_gst_claims), onClick: () => onDrilldown('gst_input') },
    { key: 'gst-collected', icon: <IndianRupee />, label: 'Total GST collected', value: currency(summary.freelance_gst_collected), onClick: () => onDrilldown('gst_collected') },
    { key: 'standard-deduction', icon: <IndianRupee />, label: 'Salary standard deduction', value: currency(summary.salary_standard_deduction) },
    { key: 'taxable-income', icon: <BarChart3 />, label: 'Taxable income', value: currency(summary.taxable_income) },
    { key: 'estimated-tax', icon: <IndianRupee />, label: `Estimated tax (${tax.regime})`, value: currency(tax.total_tax) },
    { key: 'projected-income', icon: <Calculator />, label: 'Projected annual income', value: currency(tax.predicted_annual_income) },
    { key: 'projected-tax', icon: <Calculator />, label: 'Projected annual tax', value: currency(tax.predicted_total_tax) },
    { key: 'advance-tax', icon: <Calculator />, label: 'Avg. advance tax installment', value: currency(tax.quarterly_advance_tax?.per_quarter) },
    { key: 'tds', icon: <IndianRupee />, label: 'TDS paid', value: currency(tax.tds_paid), onClick: () => onDrilldown('tds') },
    { key: 'pf', icon: <IndianRupee />, label: 'PF', value: currency(summary.pf_total) },
    { key: 'vpf', icon: <IndianRupee />, label: 'VPF', value: currency(summary.vpf_total) },
    { key: 'remaining-tax', icon: <AlertTriangle />, label: 'Remaining tax', value: currency(tax.remaining_tax) },
  ];
  const summaryMetricKeys = new Set(['salary', 'freelance', 'total-income', 'expenses', 'gst-input', 'gst-collected', 'tds', 'remaining-tax']);
  const visibleMetrics = mode === 'detailed' ? allMetrics : allMetrics.filter((metric) => summaryMetricKeys.has(metric.key));

  return (
    <>
      <section className="dashboardHeader">
        <div>
          <h2><BarChart3 size={18} /> Dashboard <span>{dashboard.financial_year}</span></h2>
          <p>Quick overview first. Detailed tax and contribution cards stay available when needed.</p>
        </div>
        <div className="segmentedControl" role="tablist" aria-label="Dashboard card view">
          <button
            className={mode === 'summary' ? 'active' : ''}
            type="button"
            onClick={() => onModeChange('summary')}
          >
            Summary
          </button>
          <button
            className={mode === 'detailed' ? 'active' : ''}
            type="button"
            onClick={() => onModeChange('detailed')}
          >
            Detailed Cards
          </button>
        </div>
      </section>
      <section className="metricGrid">
        {visibleMetrics.map((metric) => (
          <Metric key={metric.key} icon={metric.icon} label={metric.label} value={metric.value} onClick={metric.onClick} />
        ))}
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
              <Bar name="GST" dataKey="gst" fill="url(#gradGst)" radius={[5, 5, 0, 0]} />
              <Bar name="PF" dataKey="pf" fill="url(#gradPf)" radius={[5, 5, 0, 0]} />
              <Bar name="VPF" dataKey="vpf" fill="url(#gradVpf)" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="panel">
          <h2>Tax prediction <span>{tax.assessment_year}</span></h2>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={[
              { 
                name: 'Current', 
                oldRegime: tax.current_options?.old?.total_tax || 0, 
                newRegime: tax.current_options?.new?.total_tax || 0 
              },
              { 
                name: 'Predicted year end', 
                oldRegime: tax.options?.old?.total_tax || 0, 
                newRegime: tax.options?.new?.total_tax || 0 
              },
            ]} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="gradOldRegime" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a855f7" stopOpacity={0.9}/>
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.3}/>
                </linearGradient>
                <linearGradient id="gradNewRegime" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.9}/>
                  <stop offset="95%" stopColor="#059669" stopOpacity={0.3}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="5 5" vertical={false} />
              <XAxis dataKey="name" tickLine={false} />
              <YAxis tickLine={false} axisLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Legend iconType="circle" iconSize={8} />
              <Line name="Old Regime" type="monotone" dataKey="oldRegime" stroke="url(#gradOldRegime)" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
              <Line name="New Regime" type="monotone" dataKey="newRegime" stroke="url(#gradNewRegime)" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
          <TaxComparison tax={tax} />
          <TaxSlabTable rows={tax.slab_rows || []} />
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
      <h3>Advance tax installments</h3>
      <div>
        {rows.map((row) => (
          <span key={row.quarter}>Q{row.quarter} {row.due_date ? `${row.due_date} ` : ''}{currency(row.amount)}</span>
        ))}
      </div>
    </div>
  );
}

function TaxPlannerPanel({ userId, financialYear }) {
  const [planner, setPlanner] = useState(null);
  const [inputs, setInputs] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function loadPlanner() {
    if (!financialYear) return;
    const data = await api(`/tax-planning/${userId}/${encodeURIComponent(financialYear)}`);
    setPlanner(data);
    setInputs(data.inputs || {});
  }

  useEffect(() => {
    loadPlanner().catch((loadError) => setError(loadError.message));
  }, [userId, financialYear]);

  async function saveInputs(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api(`/tax-planning/${userId}/${encodeURIComponent(financialYear)}/inputs`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(inputs),
      });
      await loadPlanner();
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  }

  if (!planner) {
    return <section className="panel shadow-sm reviewPanel"><h2>Tax Planner</h2>{error ? <div className="alert alert-danger py-2">{error}</div> : <p className="muted">Loading planner...</p>}</section>;
  }

  return (
    <section className="panel shadow-sm reviewPanel taxPlanner">
      <h2><ClipboardCheck size={18} /> Tax Planner <span>{planner.itr?.suggested_form}</span></h2>
      {error && <div className="alert alert-danger py-2">{error}</div>}
      <div className="reviewSummary">
        <Metric icon={<IndianRupee />} label="Planned tax" value={currency(planner.tax.total_tax)} />
        <Metric icon={<IndianRupee />} label="Remaining after credits" value={currency(planner.breakdown.remaining_tax_after_credits)} />
        <Metric icon={<IndianRupee />} label="NPS applied" value={currency(planner.breakdown.employer_nps_deduction)} />
        <Metric icon={<FileText />} label="Suggested ITR" value={planner.itr?.suggested_form || '-'} />
      </div>
      <form className="settingsForm" onSubmit={saveInputs}>
        <label>Freelance method
          <select className="form-select" value={inputs.freelance_method || 'actual'} onChange={(event) => setInputs({ ...inputs, freelance_method: event.target.value })}>
            <option value="actual">Actual expenses</option>
            <option value="44ADA">Possible 44ADA</option>
          </select>
        </label>
        <label>Advance tax paid
          <input className="form-control" type="number" min="0" value={inputs.advance_tax_paid || 0} onChange={(event) => setInputs({ ...inputs, advance_tax_paid: Number(event.target.value) })} />
        </label>
        <label className="checkboxLabel">
          <input type="checkbox" checked={Boolean(inputs.employer_nps_enabled)} onChange={(event) => setInputs({ ...inputs, employer_nps_enabled: event.target.checked })} />
          Apply employer NPS only if opted/visible
        </label>
        <label>Employer NPS amount
          <input className="form-control" type="number" min="0" value={inputs.employer_nps_amount || 0} onChange={(event) => setInputs({ ...inputs, employer_nps_amount: Number(event.target.value) })} />
        </label>
        <label>Basic + DA salary
          <input className="form-control" type="number" min="0" value={inputs.basic_da_salary || 0} onChange={(event) => setInputs({ ...inputs, basic_da_salary: Number(event.target.value) })} />
        </label>
        <label>Let-out property interest
          <input className="form-control" type="number" min="0" value={inputs.let_out_property_interest || 0} onChange={(event) => setInputs({ ...inputs, let_out_property_interest: Number(event.target.value) })} />
        </label>
        <div className="settingsActions">
          <button className="btn btn-primary" type="submit" disabled={busy}><Check size={16} /> {busy ? 'Saving...' : 'Save planner inputs'}</button>
        </div>
      </form>
      <div className="reviewToolsGrid">
        <div className="reviewPanel">
          <h3>Recommendations</h3>
          <div className="reviewList">
            {planner.recommendations.map((item, index) => (
              <div className="reviewRow" key={index}>
                <div><strong>{item.title}</strong><span>{item.message}</span></div>
                <span className="badge text-bg-secondary">{item.status}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="reviewPanel">
          <h3>ITR Checklist</h3>
          <div className="reviewList">
            {planner.itr.checklist.map((item) => <div className="reviewRow" key={item}><span>{item}</span></div>)}
          </div>
        </div>
      </div>
    </section>
  );
}

function AiAdvisorPanel({ userId, financialYear, advisor, onInputChange, onClearTokenCount, onRunAnalysis, onSendMessage }) {
  const error = advisor.error || '';
  const aiBusy = advisor.busy || '';
  const aiAnalysis = advisor.analysis || '';
  const aiMessages = advisor.messages || [];
  const aiInput = advisor.input || '';
  const tokenCount = Math.max(0, Number(advisor.tokenCount || 0));

  return (
    <section className="panel shadow-sm reviewPanel aiAdvisorPanel">
      <div className="aiAdvisorHeader">
        <div>
          <h2><MessageSquare size={18} /> AI Advisor <span>{financialYear}</span></h2>
          <p>Optional Cloud AI suggestions for the selected user and financial year. Deterministic tax calculations remain in Tax Planner.</p>
        </div>
        <div className="tokenControls">
          <div className="tokenBadge">Tokens: {tokenCount}</div>
          <button className="btn btn-sm btn-outline-secondary" type="button" onClick={onClearTokenCount} disabled={tokenCount === 0}>
            Clear
          </button>
        </div>
      </div>
      {error && <div className="alert alert-danger py-2">{error}</div>}
      <div className="aiToolbar">
        <span>{userId === 'all' ? 'All users' : `User ${userId}`} - {financialYear}</span>
        <button className="btn btn-outline-primary" type="button" onClick={onRunAnalysis} disabled={Boolean(aiBusy) || !financialYear}>
          <Calculator size={15} /> {aiBusy === 'analysis' ? 'Analyzing...' : 'Run analysis'}
        </button>
      </div>
      {aiAnalysis && <div className="aiAnalysis">{aiAnalysis}</div>}
      <div className="aiChatWindow aiAdvisorChat">
        {aiMessages.length === 0 && !aiBusy && <p className="muted">Run analysis or ask a tax-planning question after configuring Cloud AI in Settings.</p>}
        {aiBusy && <p className="muted">Cloud AI is processing. You can open another module and return here later.</p>}
        {aiMessages.map((message, index) => (
          <div className={`aiMessage ${message.role}`} key={`${message.role}-${index}`}>
            <strong>{message.role === 'user' ? 'You' : 'Cloud AI'}</strong>
            <span>{message.content}</span>
          </div>
        ))}
      </div>
      <form className="aiChatForm" onSubmit={(event) => { event.preventDefault(); onSendMessage(); }}>
        <input
          className="form-control"
          value={aiInput}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="Ask about legal tax planning, ITR readiness, or missing data"
        />
        <button className="btn btn-primary" type="submit" disabled={Boolean(aiBusy) || !aiInput.trim() || !financialYear}>
          {aiBusy === 'chat' ? 'Sending...' : 'Send'}
        </button>
      </form>
    </section>
  );
}

function DrilldownPanel({ type, dashboard, users, onClose, onDeleted }) {
  const records = dashboard?.records || [];
  const expenses = dashboard?.expenses || [];
  const titles = {
    salary: 'Salary records',
    freelance: 'Freelance invoices',
    gst_collected: 'Freelance invoices with GST',
    gst_input: 'Expenses with GST input',
    expenses: 'Expenses',
    tds: 'Records with TDS',
  };
  if (type === 'gst_input' || type === 'expenses') {
    const filtered = type === 'gst_input' ? expenses.filter((item) => Number(item.gst_amount || 0) > 0) : expenses;
    return (
      <section className="panel shadow-sm reviewPanel">
        <h2>{titles[type]} <button className="btn btn-sm btn-outline-secondary" type="button" onClick={onClose}>Close</button></h2>
        <ExpensesPanel expenses={filtered} users={users} onDeleted={onDeleted} />
      </section>
    );
  }
  const filteredRecords = records.filter((record) => {
    if (type === 'salary') return record.income_type === 'salary';
    if (type === 'freelance') return record.income_type === 'freelance_invoice';
    if (type === 'gst_collected') return record.income_type === 'freelance_invoice' && Number(record.gst_amount || 0) > 0;
    if (type === 'tds') return Number(record.tds_amount || 0) > 0;
    return true;
  });
  return (
    <section className="panel shadow-sm reviewPanel">
      <h2>{titles[type] || 'Drilldown'} <button className="btn btn-sm btn-outline-secondary" type="button" onClick={onClose}>Close</button></h2>
      <RecordsPanel records={filteredRecords} onDeleted={onDeleted} />
    </section>
  );
}

function TaxSlabTable({ rows }) {
  if (!rows.length) return null;
  return (
    <div className="tableWrap taxSlabTable">
      <table className="table table-sm align-middle">
        <thead>
          <tr><th>Income range</th><th>Rate</th><th>Taxable</th><th>Tax</th></tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              <td>{currency(row.from)} - {row.to === null ? 'Above' : currency(row.to)}</td>
              <td>{Math.round(row.rate * 100)}%</td>
              <td>{currency(row.taxable_amount)}</td>
              <td>{currency(row.tax)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metric({ icon, label, value, onClick }) {
  const content = (
    <>
      <div className="metricIcon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </>
  );
  if (onClick) {
    return <button className="metric metricButton" type="button" onClick={onClick}>{content}</button>;
  }
  return (
    <div className="metric">
      {content}
    </div>
  );
}

function DocumentPanel({ documents, pendingDocs, onReview, onRequestDelete }) {
  const [openError, setOpenError] = useState('');

  function requestDelete(event, document) {
    event.stopPropagation();
    onRequestDelete(document);
  }

  async function openSourcePdf(event, document) {
    event.stopPropagation();
    setOpenError('');
    try {
      const blob = await apiBlob(`/documents/${document.id}/file`);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setOpenError(error.message);
    }
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
      {openError && <div className="alert alert-danger py-2">{openError}</div>}
      <div className="list">
        {documents.map((doc) => (
          <div className="documentRow" key={doc.id} role="button" tabIndex={0} onClick={(event) => openForReview(event, doc)} onKeyDown={(event) => handleRowKeyDown(event, doc)}>
            <div>
              <strong>
                {doc.original_name}
                {getRealWarnings(doc.warnings).length > 0 && (
                  <AlertTriangle
                    size={16}
                    className="text-warning ms-2 align-middle"
                    title={`Click to review and fix:\n\n${getRealWarnings(doc.warnings).join('\n')}`}
                  />
                )}
              </strong>
              <span>{doc.document_type} · {doc.status} · confidence {Math.round((doc.confidence || 0) * 100)}%</span>
              <button className="linkButton" type="button" onClick={(event) => openSourcePdf(event, doc)}>
                Open source PDF
              </button>
            </div>
            <div className="rowActions" onClick={(event) => event.stopPropagation()}>
              <button className="btn btn-sm btn-outline-danger" type="button" title="Delete document" onClick={(event) => requestDelete(event, doc)}>
                <Trash2 size={15} />
              </button>
            </div>
          </div>
        ))}
        {documents.length === 0 && <p className="muted">Upload a PDF to begin.</p>}
      </div>
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

const EXPENSE_CATEGORIES = [
  'Travel',
  'Software',
  'Hardware',
  'Utilities',
  'Office Supplies',
  'Professional Fees',
  'Rent',
  'Meals',
  'Others'
];

function ReviewModal({ document, users, onClose, onSaved }) {
  const extracted = document.extracted || {};
  const rawExtractedType = extracted.income_type || extracted.document_type || document.document_type || 'freelance_invoice';
  const extractedType = rawExtractedType === 'salary' ? 'salary' : (rawExtractedType === 'purchase_expense' ? 'purchase_expense' : 'freelance_invoice');
  const initialGross = Number(extracted.gross_amount || 0);
  const initialNet = Number(extracted.net_amount || 0);
  const initialTds = Number(extracted.tds_amount || 0);
  const initialGst = Number(extracted.gst_amount || 0);
  const initialTdsVal = extractedType === 'freelance_invoice' && initialTds === 0 ? roundMoney(initialGross * 0.1) : initialTds;
  const [form, setForm] = useState({
    user_id: document.detected_user_id || '',
    income_type: extractedType,
    record_date: extracted.record_date || '',
    payer: extracted.payer || '',
    gross_amount: initialGross,
    net_amount: extractedType === 'freelance_invoice' ? roundMoney(initialGross - initialTdsVal) : (extractedType === 'purchase_expense' ? roundMoney(initialGross + initialGst) : initialNet),
    tds_amount: extractedType === 'purchase_expense' ? 0 : initialTdsVal,
    deductions_amount: extracted.deductions_amount || 0,
    pf_amount: extractedType === 'salary' ? extracted.pf_amount || 0 : 0,
    vpf_amount: extractedType === 'salary' ? extracted.vpf_amount || 0 : 0,
    gst_amount: initialGst,
    category: extracted.category || 'Others',
    notes: extracted.notes || '',
  });
  const [error, setError] = useState('');

  const validationWarnings = useMemo(() => {
    const warnings = [];
    const gross = Number(form.gross_amount || 0);
    const net = Number(form.net_amount || 0);
    const tds = Number(form.tds_amount || 0);
    const pf = Number(form.pf_amount || 0);
    const vpf = Number(form.vpf_amount || 0);
    const deds = Number(form.deductions_amount || 0);

    if (form.income_type === 'salary' && gross > 0) {
      const expectedNet = gross - (pf + vpf + tds + deds);
      if (Math.abs(expectedNet - net) > 10.0) {
        warnings.push({
          type: 'salary_mismatch',
          message: `Gross salary minus deductions and taxes does not match net amount.`,
          expected: expectedNet,
        });
      }
    }
    if (form.income_type === 'freelance_invoice' && gross > 0) {
      const expectedNet = gross - tds;
      if (Math.abs(expectedNet - net) > 10.0) {
        warnings.push({
          type: 'freelance_mismatch',
          message: `Gross freelance income minus TDS does not match net amount.`,
          expected: expectedNet,
        });
      }
      if (tds === 0) {
        warnings.push({
          type: 'no_tds',
          message: "No TDS was recorded for this freelance invoice.",
        });
      }
    }
    if (form.income_type === 'purchase_expense' && gross > 0) {
      const gst = Number(form.gst_amount || 0);
      const expectedNet = gross + gst;
      if (Math.abs(expectedNet - net) > 10.0) {
        warnings.push({
          type: 'expense_mismatch',
          message: `Gross amount plus GST does not match net amount.`,
          expected: expectedNet,
        });
      }
    }
    return warnings;
  }, [form]);

  const allWarnings = useMemo(() => {
    const docWarnings = Array.isArray(document.warnings)
      ? document.warnings
      : (typeof document.warnings === 'string'
          ? (() => {
              try {
                return JSON.parse(document.warnings);
              } catch {
                return [document.warnings];
              }
            })()
          : []);
    const filteredDocWarnings = docWarnings.filter(w =>
      typeof w === 'string' &&
      !w.includes("does not closely match net amount") &&
      !w.includes("does not match net amount") &&
      !w.includes("No TDS was recorded") &&
      !w.includes("plus GST does not closely match")
    );
    const docWarnObjects = filteredDocWarnings.map(w => ({ type: 'info', message: w }));
    return [...docWarnObjects, ...validationWarnings];
  }, [document.warnings, validationWarnings]);

  function applyIncomeType(nextType) {
    setForm((current) => {
      const gross = Number(current.gross_amount || 0);
      const gst = Number(current.gst_amount || 0);
      const tds = nextType === 'freelance_invoice' && Number(current.tds_amount || 0) === 0
        ? roundMoney(gross * 0.1)
        : (nextType === 'freelance_invoice' ? Number(current.tds_amount || 0) : 0);
      return {
        ...current,
        income_type: nextType,
        tds_amount: tds,
        net_amount: nextType === 'freelance_invoice' ? roundMoney(gross - tds) : (nextType === 'purchase_expense' ? roundMoney(gross + gst) : current.net_amount),
        pf_amount: nextType === 'salary' ? current.pf_amount : 0,
        vpf_amount: nextType === 'salary' ? current.vpf_amount : 0,
        gst_amount: nextType === 'salary' ? 0 : gst,
      };
    });
  }

  function updateMoneyField(key, value) {
    const numericValue = Number(value);
    setForm((current) => {
      const next = { ...current, [key]: numericValue };
      const gross = Number(next.gross_amount || 0);
      if (next.income_type === 'freelance_invoice') {
        if (key === 'gross_amount') {
          next.tds_amount = roundMoney(gross * 0.1);
          next.net_amount = roundMoney(gross - next.tds_amount);
        } else if (key === 'tds_amount') {
          next.net_amount = roundMoney(gross - next.tds_amount);
        }
      } else if (next.income_type === 'purchase_expense') {
        const gst = Number(next.gst_amount || 0);
        if (key === 'gross_amount' || key === 'gst_amount') {
          next.net_amount = roundMoney(gross + gst);
        }
        next.tds_amount = 0;
      }
      return next;
    });
  }

  async function submit(event) {
    event.preventDefault();
    setError('');
    try {
      await api(`/extractions/${document.id}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, user_id: Number(form.user_id) }),
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="ledger-modal-backdrop">
      <form className="ledger-modal shadow-lg" onSubmit={submit}>
        <h2>Review extraction</h2>
        <p>{document.original_name}</p>
        {error && <div className="alert alert-danger">{error}</div>}
        <div className="reviewGrid">
          <label>User<select className="form-select" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} required>
            <option value="">Select user</option>
            {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
          </select></label>
          <label>Type<select className="form-select" value={form.income_type} onChange={(e) => applyIncomeType(e.target.value)}>
            <option value="salary">Salary</option>
            <option value="freelance_invoice">Freelance invoice</option>
            <option value="purchase_expense">Expense</option>
          </select></label>
          <label>Date<input className="form-control" type="date" value={form.record_date} onChange={(e) => setForm({ ...form, record_date: e.target.value })} required /></label>
          <label>{form.income_type === 'purchase_expense' ? 'Vendor' : 'Employer / Company'}<input className="form-control" value={form.payer || ''} onChange={(e) => setForm({ ...form, payer: e.target.value })} /></label>
          <label>Gross<input className="form-control" type="number" value={form.gross_amount} onChange={(e) => updateMoneyField('gross_amount', e.target.value)} /></label>
          <label>Net<input className="form-control" type="number" value={form.net_amount} onChange={(e) => updateMoneyField('net_amount', e.target.value)} /></label>
          {form.income_type !== 'purchase_expense' && (
            <label>TDS<input className="form-control" type="number" value={form.tds_amount} onChange={(e) => updateMoneyField('tds_amount', e.target.value)} /></label>
          )}
          {form.income_type === 'salary' ? (
            <>
              <label>Other deductions<input className="form-control" type="number" value={form.deductions_amount} onChange={(e) => updateMoneyField('deductions_amount', e.target.value)} /></label>
              <label>PF<input className="form-control" type="number" value={form.pf_amount} onChange={(e) => updateMoneyField('pf_amount', e.target.value)} /></label>
              <label>VPF<input className="form-control" type="number" value={form.vpf_amount} onChange={(e) => updateMoneyField('vpf_amount', e.target.value)} /></label>
            </>
          ) : form.income_type === 'freelance_invoice' ? (
            <label>GST<input className="form-control" type="number" value={form.gst_amount} onChange={(e) => updateMoneyField('gst_amount', e.target.value)} /></label>
          ) : (
            <>
              <label>GST<input className="form-control" type="number" value={form.gst_amount} onChange={(e) => updateMoneyField('gst_amount', e.target.value)} /></label>
              <label>Category<select className="form-select" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} required>
                {EXPENSE_CATEGORIES.map(cat => <option key={cat} value={cat}>{cat}</option>)}
              </select></label>
              <label className="notesField" style={{ gridColumn: 'span 2' }}>Notes<input className="form-control" value={form.notes || ''} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
            </>
          )}
        </div>
        {allWarnings.length > 0 && (
          <div className="warnings">
            {allWarnings.map((warning, index) => {
              const isMismatch = warning.type === 'salary_mismatch' || warning.type === 'freelance_mismatch' || warning.type === 'expense_mismatch';
              return (
                <div key={index} className="warning-item d-flex align-items-center justify-content-between flex-wrap gap-2">
                  <span>{warning.message}</span>
                  {isMismatch && (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-warning"
                      onClick={() => updateMoneyField('net_amount', warning.expected)}
                      style={{ fontSize: '12px', padding: '4px 8px', borderRadius: '6px' }}
                    >
                      Use calculated Net: {currency(warning.expected)}
                    </button>
                  )}
                </div>
              );
            })}
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


// NewIncomeButton removed and replaced by direct button render at root to avoid containing block bugs

function NewIncomeModal({ users, selectedUser, onClose, onCreated }) {
  const [form, setForm] = useState({
    user_id: selectedUser === 'all' ? '' : selectedUser,
    income_type: 'salary',
    record_date: '',
    payer: '',
    gross_amount: '',
    net_amount: '',
    tds_amount: '',
    deductions_amount: '',
    pf_amount: '',
    vpf_amount: '',
    gst_amount: '',
  });
  const [error, setError] = useState('');

  const validationWarnings = useMemo(() => {
    const warnings = [];
    const gross = Number(form.gross_amount || 0);
    const net = Number(form.net_amount || 0);
    const tds = Number(form.tds_amount || 0);
    const pf = Number(form.pf_amount || 0);
    const vpf = Number(form.vpf_amount || 0);
    const deds = Number(form.deductions_amount || 0);

    if (form.income_type === 'salary' && gross > 0) {
      const expectedNet = gross - (pf + vpf + tds + deds);
      if (Math.abs(expectedNet - net) > 10.0) {
        warnings.push({
          type: 'salary_mismatch',
          message: `Gross salary minus deductions and taxes does not match net amount.`,
          expected: expectedNet,
        });
      }
    }
    if (form.income_type === 'freelance_invoice' && gross > 0) {
      const expectedNet = gross - tds;
      if (Math.abs(expectedNet - net) > 10.0) {
        warnings.push({
          type: 'freelance_mismatch',
          message: `Gross freelance income minus TDS does not match net amount.`,
          expected: expectedNet,
        });
      }
      if (tds === 0) {
        warnings.push({
          type: 'no_tds',
          message: "No TDS was recorded for this freelance invoice.",
        });
      }
    }
    return warnings;
  }, [form]);

  function applyIncomeType(nextType) {
    setForm((current) => {
      const gross = Number(current.gross_amount || 0);
      const gst = Number(current.gst_amount || 0);
      const tds = nextType === 'freelance_invoice' && Number(current.tds_amount || 0) === 0
        ? roundMoney(gross * 0.1)
        : (nextType === 'freelance_invoice' ? Number(current.tds_amount || 0) : 0);
      return {
        ...current,
        income_type: nextType,
        tds_amount: tds,
        net_amount: nextType === 'freelance_invoice' ? roundMoney(gross - tds) : current.net_amount,
        pf_amount: nextType === 'salary' ? current.pf_amount : 0,
        vpf_amount: nextType === 'salary' ? current.vpf_amount : 0,
        gst_amount: nextType === 'salary' ? 0 : gst,
      };
    });
  }

  function updateMoneyField(key, value) {
    setForm((current) => {
      const next = { ...current, [key]: value };
      const gross = Number(next.gross_amount || 0);
      if (next.income_type === 'freelance_invoice') {
        if (key === 'gross_amount') {
          next.tds_amount = roundMoney(gross * 0.1);
          next.net_amount = roundMoney(gross - next.tds_amount);
        } else if (key === 'tds_amount') {
          next.net_amount = roundMoney(gross - Number(next.tds_amount || 0));
        }
      }
      return next;
    });
  }

  async function submit(event) {
    event.preventDefault();
    setError('');
    try {
      await api('/records', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          user_id: Number(form.user_id),
          gross_amount: Number(form.gross_amount || 0),
          net_amount: Number(form.net_amount || 0),
          tds_amount: Number(form.tds_amount || 0),
          deductions_amount: Number(form.deductions_amount || 0),
          pf_amount: Number(form.pf_amount || 0),
          vpf_amount: Number(form.vpf_amount || 0),
          gst_amount: Number(form.gst_amount || 0),
        }),
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="ledger-modal-backdrop">
      <form className="ledger-modal shadow-lg" onSubmit={submit}>
        <h2>Add Manual Income</h2>
        <p>Manually enter details for Salary or Freelance Invoice</p>
        {error && <div className="alert alert-danger">{error}</div>}
        <div className="reviewGrid">
          <label>User<select className="form-select" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} required>
            <option value="">Select user</option>
            {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
          </select></label>
          <label>Type<select className="form-select" value={form.income_type} onChange={(e) => applyIncomeType(e.target.value)}>
            <option value="salary">Salary</option>
            <option value="freelance_invoice">Freelance invoice</option>
          </select></label>
          <label>Date<input className="form-control" type="date" value={form.record_date} onChange={(e) => setForm({ ...form, record_date: e.target.value })} required /></label>
          <label>{form.income_type === 'freelance_invoice' ? 'Client' : 'Employer / Company'}<input className="form-control" value={form.payer || ''} onChange={(e) => setForm({ ...form, payer: e.target.value })} required /></label>
          <label>Gross<input className="form-control" type="number" step="any" value={form.gross_amount} onChange={(e) => updateMoneyField('gross_amount', e.target.value)} required /></label>
          <label>Net<input className="form-control" type="number" step="any" value={form.net_amount} onChange={(e) => updateMoneyField('net_amount', e.target.value)} required /></label>
          <label>TDS<input className="form-control" type="number" step="any" value={form.tds_amount} onChange={(e) => updateMoneyField('tds_amount', e.target.value)} /></label>

          {form.income_type === 'salary' ? (
            <>
              <label>Other deductions<input className="form-control" type="number" step="any" value={form.deductions_amount} onChange={(e) => updateMoneyField('deductions_amount', e.target.value)} /></label>
              <label>PF<input className="form-control" type="number" step="any" value={form.pf_amount} onChange={(e) => updateMoneyField('pf_amount', e.target.value)} /></label>
              <label>VPF<input className="form-control" type="number" step="any" value={form.vpf_amount} onChange={(e) => updateMoneyField('vpf_amount', e.target.value)} /></label>
            </>
          ) : (
            <label>GST<input className="form-control" type="number" step="any" value={form.gst_amount} onChange={(e) => updateMoneyField('gst_amount', e.target.value)} /></label>
          )}
        </div>
        {validationWarnings.length > 0 && (
          <div className="warnings">
            {validationWarnings.map((warning, index) => {
              const isMismatch = warning.type === 'salary_mismatch' || warning.type === 'freelance_mismatch';
              return (
                <div key={index} className="warning-item d-flex align-items-center justify-content-between flex-wrap gap-2">
                  <span>{warning.message}</span>
                  {isMismatch && (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-warning"
                      onClick={() => updateMoneyField('net_amount', warning.expected)}
                      style={{ fontSize: '12px', padding: '4px 8px', borderRadius: '6px' }}
                    >
                      Use calculated Net: {currency(warning.expected)}
                    </button>
                  )}
                </div>
              );
            })}
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



function EditUserModal({ user, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: user.name || '',
    pan: user.pan || '',
    aliases: user.aliases || '',
    profile_hints: user.profile_hints || '',
  });
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    try {
      await api(`/users/${user.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="ledger-modal-backdrop">
      <div className="ledger-modal shadow-lg" style={{ maxWidth: '500px' }}>
        <h2>Edit User</h2>
        <p>Update profile details for {user.name}</p>
        {error && <div className="alert alert-danger">{error}</div>}
        <form onSubmit={submit}>
          <div className="mb-3">
            <label className="form-label">Name</label>
            <input className="form-control w-100" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </div>
          <div className="mb-3">
            <label className="form-label">PAN</label>
            <input className="form-control w-100" value={form.pan} onChange={(e) => setForm({ ...form, pan: e.target.value })} />
          </div>
          <div className="mb-3">
            <label className="form-label">Aliases</label>
            <input className="form-control w-100" value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} placeholder="e.g. Akshay Bhatnagar, Bhatnagar Akshay" />
          </div>
          <div className="mb-3">
            <label className="form-label">Employer/client hints</label>
            <input className="form-control w-100" value={form.profile_hints} onChange={(e) => setForm({ ...form, profile_hints: e.target.value })} placeholder="e.g. GenAQ, Bharti Airtel" />
          </div>
          <div className="d-flex justify-content-end gap-2 mt-4">
            <button className="btn btn-outline-secondary" type="button" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" type="submit">Save Changes</button>
          </div>
        </form>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
