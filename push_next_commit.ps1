# EvalProof scheduled commit publisher.
#
# Publishes the current source branch's pending commits to the remote main branch
# in a five-day window. The script never checks out or mutates the source working
# tree; it builds the next batch in a temporary git worktree instead.

[CmdletBinding()]
param(
    [string]$Repository = "C:\Users\Mert\Documents\EvalProof",
    [string]$Remote = "origin",
    [string]$RemoteBranch = "main",
    [int]$Days = 5,
    [string]$StatePath = "",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Days -lt 1) { throw "Days must be at least 1." }

$Repository = (Resolve-Path -LiteralPath $Repository).Path
if ([string]::IsNullOrWhiteSpace($StatePath)) {
    $stateDirectory = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "EvalProof"
    $StatePath = Join-Path $stateDirectory "commit-schedule.json"
}
$StatePath = [IO.Path]::GetFullPath($StatePath)

function Invoke-Git {
    param(
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )
    $output = @(& git -C $Path @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        $details = ($output -join [Environment]::NewLine).Trim()
        throw "git $($Arguments -join ' ') failed in '$Path'. $details"
    }
    return $output
}

function Get-TrimmedLines {
    param([object[]]$Lines)
    return @($Lines | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ })
}

function Write-State {
    param([object]$State)
    $directory = Split-Path -Parent $StatePath
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temporaryPath = "$StatePath.tmp"
    $State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporaryPath -Encoding UTF8
    Move-Item -LiteralPath $temporaryPath -Destination $StatePath -Force
}

function Read-State {
    if (-not (Test-Path -LiteralPath $StatePath)) { return $null }
    return Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
}

function New-State {
    param(
        [string]$SourceBranch,
        [string[]]$Commits
    )
    return [pscustomobject]@{
        version = 1
        repository = $Repository
        remote = $Remote
        remote_branch = $RemoteBranch
        source_branch = $SourceBranch
        start_date = (Get-Date).Date.ToString("yyyy-MM-dd")
        days = $Days
        cycle_commits = @($Commits)
        completed_commits = @()
    }
}

function Get-CommitList {
    param([string]$SourceBranch)
    $range = "$Remote/$RemoteBranch..$SourceBranch"
    return Get-TrimmedLines (Invoke-Git $Repository @("rev-list", "--reverse", $range))
}

function Get-TargetCompleted {
    param(
        [int]$Total,
        [int]$Completed,
        [int]$ElapsedDays,
        [int]$WindowDays
    )
    if ($Completed -ge $Total) { return $Total }
    $dayNumber = [Math]::Min($WindowDays, $ElapsedDays + 1)
    return [Math]::Ceiling($Total * $dayNumber / [double]$WindowDays)
}

