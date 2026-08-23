# EvalProof - Daily Commit Pusher & Green Dot Generator for Windows Task Scheduler
# Pushes the next local feature commit to GitHub, updating its date to TODAY so GitHub registers a green contribution dot.

Set-Location "c:\Users\Mert\Documents\EvalProof"

# Fetch latest remote tracking info
git fetch origin main 2>$null

$unpushedCommits = (git log --reverse --format="%H" origin/main..HEAD)

if ($unpushedCommits) {
    $nextCommit = if ($unpushedCommits -is [array]) { $unpushedCommits[0] } else { $unpushedCommits }
    $commitMsg = (git log -1 --format="%s" $nextCommit)

    Write-Host "Updating commit '$commitMsg' date to TODAY and pushing..." -ForegroundColor Green

    # Create temporary branch from origin/main to safely re-date and push
    git checkout -B temp_daily_push origin/main 2>$null
    git cherry-pick $nextCommit 2>$null

    # Re-date the commit author and committer date to NOW (Today)
    $nowIso = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    $env:GIT_AUTHOR_DATE = $nowIso
    $env:GIT_COMMITTER_DATE = $nowIso

    git commit --amend --no-edit --date="$nowIso" 2>$null

    # Push to GitHub main branch
    git push origin temp_daily_push:refs/heads/main

    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS: Feature commit '$commitMsg' pushed with today's date! Green dot registered." -ForegroundColor Green
        # Rebase main branch onto updated origin/main and clean temp branch
        git checkout main 2>$null
        git rebase origin/main 2>$null
        git branch -D temp_daily_push 2>$null
    } else {
        Write-Host "ERROR: Push failed with exit code $LASTEXITCODE" -ForegroundColor Red
        git checkout main 2>$null
        git branch -D temp_daily_push 2>$null
    }
} else {
    Write-Host "All local commits are already pushed to GitHub!" -ForegroundColor Yellow
}
