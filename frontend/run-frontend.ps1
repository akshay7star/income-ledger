$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $Root "frontend")
& npm.cmd run dev -- --host 127.0.0.1 --port 5173
