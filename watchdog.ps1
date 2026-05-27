$streamlit = 'C:\Users\USER\AppData\Local\Programs\Python\Python312\Scripts\streamlit.exe'
$app       = 'C:\Users\USER\stock_analyzer\app.py'
$workdir   = 'C:\Users\USER\stock_analyzer'
$logfile   = 'C:\Users\USER\stock_analyzer\watchdog.log'

$proc = Get-Process -Name streamlit -ErrorAction SilentlyContinue
if (-not $proc) {
    Start-Process -FilePath $streamlit -ArgumentList 'run',$app,'--server.port','8501','--server.headless','true' -WorkingDirectory $workdir -WindowStyle Hidden
    Add-Content $logfile "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] STARTED"
} else {
    Add-Content $logfile "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] RUNNING PID=$($proc.Id)"
}
