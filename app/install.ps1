param([switch]$NoPause)
# CAD도우미 설치 (Windows PowerShell 5.1+). 설치하기.cmd 가 실행합니다.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Pkg       = Split-Path -Parent $PSScriptRoot          # 압축 푼 폴더
$Src       = $PSScriptRoot                              # ...\app
$HomeDir   = Join-Path $env:USERPROFILE 'CadHelper'
$AppDir    = Join-Path $HomeDir 'app'
$VenvDir   = Join-Path $HomeDir 'venv'
$VenvPy    = Join-Path $VenvDir 'Scripts\python.exe'
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$LogFile   = Join-Path $HomeDir 'logs\install.log'
$Desk      = [Environment]::GetFolderPath('Desktop')        # OneDrive 바탕화면이어도 실제 위치
$Work      = Join-Path ($env:SystemDrive + '\') 'CAD작업'     # Codex 데스크톱 앱 프로젝트 폴더 (C:\CAD작업)
try { New-Item -ItemType Directory -Force -Path $Work -ErrorAction Stop | Out-Null }
catch { $Work = Join-Path $Desk 'CAD작업' }                 # C:\ 에 만들 권한이 없는 PC면 바탕화면에

function Say($msg, $color = 'White') { Write-Host $msg -ForegroundColor $color; try { Add-Content -LiteralPath $LogFile -Value ("{0} {1}" -f (Get-Date -Format s), $msg) -Encoding UTF8 } catch {} }
function Step($n, $msg) { Say ""; Say "[$n/8] $msg" 'Cyan' }

function Get-InstalledPrograms {
    $keys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName } |
        Select-Object DisplayName, DisplayVersion, InstallLocation
}

