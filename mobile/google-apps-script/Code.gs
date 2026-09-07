const EXPENSE_HEADERS = [
  'entry_id',
  'user_id',
  'user_name',
  'expense_date',
  'financial_year',
  'category',
  'base_amount',
  'gst_rate',
  'amount',
  'gst_amount',
  'payment_method',
  'notes',
  'created_at',
  'sync_status',
  'synced_at',
  'sql_expense_id',
  'sync_error',
];

const USER_HEADERS = ['user_id', 'user_name', 'updated_at'];

function setupIncomeLedger() {
  const properties = PropertiesService.getScriptProperties();
  let spreadsheetId = properties.getProperty('SPREADSHEET_ID');
  let spreadsheet;
  if (spreadsheetId) {
    spreadsheet = SpreadsheetApp.openById(spreadsheetId);
  } else {
    spreadsheet = SpreadsheetApp.create('Income Ledger Mobile Expenses');
    spreadsheetId = spreadsheet.getId();
    properties.setProperty('SPREADSHEET_ID', spreadsheetId);
  }
  let secret = properties.getProperty('SYNC_SECRET');
  if (!secret) {
    secret = `${Utilities.getUuid()}-${Utilities.getUuid()}`;
    properties.setProperty('SYNC_SECRET', secret);
  }
  ensureSheets_(spreadsheet);
  const setupDetails = {
    spreadsheetUrl: spreadsheet.getUrl(),
    syncKey: secret,
    next: 'Deploy this script as a web app, then copy its /exec URL and this sync key into Income Ledger Settings.',
  };
  console.log(JSON.stringify(setupDetails, null, 2));
  // Never return the key: deployed top-level functions can be invoked by the HTML client.
  return 'Setup complete. Copy the spreadsheet URL and sync key from this execution log.';
}

function doGet() {
  ensureConfigured_();
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Income Ledger Mobile')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.DEFAULT);
}

function doPost(event) {
  try {
    ensureConfigured_();
    const request = JSON.parse((event && event.postData && event.postData.contents) || '{}');
    requireSecret_(request.secret);
    let result;
    if (request.action === 'sync_users') {
      result = syncUsers_(request.users || []);
    } else if (request.action === 'list_pending') {
      result = { entries: listPending_() };
    } else if (request.action === 'mark_results') {
      result = markResults_(request.results || []);
    } else {
      throw new Error('Unsupported action.');
    }
    return jsonOutput_({ ok: true, ...result });
  } catch (error) {
    return jsonOutput_({ ok: false, error: String(error.message || error) });
  }
}

function getBootstrapData(secret) {
  ensureConfigured_();
  requireSecret_(secret);
  const spreadsheet = getSpreadsheet_();
  const usersSheet = spreadsheet.getSheetByName('Users');
  const rows = usersSheet.getLastRow() > 1
    ? usersSheet.getRange(2, 1, usersSheet.getLastRow() - 1, USER_HEADERS.length).getDisplayValues()
    : [];
  const pendingCount = countPending_(spreadsheet.getSheetByName('Expenses'));
  return {
    users: rows.filter((row) => row[0]).map((row) => ({ id: Number(row[0]), name: row[1] })),
    pendingCount,
  };
}

function saveExpense(secret, payload) {
  ensureConfigured_();
  requireSecret_(secret);
  const userId = Number(payload.user_id);
  const user = userById_(userId);
  if (!user) throw new Error('Select a valid Income Ledger user. Start the laptop app once if the user list is empty.');
  const expenseDate = String(payload.expense_date || '').trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(expenseDate)) throw new Error('Choose a valid expense date.');
  const category = String(payload.category || '').trim();
  if (!category) throw new Error('Category is required.');
  const baseAmount = roundMoney_(Number(payload.base_amount));
  const gstRate = roundMoney_(Number(payload.gst_rate || 0));
  if (!(baseAmount > 0)) throw new Error('Amount before GST must be greater than zero.');
  if (gstRate < 0 || gstRate > 100) throw new Error('GST rate must be between 0 and 100.');
  const gstAmount = roundMoney_(baseAmount * gstRate / 100);
  const totalAmount = roundMoney_(baseAmount + gstAmount);
  const entryId = Utilities.getUuid();
  const createdAt = new Date().toISOString();
  const row = [
    entryId,
    userId,
    user.name,
    expenseDate,
    financialYearFor_(expenseDate),
    category,
    baseAmount,
    gstRate,
    totalAmount,
    gstAmount,
    String(payload.payment_method || '').trim(),
    String(payload.notes || '').trim(),
    createdAt,
    'PENDING',
    '',
    '',
    '',
  ];
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = getSpreadsheet_().getSheetByName('Expenses');
    sheet.appendRow(row);
    const lastRow = sheet.getLastRow();
    sheet.getRange(lastRow, 7, 1, 4).setNumberFormat('₹#,##0.00');
  } finally {
    lock.releaseLock();
  }
  return { entryId, totalAmount, gstAmount, status: 'PENDING' };
}

