# Generate production secrets on Windows PowerShell.
# Run: powershell -ExecutionPolicy Bypass -File scripts/generate-secrets.ps1
1..4 | ForEach-Object {
  $b = New-Object byte[] 32
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $rng.GetBytes($b)
  -join ($b | ForEach-Object { $_.ToString("x2") })
}
Write-Host "\nUse the 4 lines as: JWT_SECRET, METRICS_TOKEN, OPENEDX_CONNECTOR_HMAC_SECRET/AI_CONNECTOR_HMAC_SECRET, POSTGRES_PASSWORD or another secret."
