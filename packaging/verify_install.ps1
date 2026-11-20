#Requires -RunAsAdministrator
# 供干净的 Windows 测试机使用。真实运行安装与卸载，结果写入 build/install-verification。
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
    # 比较注册表原值，便于检查 %SystemRoot% 等变量以及原有空条目是否得以保留。
    if (Test-Path -LiteralPath $EnvironmentKey) {
        return (Get-Item -LiteralPath $EnvironmentKey).GetValue('Path', $null, 'DoNotExpandEnvironmentNames')
    }
}

function Test-InstalledShortcut([string]$Link, [string]$Application, [string]$Report) {
    # 通过实际 .lnk 发起自检，并从新进程的报告确认启动的是此次安装的程序。
    if (-not (Test-Path -LiteralPath $Link -PathType Leaf)) { throw "Missing shortcut: $Link" }
    $shell = New-Object -ComObject Shell.Application
    $folder = $shell.NameSpace([IO.Path]::GetDirectoryName($Link))
    $target = $folder.ParseName([IO.Path]::GetFileName($Link)).GetLink.Path
    Write-Host "Launching $Link (shell target: $target)"
    Start-Process -FilePath $Link -ArgumentList "--self-test `"$Report`"" -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 120 -and -not (Test-Path -LiteralPath $Report); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-Path -LiteralPath $Report)) { throw "No self-test report from shortcut $Link (target: $target)" }
    $selfTest = Get-Content -Raw -LiteralPath $Report | ConvertFrom-Json
    if (-not $selfTest.ok -or -not $selfTest.frozen) { throw "Installed application self-test failed: $($selfTest.error)" }
    if ($selfTest.executable -ne $Application) { throw "Shortcut $Link launched $($selfTest.executable), expected $Application" }
    # 报告写完时 Qt 可能还在退出，等待程序释放 exe 后才能测试重装。
    foreach ($process in (Get-Process -Name ds_context_hub -ErrorAction SilentlyContinue)) {
        if ($process.Path -eq $Application -and -not $process.WaitForExit(30000)) { throw 'The self-test did not exit' }
    }
}

function Invoke-CheckedProcess([string]$File, [string]$Arguments) {
    # 安装器是 GUI 程序，显式等待进程才能得到退出码并按顺序验证后续状态。
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru -WindowStyle Hidden
    if (-not $process.WaitForExit(180000)) {
        throw "Timed out waiting for $File"
    }
    if ($process.ExitCode -ne 0) {
        throw "$File exited with code $($process.ExitCode)"
    }
}

try {
    # 测试需要更改 PATH、注册表和快捷方式，遇到已有安装时提前结束，保留其状态。
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
        # 首次安装从不存在的路径开始，同时覆盖空格和非 ASCII 字符。
        if (Test-Path -LiteralPath $directory) {
            throw "The verification directory already exists: $directory"
        }
        $hive = 'HKCU'
        $environmentKey = 'Environment'
        $programs = [Environment]::GetFolderPath('Programs')
        $desktop = [Environment]::GetFolderPath('DesktopDirectory')
        # 两种安装范围分别检查用户或系统注册表，以及对应的开始菜单和桌面。
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
        if (-not (Test-Path -LiteralPath $application -PathType Leaf)) { throw "Missing installed executable: $application" }
        Test-InstalledShortcut $startLink $application (Join-Path $testRoot "$scope-start-self-test.json")
        Test-InstalledShortcut $desktopLink $application (Join-Path $testRoot "$scope-desktop-self-test.json")
        if ((Get-StoredPath $environmentKey) -cne $beforePath) { throw 'The default installation changed PATH' }
        Invoke-CheckedProcess $setupPath "/S /$scope /AddToPath /D=$directory"
        $duringPath = Get-StoredPath $environmentKey
        if (($duringPath -split ';') -notcontains $directory) { throw 'Missing optional PATH entry' }
        # 再用同一选项重装，PATH 内容应与第一次添加后完全相同。
        Invoke-CheckedProcess $setupPath "/S /$scope /AddToPath /D=$directory"
        $afterReinstall = Get-StoredPath $environmentKey
        if ($afterReinstall -ne $duringPath) { throw 'Reinstallation changed PATH unexpectedly' }
        $retainedFile = Join-Path $directory 'user-created.txt'
        # 这个文件模拟用户自己添加的内容，让测试能发现过度清理的卸载器。
        'This synthetic user file must survive uninstall.' | Set-Content -LiteralPath $retainedFile -Encoding UTF8
        Invoke-CheckedProcess (Join-Path $directory 'Uninstall.exe') "/S /$scope"
        # NSIS 会从临时副本完成卸载，需等程序文件与注册信息都清理完再断言结果。
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
