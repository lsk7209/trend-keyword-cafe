$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"
$LogPath = Join-Path $LogDir "daily_pipeline.log"
$ExportPath = "public\data\summary.json"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

Set-Location $ProjectRoot
$startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $LogPath -Value "[$startedAt] pipeline start"

try {
    & $PythonPath "scripts\run_pipeline.py" *>> $LogPath
    if ($LASTEXITCODE -ne 0) {
        throw "pipeline exited with code $LASTEXITCODE"
    }
    & $PythonPath "scripts\export_static_dashboard.py" *>> $LogPath
    if ($LASTEXITCODE -ne 0) {
        throw "export exited with code $LASTEXITCODE"
    }
    git add $ExportPath *>> $LogPath
    $ChangedFiles = git diff --cached --name-only -- $ExportPath
    if ($ChangedFiles) {
        $CommitDate = Get-Date -Format "yyyy-MM-dd"
        git commit -m "Update static dashboard data $CommitDate" *>> $LogPath
        if ($LASTEXITCODE -ne 0) {
            throw "git commit exited with code $LASTEXITCODE"
        }
        git push *>> $LogPath
        if ($LASTEXITCODE -ne 0) {
            throw "git push exited with code $LASTEXITCODE"
        }
        Add-Content -Path $LogPath -Value "[$CommitDate] static dashboard data pushed"
    } else {
        git reset -- $ExportPath *>> $LogPath
        Add-Content -Path $LogPath -Value "static dashboard data unchanged"
    }
    $finishedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogPath -Value "[$finishedAt] pipeline success"
} catch {
    $failedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogPath -Value "[$failedAt] pipeline failed: $($_.Exception.Message)"
    throw
}
