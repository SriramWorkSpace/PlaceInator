# Functional smoke test for the PyInstaller onedir spike, driven natively in
# PowerShell rather than through a Python subprocess.Popen chain.
#
# Discovered while building this spike: launching the frozen exe as a
# grandchild of this agent's sandboxed shell tooling (shell -> python.exe ->
# subprocess.Popen(frozen exe)) fails Winsock init with WinError 10106,
# while launching it directly (shell -> Start-Process exe) works cleanly --
# same exe, same environment, only the process-tree depth differs. That's an
# artifact of the sandboxed tool environment, not the packaged app (verified:
# the unfrozen dev entry point launched the same two ways showed the same
# split). This script avoids the chain entirely.

param(
    [Parameter(Mandatory = $true)][string]$ExePath,
    [Parameter(Mandatory = $true)][string]$DataDir
)

$ErrorActionPreference = "Stop"

if (Test-Path $DataDir) { Remove-Item -Recurse -Force $DataDir }
New-Item -ItemType Directory -Path $DataDir | Out-Null

$stdoutFile = Join-Path $env:TEMP "placeinator-spike-stdout.txt"
$stderrFile = Join-Path $env:TEMP "placeinator-spike-stderr.txt"
Remove-Item $stdoutFile, $stderrFile -ErrorAction SilentlyContinue

Write-Output "[1/9] starting $ExePath"
$envVars = @{
    PLACEINATOR_LOG_LEVEL = "info"
    PLACEINATOR_DATA_DIR  = $DataDir
}
foreach ($k in $envVars.Keys) { [Environment]::SetEnvironmentVariable($k, $envVars[$k], "Process") }

$proc = Start-Process -FilePath $ExePath -NoNewWindow -PassThru `
    -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile

try {
    # Get-Content returns a bare string (not a 1-element array) when the file
    # has exactly one line -- $content[0] on a string indexes the first
    # *character*, not the first line. -Raw + regex sidesteps that entirely.
    # exit 1 inside a try/finally does not run the finally block in a
    # -File-invoked script (a real PowerShell gotcha, not a .NET exception),
    # which is exactly how the first version of this script leaked an
    # orphaned, still-downloading child process. throw does trigger finally.
    $deadline = (Get-Date).AddSeconds(60)
    $line = $null
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) {
            throw "process exited before printing a handshake line. stderr:`n$(Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue)"
        }
        $raw = Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue
        if ($raw -match "(?m)^PLACEINATOR_READY.*$") {
            $line = $matches[0]
            break
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $line) {
        throw "no handshake line within 60s. stderr:`n$(Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue)"
    }

    $payload = $line.Substring("PLACEINATOR_READY".Length).Trim() | ConvertFrom-Json
    $base = "http://127.0.0.1:$($payload.port)"
    $headers = @{ Authorization = "Bearer $($payload.token)" }
    Write-Output "[2/9] handshake OK -- port $($payload.port)"

    $health = Invoke-RestMethod -Uri "$base/health" -Method Get
    if ($health.status -ne "ok") { throw "unexpected /health response: $($health | ConvertTo-Json)" }
    Write-Output "[3/9] /health OK"

    $status = Invoke-RestMethod -Uri "$base/api/status" -Method Get -Headers $headers
    if (-not $status.database_ok) { throw "database_ok was false: $($status | ConvertTo-Json)" }
    Write-Output "[4/9] SQLite OK -- $($status.table_count) tables, data_dir=$($status.data_dir)"

    $deadline = (Get-Date).AddSeconds(600)
    $modelStatus = $null
    while ((Get-Date) -lt $deadline) {
        $modelStatus = Invoke-RestMethod -Uri "$base/api/matching/model-status" -Method Get -Headers $headers
        if ($modelStatus.ready) { break }
        Start-Sleep -Seconds 2
    }
    if (-not $modelStatus.ready) { throw "model never became ready: $($modelStatus | ConvertTo-Json)" }
    Write-Output "[5/9] ONNX Runtime + embedding model ready"

    $profileBody = @{ full_name = "Spike Tester"; email = "spike@example.com" } | ConvertTo-Json
    Invoke-RestMethod -Uri "$base/api/profile" -Method Put -Headers $headers `
        -ContentType "application/json" -Body $profileBody | Out-Null
    Write-Output "[6/9] profile created"

    $resumeTex = @"
\documentclass{article}
\begin{document}
Jane Doe
\section{Skills}
Python, FastAPI, PostgreSQL, Docker, Kubernetes
\section{Experience}
\begin{itemize}
\item Built a backend service in Python and FastAPI handling 10k requests/sec
\item Deployed services to Kubernetes and ran CI/CD pipelines
\end{itemize}
\end{document}
"@

    $boundary = [System.Guid]::NewGuid().ToString()
    $LF = "`r`n"
    $bodyLines = (
        "--$boundary",
        "Content-Disposition: form-data; name=`"label`"$LF",
        "SDE",
        "--$boundary",
        "Content-Disposition: form-data; name=`"source_format`"$LF",
        "tex",
        "--$boundary",
        "Content-Disposition: form-data; name=`"is_primary`"$LF",
        "true",
        "--$boundary",
        "Content-Disposition: form-data; name=`"file`"; filename=`"resume.tex`"",
        "Content-Type: text/plain$LF",
        $resumeTex,
        "--$boundary--$LF"
    ) -join $LF

    $resume = Invoke-RestMethod -Uri "$base/api/resumes" -Method Post -Headers $headers `
        -ContentType "multipart/form-data; boundary=$boundary" -Body $bodyLines
    if ($resume.chunk_count -le 0) { throw "resume produced no chunks -- embedding likely failed" }
    Write-Output "[7/9] resume embedded -- $($resume.chunk_count) chunks (real ONNX inference)"

    $jobBody = @{
        company     = "Acme"
        designation = "Backend Engineer"
        description = "Python, FastAPI, Kubernetes"
        location    = $null
        url         = $null
        deadline    = $null
    } | ConvertTo-Json
    $job = Invoke-RestMethod -Uri "$base/api/jobs/manual" -Method Post -Headers $headers `
        -ContentType "application/json" -Body $jobBody

    $matchResults = Invoke-RestMethod -Uri "$base/api/matching/jobs/$($job.id)/rank-resumes" -Method Post -Headers $headers
    if (-not $matchResults -or $matchResults[0].resume_id -ne $resume.id) { throw "unexpected match result: $($matchResults | ConvertTo-Json)" }
    Write-Output "[8/9] real match computed -- semantic_score=$($matchResults[0].semantic_score)"

    Write-Output "[9/9] shutting down"
    Stop-Process -Id $proc.Id -Force
    Start-Sleep -Seconds 1

    Write-Output ""
    Write-Output "ALL CHECKS PASSED"
    exit 0
}
catch {
    Write-Output "[FAIL] $_"
    Write-Output $_.ScriptStackTrace
    exit 1
}
finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
}
