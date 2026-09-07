# Income Ledger Mobile

This Google Apps Script web app is the Android-friendly expense entry client. It creates and uses a private Google Sheet, while the deployed web app exchanges data with the laptop using a long private sync key.

## Deploy

1. Open `https://script.google.com/home/start` and create a new project named **Income Ledger Mobile**.
2. Replace `Code.gs` with this folder's `Code.gs`, add an HTML file named `Index`, and replace its contents with `Index.html`.
3. In **Project Settings**, enable **Show appsscript.json**, then replace it with this folder's manifest.
4. Run `setupIncomeLedger` once and approve Google's permission prompt. Copy the `spreadsheetUrl` and `syncKey` printed in the execution log. The function deliberately does not return the key to web clients.
5. Choose **Deploy → New deployment → Web app**. Execute as **Me** and allow access to **Anyone**. The Sheet itself remains private; requests without the 256-bit sync key cannot read users or write/read expenses.
6. Copy the deployment URL ending in `/exec`.
7. In the desktop Income Ledger, open **Settings → Google Sheet mobile sync**, paste the `/exec` URL and sync key, enable sync, save, then choose **Sync now**. This also uploads the local user ID/name list for the mobile dropdown.
8. Open the `/exec` URL in Chrome on Android, enter the sync key once, then use Chrome's **Add to Home screen** command.

Do not share the deployment URL together with the sync key. If the key is exposed, delete the `SYNC_SECRET` script property, run `setupIncomeLedger` again, redeploy, and update the desktop setting.