Push-Location $Repository
$temporaryRepository = $null
$temporaryWorktree = $null
try {

    $sourceBranch = Get-TrimmedLines (Invoke-Git $Repository @("branch", "--show-current")) | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($sourceBranch)) {
        throw "The repository is in detached HEAD state. Run the scheduler from a named source branch."
    }

    $state = Read-State
    if ($null -ne $state) {
        if ($state.repository -ne $Repository -or
            $state.remote -ne $Remote -or
            $state.remote_branch -ne $RemoteBranch -or
            $state.source_branch -ne $sourceBranch) {
            throw "Existing schedule state belongs to another repository, remote, branch, or source branch: $StatePath"
        }
        if ([int]$state.days -ne $Days) {
            throw "Existing schedule uses $($state.days) days, but this run requested $Days days: $StatePath"
        }
    }

    $currentCandidates = @(Get-CommitList $sourceBranch)
    $completedHistory = @()
    if ($null -ne $state -and $null -ne $state.completed_commits) {
        $completedHistory = @($state.completed_commits | ForEach-Object { $_.ToString() })
    }

    if ($null -eq $state) {
        $state = New-State $sourceBranch $currentCandidates
        Write-State $state
    } else {
        $cycleCommits = @($state.cycle_commits | ForEach-Object { $_.ToString() })
        $cycleCompleted = @($state.completed_commits | ForEach-Object { $_.ToString() })
        $remainingInCycle = @($cycleCommits | Where-Object { $_ -notin $cycleCompleted })

        if ($remainingInCycle.Count -eq 0) {
            $newCandidates = @($currentCandidates | Where-Object { $_ -notin $completedHistory })
            if ($newCandidates.Count -gt 0) {
                $state = New-State $sourceBranch $newCandidates
                $state.completed_commits = @($completedHistory)
                Write-State $state
            } else {
                Write-Host "No pending commits. All source commits are already scheduled and published." -ForegroundColor Yellow
                exit 0
            }
        }
    }

    $cycleCommits = @($state.cycle_commits | ForEach-Object { $_.ToString() })
    $cycleCompleted = @($state.completed_commits | ForEach-Object { $_.ToString() })
    $completedInCycle = @($cycleCommits | Where-Object { $_ -in $cycleCompleted })
    $remaining = @($cycleCommits | Where-Object { $_ -notin $cycleCompleted })

    if ($remaining.Count -eq 0) {
        Write-Host "No pending commits in the current schedule." -ForegroundColor Yellow
        exit 0
    }

    $startDate = [DateTime]::ParseExact($state.start_date, "yyyy-MM-dd", $null).Date
    $elapsedDays = [Math]::Max(0, ((Get-Date).Date - $startDate).Days)
    $targetCompleted = Get-TargetCompleted $cycleCommits.Count $completedInCycle.Count $elapsedDays $Days
    $quota = [Math]::Min($remaining.Count, [Math]::Max(0, $targetCompleted - $completedInCycle.Count))

    if ($quota -le 0) {
        Write-Host "Today's quota is already complete. Remaining commits: $($remaining.Count)." -ForegroundColor Yellow
        exit 0
    }

    $batch = @($remaining | Select-Object -First $quota)
    Write-Host "Schedule: day $([Math]::Min($Days, $elapsedDays + 1))/$Days; publishing $($batch.Count) of $($remaining.Count) remaining commit(s)." -ForegroundColor Cyan
    foreach ($commit in $batch) {
        $message = (Invoke-Git $Repository @("show", "-s", "--format=%s", $commit) | Select-Object -First 1).ToString().Trim()
        Write-Host "  $($commit.Substring(0, 8)) $message"
    }

    if ($DryRun) {
        Write-Host "Dry run: no commits were created and nothing was pushed." -ForegroundColor Yellow
        exit 0
    }

    $temporaryRepository = Join-Path ([IO.Path]::GetTempPath()) ("evalproof-source-" + [Guid]::NewGuid().ToString("N"))
    $temporaryWorktree = Join-Path ([IO.Path]::GetTempPath()) ("evalproof-push-" + [Guid]::NewGuid().ToString("N"))
    $sourceHead = Get-TrimmedLines (Invoke-Git $Repository @("rev-parse", $sourceBranch)) | Select-Object -First 1    $remoteUrl = Get-TrimmedLines (Invoke-Git $Repository @("remote", "get-url", $Remote)) | Select-Object -First 1
    Invoke-Git $Repository @("clone", "--no-local", $Repository, $temporaryRepository) | Out-Null
    Invoke-Git $temporaryRepository @("remote", "set-url", $Remote, $remoteUrl) | Out-Null
    Invoke-Git $temporaryRepository @("branch", "--force", $sourceBranch, $sourceHead) | Out-Null
    Invoke-Git $temporaryRepository @("fetch", $Remote, $RemoteBranch) | Out-Null
    Invoke-Git $temporaryRepository @("worktree", "add", "--detach", $temporaryWorktree, "$Remote/$RemoteBranch") | Out-Null

    try {
        foreach ($commit in $batch) {
            Invoke-Git $temporaryWorktree @("cherry-pick", "--no-commit", $commit) | Out-Null
            $now = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
            $env:GIT_AUTHOR_DATE = $now
            $env:GIT_COMMITTER_DATE = $now
            try {
                Invoke-Git $temporaryWorktree @("commit", "--no-verify", "--allow-empty", "-C", $commit, "--date=$now") | Out-Null
            } finally {
                Remove-Item Env:GIT_AUTHOR_DATE -ErrorAction SilentlyContinue
                Remove-Item Env:GIT_COMMITTER_DATE -ErrorAction SilentlyContinue
            }
        }
        Invoke-Git $temporaryWorktree @("push", $Remote, "HEAD:refs/heads/$RemoteBranch") | Out-Null
    } catch {
        & git -C $temporaryWorktree cherry-pick --abort 2>$null | Out-Null
        throw
    } finally {
        Invoke-Git $temporaryRepository @("worktree", "remove", "--force", $temporaryWorktree) | Out-Null
        Remove-Item -LiteralPath $temporaryRepository -Recurse -Force
        $temporaryWorktree = $null
        $temporaryRepository = $null
    }

    $updatedCompleted = @($completedHistory + $batch | Select-Object -Unique)
    $state.completed_commits = @($updatedCompleted)
    Write-State $state
    $remainingAfter = $cycleCommits.Count - $batch.Count - $completedInCycle.Count
    Write-Host "SUCCESS: published $($batch.Count) commit(s). Remaining in this five-day cycle: $remainingAfter." -ForegroundColor Green
} finally {
    if ($null -ne $temporaryWorktree -and $null -ne $temporaryRepository -and (Test-Path -LiteralPath $temporaryWorktree)) {
        & git -C $temporaryRepository worktree remove --force $temporaryWorktree 2>$null | Out-Null
    }
    if ($null -ne $temporaryRepository -and (Test-Path -LiteralPath $temporaryRepository)) {
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        $resolvedTemporaryRepository = (Resolve-Path -LiteralPath $temporaryRepository).Path
        if ($resolvedTemporaryRepository.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTemporaryRepository -Recurse -Force
        }
    }
    Pop-Location
}