# config.toml 안에 같은 [projects."경로"] / [sandbox_workspace_write] 가 이미 있는지 (중복 표 = Codex 설정 깨짐)
function Get-TomlProjectPaths($text) {
    $paths = @()
    foreach ($m in [regex]::Matches($text, '(?m)^\s*\[projects\.(?:''([^'']*)''|"((?:[^"\\]|\\.)*)")\]')) {
        if ($m.Groups[1].Success) { $paths += $m.Groups[1].Value } else { $paths += ($m.Groups[2].Value -replace '\\\\', '\') }
    }
    return $paths
}

function Find-Python {
    $c = @()
    $c += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    $c += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    $c += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
    $c += Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
    $c += Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.13-64\python.exe'
    foreach ($n in 'python.exe', 'py.exe') {
        $cmd = Get-Command $n -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notmatch 'WindowsApps') { $c += $cmd.Source }
    }
    foreach ($p in $c) {
        if (-not (Test-Path $p)) { continue }
        try {
            $v = & $p -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
            if ($v -match '^3\.(1[0-9])$' -and [int]$Matches[1] -ge 10 -and [int]$Matches[1] -le 14) { return $p }
        } catch {}
    }
    return $null
}

try {
    New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
    Say "=============================================" 'Green'
    Say "   CAD도우미 설치를 시작합니다 (5~10분)" 'Green'
    Say "   창을 닫지 말고 기다려 주세요." 'Green'
    Say "=============================================" 'Green'

    # 1. Python ---------------------------------------------------------------
    Step 1 "Python 확인"
    $py = Find-Python
    if (-not $py) {
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if ($winget) {
            Say "Python을 설치합니다 (winget)..."
            & $winget.Source install --id Python.Python.3.13 --exact --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Null
            $py = Find-Python
        }
        if (-not $py) {
            Say "Python을 인터넷에서 내려받아 설치합니다..."
            $inst = Join-Path $env:TEMP 'python-3.13.7-amd64.exe'
            Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe' -OutFile $inst
            Start-Process -Wait -FilePath $inst -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_test=0', 'Include_launcher=0', 'Shortcuts=0'
            $py = Find-Python
        }
        if (-not $py) { throw "Python 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요." }
    }
    Say "Python: $py" 'Gray'

    # 2. 프로그램 복사 ----------------------------------------------------------
    Step 2 "프로그램 복사"
    $pkgFull = [IO.Path]::GetFullPath($Pkg).TrimEnd('\')
    $homeFull = [IO.Path]::GetFullPath($HomeDir).TrimEnd('\')
    if ($pkgFull -ieq $homeFull -or $pkgFull.StartsWith($homeFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "설치 파일을 '$HomeDir' 안에 풀면 안 됩니다. 바탕화면 같은 다른 곳에 압축을 풀고 다시 실행해 주세요."
    }
    if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    Copy-Item -Recurse -Force -Path (Join-Path $Src '*') -Destination $AppDir -Exclude '__pycache__', 'install.ps1'
    Get-ChildItem $AppDir -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    Get-ChildItem $AppDir -Recurse -File -Filter '.secret' -ErrorAction SilentlyContinue | Remove-Item -Force
    foreach ($d in 'output', 'backups', 'knowledge', 'logs') { New-Item -ItemType Directory -Force -Path (Join-Path $HomeDir $d) | Out-Null }
    $tokenFile = Join-Path $HomeDir 'sketchup_token.txt'
    if (-not (Test-Path $tokenFile)) {
        $b = New-Object byte[] 16; [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
        [IO.File]::WriteAllText($tokenFile, (($b | ForEach-Object { $_.ToString('x2') }) -join ''), $Utf8NoBom)
    }

    # 3. 부품 설치 --------------------------------------------------------------
    Step 3 "필요한 부품 설치 (인터넷 필요, 몇 분 걸립니다)"
    # Native programs write warnings to stderr; in PowerShell 5.1 that must not count as failure.
    $ErrorActionPreference = 'Continue'
    if ((Test-Path $VenvPy) -and -not (& $VenvPy -c "print(1)" 2>$null)) { Remove-Item -Recurse -Force $VenvDir }
    if (-not (Test-Path $VenvPy)) { & $py -m venv $VenvDir 2>&1 | Out-Null; if ($LASTEXITCODE -ne 0) { throw "Python 가상환경을 만들지 못했습니다." } }
    $pipOut = & $VenvPy -m pip install --disable-pip-version-check -q -r (Join-Path $AppDir 'requirements.txt') 2>&1
    if ($LASTEXITCODE -ne 0) { Say ($pipOut | Out-String) 'Gray'; throw "부품 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행해 주세요." }

    # 4. 자체 점검 --------------------------------------------------------------
    Step 4 "프로그램 점검"
    $env:CADHELPER_HOME = $HomeDir
    $env:CADHELPER_APP = $AppDir
    $probe = & $VenvPy -W ignore -c "import os,sys;a=os.environ['CADHELPER_APP'];sys.path[:0]=[a,os.path.join(a,'vendor')];import cadhelper_server as s;m=s.build();print('OK')" 2>$null
    $ErrorActionPreference = 'Stop'
    if (($probe | Select-Object -Last 1) -ne 'OK') { throw "프로그램 점검 실패: $probe (기록 폴더의 install.log 확인)" }
    Say "점검 통과" 'Gray'

    # 5. Codex 등록 -------------------------------------------------------------
    Step 5 "Codex에 연결"
    New-Item -ItemType Directory -Force -Path $CodexHome | Out-Null
    $cfg = Join-Path $CodexHome 'config.toml'
    $text = if (Test-Path $cfg) { [IO.File]::ReadAllText($cfg) } else { '' }
    if ($text -and -not (Test-Path "$cfg.bak-cadhelper")) { Copy-Item $cfg "$cfg.bak-cadhelper" }  # keep the pre-install original
    $text = [regex]::Replace($text, '(?s)\r?\n?# >>> cad-helper >>>.*?# <<< cad-helper <<<\r?\n?', "`n")
    if ($text -match '(?m)^\[mcp_servers\.(cad-helper|"cad-helper")\]') {
        throw "Codex 설정에 'cad-helper'가 이미 다른 방식으로 등록돼 있습니다. $cfg 에서 그 항목을 지우고 다시 실행해 주세요."
    }
    $q = { param($s) '"' + $s.Replace('\', '\\').Replace('"', '\"') + '"' }  # TOML basic string, escaped
    # CAD작업 폴더를 신뢰 프로젝트로 (이미 등록돼 있으면 그대로 둠)
    $extra = ''
    if (-not (Get-TomlProjectPaths $text | Where-Object { $_.TrimEnd('\') -ieq $Work.TrimEnd('\') })) {
        $extra += "`n[projects.$(& $q $Work)]`ntrust_level = `"trusted`"`n"
    }
    # 쓰기 허용 폴더: CAD도우미 폴더만. 도면(내 문서·바탕화면 등) 읽기는 원래 어디든 가능하고,
    # 도면 열기·저장·결과물 만들기는 CAD도우미 도구(샌드박스 밖, 확인창 보호)가 한다.
    # 내 문서·바탕화면 쓰기를 열면 AI 셸이 도면을 직접 지우거나 덮어쓸 수 있어 일부러 열지 않는다.
    if ($text -match '(?m)^\s*\[sandbox_workspace_write\]' -or $text -match '(?m)^\s*sandbox_workspace_write\.') {
        Say "Codex 설정에 쓰기 허용 폴더(sandbox_workspace_write)가 이미 있어 그대로 둡니다." 'Yellow'
    } else {
        $roots = @($HomeDir)
        $extra += "`n[sandbox_workspace_write]`nwritable_roots = [" + (($roots | ForEach-Object { & $q $_ }) -join ', ') + "]`n"
    }
    $block = @"

# >>> cad-helper >>>
[mcp_servers.cad-helper]
command = $(& $q $VenvPy)
args = [$(& $q (Join-Path $AppDir 'cadhelper_server.py'))]
startup_timeout_sec = 60
tool_timeout_sec = 900

[mcp_servers.cad-helper.env]
CADHELPER_HOME = $(& $q $HomeDir)
CODEX_HOME = $(& $q $CodexHome)
USERPROFILE = $(& $q $env:USERPROFILE)
SYSTEMROOT = $(& $q $env:SystemRoot)
$extra# <<< cad-helper <<<
"@
    [IO.File]::WriteAllText($cfg, $text.TrimEnd() + "`n" + $block, $Utf8NoBom)
    Say "Codex 설정: $cfg" 'Gray'

    # 6. 스킬과 규칙 ------------------------------------------------------------
    Step 6 "Codex 스킬과 안전 규칙 설치"
    $skills = Join-Path $CodexHome 'skills'
    New-Item -ItemType Directory -Force -Path $skills | Out-Null
    Get-ChildItem (Join-Path $Pkg 'codex\skills') -Directory | ForEach-Object {
        $dst = Join-Path $skills $_.Name
        if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
        Copy-Item -Recurse -Force $_.FullName $dst
    }
    $agents = Join-Path $CodexHome 'AGENTS.md'
    $ours = [IO.File]::ReadAllText((Join-Path $Pkg 'codex\AGENTS.md'))
    $cur = if (Test-Path $agents) { [IO.File]::ReadAllText($agents) } else { '' }
    $cur = [regex]::Replace($cur, '(?s)<!-- >>> CAD도우미 \(CadHelper\) >>>.*?<!-- <<< CAD도우미 \(CadHelper\) <<< -->\r?\n?', '')
    [IO.File]::WriteAllText($agents, ($cur.TrimEnd() + "`n`n" + $ours).TrimStart(), $Utf8NoBom)

    # 7. SketchUp 플러그인 + 설치된 CAD 확인 -----------------------------------
    Step 7 "AutoCAD / SketchUp 확인, SketchUp 연결 플러그인 설치"
    $progs = @(Get-InstalledPrograms)
    $acadFull = @($progs | Where-Object { $_.DisplayName -match '^AutoCAD( (Architecture|Mechanical|Electrical|MEP|Map 3D|Plant 3D|Civil 3D))? 20\d\d' -and $_.DisplayName -notmatch ' LT ' } | ForEach-Object { $_.DisplayName } | Sort-Object -Unique)
    $acadLt   = @($progs | Where-Object { $_.DisplayName -match '^AutoCAD LT 20\d\d' } | ForEach-Object { $_.DisplayName } | Sort-Object -Unique)
    $otherCad = @($progs | Where-Object { $_.DisplayName -match '^(ZWCAD|GstarCAD|BricsCAD)' } | ForEach-Object { $_.DisplayName } | Sort-Object -Unique)
    if ($acadFull) { Say ("AutoCAD: " + ($acadFull -join ', ') + "  -> 자동 조작 가능") 'Gray' }
    if ($acadLt)   { Say ("AutoCAD LT: " + ($acadLt -join ', ') + "  -> LT는 외부 연결이 막혀 있어 도면 자동 조작은 안 됩니다 (엑셀·3D·파일 처리는 가능)") 'Yellow' }
    if ($otherCad) { Say ("호환 CAD: " + ($otherCad -join ', ') + "  -> AutoCAD와 같은 방식으로 연결을 시도합니다") 'Gray' }
    if (-not ($acadFull -or $acadLt -or $otherCad)) { Say "설치 목록에서 AutoCAD를 찾지 못했습니다. (켜져 있으면 연결을 시도합니다)" 'Yellow' }
    $years = @()
    foreach ($p in $progs) {
        if ($p.DisplayName -match '^(Trimble )?SketchUp( Pro| Make)? ?(20\d\d)' -and $p.DisplayName -notmatch 'Viewer|LayOut') {
            $y = [int]$Matches[3]
            if ($y -ge 2017) { $years += "SketchUp $y" } else { Say "$($p.DisplayName): 2016 이하 버전은 지원하지 않습니다." 'Yellow' }
        }
    }
    foreach ($root in "$env:ProgramFiles\SketchUp", "${env:ProgramFiles(x86)}\SketchUp") {
        if (Test-Path $root) { Get-ChildItem $root -Directory -Filter 'SketchUp 20*' | ForEach-Object { $years += $_.Name } }
    }
    $su = Join-Path $env:APPDATA 'SketchUp'
    if (Test-Path $su) { Get-ChildItem $su -Directory -Filter 'SketchUp 20*' | ForEach-Object { $years += $_.Name } }
    $years = $years | Sort-Object -Unique
    if (-not $years) { Say "SketchUp이 설치돼 있지 않아 건너뜁니다. (나중에 SketchUp을 설치했다면 설치하기를 한 번 더 실행)" 'Yellow' }
    foreach ($y in $years) {
        $plug = Join-Path $su "$y\SketchUp\Plugins"
        New-Item -ItemType Directory -Force -Path $plug | Out-Null
        Copy-Item -Force (Join-Path $AppDir 'sketchup_plugin\cadhelper_bridge.rb') $plug
        Say "$y 에 설치" 'Gray'
    }

    # 8. 바탕화면 ---------------------------------------------------------------
    Step 8 "CAD작업 폴더와 바탕화면 바로가기 만들기"
    $desk = $Desk
    New-Item -ItemType Directory -Force -Path $Work | Out-Null
    $wa = Join-Path $Work 'AGENTS.md'
    if (-not (Test-Path $wa) -or ([IO.File]::ReadAllText($wa) -match 'CAD작업 폴더 \(CadHelper\)')) {
        Copy-Item -Force (Join-Path $Pkg 'codex\project\AGENTS.md') $wa
    }
    $sh = New-Object -ComObject WScript.Shell
    $lnk = $sh.CreateShortcut((Join-Path $Work '결과물.lnk'))
    $lnk.TargetPath = Join-Path $HomeDir 'output'; $lnk.Save()
    Say "Codex 프로젝트 폴더: $Work" 'Gray'
    if ($Work -ne (Join-Path $desk 'CAD작업')) {
        $lnk = $sh.CreateShortcut((Join-Path $desk 'CAD작업.lnk'))
        $lnk.TargetPath = $Work; $lnk.Save()
    }
    $lnk = $sh.CreateShortcut((Join-Path $desk 'CAD도우미 결과물.lnk'))
    $lnk.TargetPath = Join-Path $HomeDir 'output'; $lnk.Save()
    $lnk = $sh.CreateShortcut((Join-Path $desk 'CAD도우미 점검.lnk'))
    $lnk.TargetPath = $VenvPy
    $lnk.Arguments = '"' + (Join-Path $AppDir 'check.py') + '"'
    $lnk.WorkingDirectory = $AppDir
    $lnk.Save()
    foreach ($doc in Get-ChildItem $Pkg -Filter '*.pdf' -ErrorAction SilentlyContinue) {
        Copy-Item -Force $doc.FullName (Join-Path $desk $doc.Name)
    }

    Say ""
    Say "=============================================" 'Green'
    Say "   설치 완료!" 'Green'
    Say "   1) Codex를 완전히 껐다가 다시 켜 주세요." 'Green'
    Say "   2) 처음 한 번만: Codex 앱에서 '프로젝트 추가' -> '$Work' 폴더 선택" 'Green'
    Say "   3) SketchUp을 쓰려면 SketchUp도 껐다 켜 주세요." 'Green'
    Say "   4) 바탕화면 'CAD도우미 점검'으로 확인할 수 있습니다." 'Green'
    Say "=============================================" 'Green'
    $code = 0
} catch {
    Say ""
    Say "설치 중 문제가 생겼습니다: $($_.Exception.Message)" 'Red'
    Say "이 화면을 사진 찍어서 보내 주세요. (기록: $LogFile)" 'Red'
    $code = 1
}
if (-not $NoPause) { Read-Host "엔터를 누르면 창이 닫힙니다" | Out-Null }
exit $code
