param([ValidateSet('Inspect','Open')][string]$Action='Inspect')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$result=@{status='not_installed'; signature_valid=$false; firmware=@(); latest=$false; controller_count=0}
try {
    $exe=Join-Path $env:ProgramFiles 'Sony\PlayStationAccessories\PlayStationAccessories.exe'
    if (!(Test-Path -LiteralPath $exe)) {
        $result | ConvertTo-Json -Compress; exit
    }
    # Limit Windows PowerShell type-data compatibility repair to this child process.
    Remove-TypeData -TypeName System.Security.AccessControl.ObjectSecurity -ErrorAction SilentlyContinue
    Import-Module Microsoft.PowerShell.Security -ErrorAction Stop
    $sig=Get-AuthenticodeSignature -LiteralPath $exe
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Sony Interactive Entertainment') {
        $result.status='signature_invalid'; $result | ConvertTo-Json -Compress; exit
    }
    $result.signature_valid=$true
    $result.status='not_running'
    if ($Action -eq 'Open') {
        Start-Process -FilePath $exe -WindowStyle Normal
        $result.status='launched'
        $result | ConvertTo-Json -Compress; exit
    }
    $ids=@(Get-Process -Name PlayStationAccessories -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $exe } | ForEach-Object {$_.Id})
    if ($ids.Count -eq 0) { $result | ConvertTo-Json -Compress; exit }
    $result.status='not_recognized'
    Add-Type -AssemblyName UIAutomationClient
    $root=[System.Windows.Automation.AutomationElement]::RootElement
    $windows=$root.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
    foreach($w in $windows) {
        if ($w.Current.ProcessId -notin $ids) {continue}
        $elements=$w.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
        foreach($e in $elements) {
            $name=$e.Current.Name
            if ($name -match '^(DualSense无线控制器|DualSense wireless controller|DualSense 无线控制器)$') { $result.controller_count++ }
            if ($name -match '^(固件|Firmware)\s+([A-Z]-[0-9]{4})$') { $result.firmware+= $Matches[2] }
            if ($name -match '^(最新|Up to date|Up-to-date)$') { $result.latest=$true }
        }
    }
    if ($result.controller_count -gt 0 -and $result.firmware.Count -gt 0) { $result.status='recognized' }
} catch {
    $result.status='unavailable'
    $result.error='无法读取官方窗口，请打开官方软件、关闭弹窗后重试。'
}
$result | ConvertTo-Json -Compress
