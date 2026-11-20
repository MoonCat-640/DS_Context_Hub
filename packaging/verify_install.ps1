#Requires -RunAsAdministrator
param(
    [string]$Setup = (Join-Path $PSScriptRoot '..\release\Setup.exe'),
    [switch]$ReviewWizard
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$testRoot = Join-Path $projectRoot 'build\install-verification'
$setupPath = (Resolve-Path -LiteralPath $Setup).Path
$appKey = 'Software\MoonCat-640\DS Context Hub'
$uninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\DSContextHub'
$results = [Collections.Generic.List[object]]::new()
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null

function Get-StoredPath([string]$EnvironmentKey) {
    if (Test-Path -LiteralPath $EnvironmentKey) {
        return (Get-Item -LiteralPath $EnvironmentKey).GetValue('Path', $null, 'DoNotExpandEnvironmentNames')
    }
}

function Invoke-CheckedProcess([string]$File, [string]$Arguments) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(180000)) {
        throw "Timed out waiting for $File"
    }
    if ($process.ExitCode -ne 0) {
        throw "$File exited with code $($process.ExitCode)"
    }
}

try {
    foreach ($hive in @('HKCU', 'HKLM')) {
        if (Test-Path -LiteralPath "${hive}:\$appKey") {
            throw "An existing installation is registered in $hive. Use a clean Windows account or VM for this verification."
        }
    }
    if ($ReviewWizard) {
        @{state = 'reviewing-wizard'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testRoot 'progress.json') -Encoding UTF8
        $wizard = Start-Process -FilePath $setupPath -PassThru
        $wizard.WaitForExit()
    }
    foreach ($scope in @('CurrentUser', 'AllUsers')) {
        @{state = 'installing'; scope = $scope} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testRoot 'progress.json') -Encoding UTF8
        $directory = Join-Path $testRoot "$scope 中文 test"
        if (Test-Path -LiteralPath $directory) {
            throw "The verification directory already exists: $directory"
        }
        $hive = 'HKCU'
        $environmentKey = 'Environment'
        $programs = [Environment]::GetFolderPath('Programs')
        $desktop = [Environment]::GetFolderPath('DesktopDirectory')
        if ($scope -eq 'AllUsers') {
            $hive = 'HKLM'
            $environmentKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
            $programs = [Environment]::GetFolderPath('CommonPrograms')
            $desktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
        }
        $environmentKey = "${hive}:\$environmentKey"
        $beforePath = Get-StoredPath $environmentKey
        $startLink = Join-Path $programs 'DS Context Hub\DS Context Hub.lnk'
        $desktopLink = Join-Path $desktop 'DS Context Hub.lnk'
        if ((Test-Path -LiteralPath $startLink) -or (Test-Path -LiteralPath $desktopLink)) {
            throw 'Existing shortcuts must be preserved. Use a clean Windows account or VM for verification.'
        }
        Invoke-CheckedProcess $setupPath "/S /$scope /D=$directory"
        $application = Join-Path $directory 'ds_context_hub.exe'
        $installedPath = Get-ItemPropertyValue -LiteralPath "${hive}:\$appKey" -Name InstallLocation
        if ($installedPath -ne $directory) { throw 'Incorrect installation location in registry' }
        if (-not (Test-Path -LiteralPath "${hive}:\$uninstallKey")) { throw 'Missing uninstall registration' }
        $shell = New-Object -ComObject WScript.Shell
        foreach ($shortcut in @($startLink, $desktopLink)) {
            if ($shell.CreateShortcut($shortcut).TargetPath -ne $application) { throw 'Incorrect shortcut target' }
        }
        if ((Get-StoredPath $environmentKey) -cne $beforePath) { throw 'The default installation changed PATH' }
        $report = Join-Path $testRoot "$scope-self-test.json"
        Start-Process -FilePath $startLink -ArgumentList "--self-test `"$report`"" -WindowStyle Hidden
        for ($attempt = 0; $attempt -lt 120 -and -not (Test-Path -LiteralPath $report); $attempt++) {
            Start-Sleep -Milliseconds 500
        }
        $selfTest = Get-Content -Raw -LiteralPath $report | ConvertFrom-Json
        if (-not $selfTest.ok -or -not $selfTest.frozen) { throw "Installed application self-test failed: $($selfTest.error)" }
        foreach ($process in (Get-Process -Name ds_context_hub -ErrorAction SilentlyContinue)) {
            if ($process.Path -eq $application -and -not $process.WaitForExit(30000)) { throw 'The self-test did not exit' }
        }
        Invoke-CheckedProcess $setupPath "/S /$scope /AddToPath /D=$directory"
        $duringPath = Get-StoredPath $environmentKey
        if (($duringPath -split ';') -notcontains $directory) { throw 'Missing optional PATH entry' }
        # Reinstall to confirm existing PATH entries are not duplicated.
        Invoke-CheckedProcess $setupPath "/S /$scope /AddToPath /D=$directory"
        $afterReinstall = Get-StoredPath $environmentKey
        if ($afterReinstall -ne $duringPath) { throw 'Reinstallation changed PATH unexpectedly' }
        $retainedFile = Join-Path $directory 'user-created.txt'
        'This synthetic user file must survive uninstall.' | Set-Content -LiteralPath $retainedFile -Encoding UTF8
        Invoke-CheckedProcess (Join-Path $directory 'Uninstall.exe') "/S /$scope"
        for ($attempt = 0; $attempt -lt 120; $attempt++) {
            if (-not (Test-Path -LiteralPath $application) -and -not (Test-Path -LiteralPath "${hive}:\$appKey")) { break }
            Start-Sleep -Milliseconds 500
        }
        if (Test-Path -LiteralPath $application) { throw 'Uninstall left the application executable behind' }
        if (-not (Test-Path -LiteralPath $retainedFile)) { throw 'Uninstall deleted a user-created file' }
        if ((Test-Path -LiteralPath $startLink) -or (Test-Path -LiteralPath $desktopLink)) { throw 'Uninstall left shortcuts behind' }
        if ((Test-Path -LiteralPath "${hive}:\$appKey") -or (Test-Path -LiteralPath "${hive}:\$uninstallKey")) {
            throw 'Uninstall left application registration behind'
        }
        $afterPath = Get-StoredPath $environmentKey
        if ($afterPath -ne $beforePath) { throw 'Uninstall did not restore the original PATH' }
        $results.Add(@{scope = $scope; ok = $true; directory = $directory})
    }
    @{ok = $true; checks = $results} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $testRoot 'result.json') -Encoding UTF8
} catch {
    @{ok = $false; checks = $results; error = $_.Exception.Message} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $testRoot 'result.json') -Encoding UTF8
    Write-Host $_.Exception.Message
    exit 1
}
