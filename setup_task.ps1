# タスクスケジューラに常駐監視タスクを登録するスクリプト
$taskName = "HiyoLabMonitor"
$pythonPath = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)?.Source
if (-not $pythonPath) {
    # pythonw が見つからない場合は python を使用
    $pythonPath = (Get-Command python.exe).Source
}
$scriptPath = "C:\Users\jun_0\Desktop\Claude\monitor.py"
$workingDir = "C:\Users\jun_0\Desktop\Claude"

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument "`"$scriptPath`"" `
    -WorkingDirectory $workingDir

# PC起動時に実行、ログインしていなくても動作
$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `  # 時間制限なし
    -RestartCount 3 `                          # クラッシュ時3回リトライ
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

# 既存タスクがあれば削除
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "濱岸ひより fanpla コミュニティ監視"

Write-Host "タスク登録完了: $taskName"
Write-Host "今すぐ開始しますか？"
Start-ScheduledTask -TaskName $taskName
Write-Host "監視を開始しました（バックグラウンドで動作中）"