function syncUsers_(users) {
  if (!Array.isArray(users)) throw new Error('users must be a list.');
  const sheet = getSpreadsheet_().getSheetByName('Users');
  const rows = users
    .map((user) => [Number(user.id), String(user.name || '').trim(), new Date().toISOString()])
    .filter((row) => Number.isInteger(row[0]) && row[0] > 0 && row[1]);
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    if (sheet.getLastRow() > 1) sheet.getRange(2, 1, sheet.getLastRow() - 1, USER_HEADERS.length).clearContent();
    if (rows.length) sheet.getRange(2, 1, rows.length, USER_HEADERS.length).setValues(rows);
  } finally {
    lock.releaseLock();
  }
  return { user_count: rows.length };
}

function listPending_() {
  const sheet = getSpreadsheet_().getSheetByName('Expenses');
  if (sheet.getLastRow() <= 1) return [];
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, EXPENSE_HEADERS.length).getDisplayValues();
  return rows
    .filter((row) => row[0] && String(row[13]).toUpperCase() !== 'SYNCED')
    .map((row) => {
      const entry = {};
      EXPENSE_HEADERS.forEach((header, index) => { entry[header] = row[index]; });
      entry.user_id = Number(entry.user_id);
      entry.amount = Number(String(entry.amount).replace(/[^0-9.-]/g, ''));
      entry.gst_amount = Number(String(entry.gst_amount).replace(/[^0-9.-]/g, ''));
      return entry;
    });
}

function markResults_(results) {
  if (!Array.isArray(results)) throw new Error('results must be a list.');
  const sheet = getSpreadsheet_().getSheetByName('Expenses');
  if (sheet.getLastRow() <= 1) return { updated_count: 0 };
  const ids = sheet.getRange(2, 1, sheet.getLastRow() - 1, 1).getDisplayValues();
  const rowById = {};
  ids.forEach((row, index) => { if (row[0]) rowById[row[0]] = index + 2; });
  let updatedCount = 0;
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    results.forEach((result) => {
      const rowNumber = rowById[String(result.entry_id || '')];
      if (!rowNumber) return;
      const status = String(result.status || '').toUpperCase() === 'SYNCED' ? 'SYNCED' : 'ERROR';
      sheet.getRange(rowNumber, 14, 1, 4).setValues([[
        status,
        status === 'SYNCED' ? new Date().toISOString() : '',
        status === 'SYNCED' ? result.sql_expense_id || '' : '',
        status === 'ERROR' ? String(result.sync_error || 'Unknown sync error') : '',
      ]]);
      updatedCount += 1;
    });
  } finally {
    lock.releaseLock();
  }
  return { updated_count: updatedCount };
}

function userById_(userId) {
  const sheet = getSpreadsheet_().getSheetByName('Users');
  if (sheet.getLastRow() <= 1) return null;
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, 2).getDisplayValues();
  const row = rows.find((item) => Number(item[0]) === userId);
  return row ? { id: Number(row[0]), name: row[1] } : null;
}

function countPending_(sheet) {
  if (sheet.getLastRow() <= 1) return 0;
  const statuses = sheet.getRange(2, 14, sheet.getLastRow() - 1, 1).getDisplayValues();
  return statuses.filter((row) => String(row[0]).toUpperCase() !== 'SYNCED').length;
}

function ensureConfigured_() {
  const properties = PropertiesService.getScriptProperties();
  if (!properties.getProperty('SPREADSHEET_ID') || !properties.getProperty('SYNC_SECRET')) {
    throw new Error('Run setupIncomeLedger() once from the Apps Script editor.');
  }
  ensureSheets_(getSpreadsheet_());
}

function ensureSheets_(spreadsheet) {
  ensureSheet_(spreadsheet, 'Expenses', EXPENSE_HEADERS);
  ensureSheet_(spreadsheet, 'Users', USER_HEADERS);
  const defaultSheet = spreadsheet.getSheetByName('Sheet1');
  if (defaultSheet && spreadsheet.getSheets().length > 2 && defaultSheet.getLastRow() === 0) {
    spreadsheet.deleteSheet(defaultSheet);
  }
}

function ensureSheet_(spreadsheet, name, headers) {
  let sheet = spreadsheet.getSheetByName(name);
  if (!sheet) sheet = spreadsheet.insertSheet(name);
  const currentHeaders = sheet.getRange(1, 1, 1, headers.length).getDisplayValues()[0];
  if (currentHeaders.join('|') !== headers.join('|')) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }
  sheet.setFrozenRows(1);
  sheet.getRange(1, 1, 1, headers.length)
    .setBackground('#172554')
    .setFontColor('#ffffff')
    .setFontWeight('bold');
  return sheet;
}

function getSpreadsheet_() {
  return SpreadsheetApp.openById(PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID'));
}

function requireSecret_(provided) {
  const expected = PropertiesService.getScriptProperties().getProperty('SYNC_SECRET');
  if (!provided || String(provided) !== expected) throw new Error('Invalid connection key.');
}

function financialYearFor_(isoDate) {
  const parts = isoDate.split('-').map(Number);
  const startYear = parts[1] >= 4 ? parts[0] : parts[0] - 1;
  return `FY ${startYear}-${String(startYear + 1).slice(-2)}`;
}

function roundMoney_(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function jsonOutput_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}
