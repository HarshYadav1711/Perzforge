# Quick API smoke test for local dev (PowerShell).
# Usage:
#   $env:ADMIN_EMAIL="you@example.com"
#   $env:ADMIN_PASSWORD="your-password"
#   .\scripts\dev-api.ps1
#   .\scripts\dev-api.ps1 -Action submit   # POST a hello-world job

param(
    [string]$BaseUrl = "http://127.0.0.1:8000/api/v1",
    [ValidateSet("health", "login", "jobs", "submit")]
    [string]$Action = "jobs",
    [string]$Email = $env:ADMIN_EMAIL,
    [string]$Password = $env:ADMIN_PASSWORD
)

function Get-AccessToken {
    param([string]$UserEmail, [string]$UserPassword)
    if (-not $UserEmail -or -not $UserPassword) {
        throw "Set ADMIN_EMAIL and ADMIN_PASSWORD environment variables first."
    }
    $body = @{ email = $UserEmail; password = $UserPassword } | ConvertTo-Json -Compress
    $login = Invoke-RestMethod -Uri "$BaseUrl/auth/login" -Method Post -ContentType "application/json" -Body $body
    return $login.access_token
}

function Invoke-Login {
    param([string]$UserEmail, [string]$UserPassword)
    try {
        return Get-AccessToken -UserEmail $UserEmail -UserPassword $UserPassword
    } catch {
        $detail = $null
        if ($_.ErrorDetails.Message) {
            try { $detail = ($_.ErrorDetails.Message | ConvertFrom-Json).detail } catch { }
        }
        if ($detail -eq "Invalid email or password") {
            Write-Error @"
Login failed: no matching user or wrong password.
If this is a fresh setup, bootstrap the first admin first:
  `$env:ADMIN_EMAIL='you@example.com'
  `$env:ADMIN_PASSWORD='your-password'
  python scripts/create_admin.py
"@
        }
        throw
    }
}

switch ($Action) {
    "health" {
        Invoke-RestMethod -Uri "$BaseUrl/healthz"
    }
    "login" {
        $token = Invoke-Login -UserEmail $Email -UserPassword $Password
        [PSCustomObject]@{ access_token = $token }
    }
    "jobs" {
        $token = Invoke-Login -UserEmail $Email -UserPassword $Password
        $headers = @{ Authorization = "Bearer $token" }
        Invoke-RestMethod -Uri "$BaseUrl/jobs" -Headers $headers
    }
    "submit" {
        $token = Invoke-Login -UserEmail $Email -UserPassword $Password
        $headers = @{ Authorization = "Bearer $token" }
        $jobBody = @{
            name = "hello"
            spec = @{
                image = "python:3.12-alpine"
                command = @("python", "-c", "print('hello from perzforge')")
                env = @{}
                gpu = $false
                timeout_minutes = 5
            }
        } | ConvertTo-Json -Depth 6 -Compress
        Invoke-RestMethod -Uri "$BaseUrl/jobs" -Method Post -ContentType "application/json" -Headers $headers -Body $jobBody
    }
}
