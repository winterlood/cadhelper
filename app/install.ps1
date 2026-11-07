param([switch]$NoPause)
# CAD도우미 설치 (Windows PowerShell 5.1+). 설치하기.cmd 가 실행합니다.
# 모든 것을 C:\work 프로젝트 폴더 안에 설치합니다:
#   C:\work\AGENTS.md            Codex 규칙 (표시된 블록만 관리)
#   C:\work\.codex\config.toml   CAD도우미 연결(MCP) 설정 (표시된 블록만 관리)
#   C:\work\.codex\skills\ch-*   스킬 (기본 6개 + 쓰면서 배운 ch-learned-*)
#   C:\work\.cadhelper\          프로그램, Python 환경, 백업, 배운 내용, 기록
#   C:\work\결과물\              엑셀·3D·사진 결과물
# 사용자 폴더(~\.codex\config.toml)에는 "C:\work 를 신뢰" 한 줄 블록만 넣습니다
# (Codex는 신뢰한 폴더의 .codex 설정만 읽기 때문에 이것만은 사용자 폴더에 있어야 합니다).
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Pkg       = Split-Path -Parent $PSScriptRoot          # 압축 푼 폴더
$Src       = $PSScriptRoot                              # ...\app
$Desk      = [Environment]::GetFolderPath('Desktop')   # OneDrive 바탕화면이어도 실제 위치
$Work      = Join-Path ($env:SystemDrive + '\') 'work'
try { New-Item -ItemType Directory -Force -Path $Work -ErrorAction Stop | Out-Null }
catch { $Work = Join-Path $Desk 'work'; New-Item -ItemType Directory -Force -Path $Work | Out-Null }  # C:\ 에 못 만들면 바탕화면에
$HomeDir   = Join-Path $Work '.cadhelper'
$AppDir    = Join-Path $HomeDir 'app'
$VenvDir   = Join-Path $HomeDir 'venv'
$VenvPy    = Join-Path $VenvDir 'Scripts\python.exe'
$OutDir    = Join-Path $Work '결과물'
$ProjCodex = Join-Path $Work '.codex'
$Skills    = Join-Path $ProjCodex 'skills'
$OldHome   = Join-Path $env:USERPROFILE 'CadHelper'    # v1.0.0 설치 위치 (있으면 옮겨 옴)
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$LogFile   = Join-Path $HomeDir 'logs\install.log'
$Shipped   = 'ch-cad-area-qa', 'ch-estimate-excel', 'ch-3d-presentation', 'ch-sketchup', 'ch-cad-edit-safely', 'ch-self-improve'
$TomlBlock = '(?s)\r?\n?# >>> cad-helper >>>.*?# <<< cad-helper <<<\r?\n?'
$MdBlock   = '(?s)<!-- >>> CAD도우미 \(CadHelper\) >>>.*?<!-- <<< CAD도우미 \(CadHelper\) <<< -->\r?\n?'

function Say($msg, $color = 'White') { Write-Host $msg -ForegroundColor $color; try { Add-Content -LiteralPath $LogFile -Value ("{0} {1}" -f (Get-Date -Format s), $msg) -Encoding UTF8 } catch {} }
function Step($n, $msg) { Say ""; Say "[$n/8] $msg" 'Cyan' }
function Read-Text($p) { if (Test-Path -LiteralPath $p) { [IO.File]::ReadAllText($p) } else { '' } }
$q = { param($s) '"' + $s.Replace('\', '\\').Replace('"', '\"') + '"' }  # TOML basic string, escaped

function Get-InstalledPrograms {
    $keys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName } |
        Select-Object DisplayName, DisplayVersion, InstallLocation
}

# config.toml 안에 같은 [projects."경로"] 가 이미 있는지 (같은 표가 두 번 있으면 Codex 설정이 깨짐)
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

# 폴더 안 파일을 덮어쓰지 않고 옮겨 담기 (v1.0.0 → work 이사용)
function Merge-Dir($from, $to) {
    if (-not (Test-Path -LiteralPath $from)) { return }
    New-Item -ItemType Directory -Force -Path $to | Out-Null
    Get-ChildItem -LiteralPath $from -Force | ForEach-Object {
        $dst = Join-Path $to $_.Name
        if (-not (Test-Path -LiteralPath $dst)) { Copy-Item -Recurse -Force -LiteralPath $_.FullName -Destination $dst }
    }
}

try {
    New-Item -ItemType Directory -Force -Path (Split-Path $LogFile) | Out-Null
    Say "=============================================" 'Green'
    Say "   CAD도우미 설치를 시작합니다 (5~10분)" 'Green'
    Say "   설치 위치: $Work" 'Green'
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
    foreach ($bad in $HomeDir, $ProjCodex, $OutDir) {
        $b = [IO.Path]::GetFullPath($bad).TrimEnd('\')
        if ($pkgFull -ieq $b -or $pkgFull.StartsWith($b + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "설치 파일을 '$bad' 안에 풀면 안 됩니다. 바탕화면 같은 다른 곳에 압축을 풀고 다시 실행해 주세요."
        }
    }
    if (Test-Path $AppDir) { Remove-Item -Recurse -Force $AppDir }
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    Copy-Item -Recurse -Force -Path (Join-Path $Src '*') -Destination $AppDir -Exclude '__pycache__', 'install.ps1'
    Get-ChildItem $AppDir -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    Get-ChildItem $AppDir -Recurse -File -Filter '.secret' -ErrorAction SilentlyContinue | Remove-Item -Force
    foreach ($d in 'backups', 'knowledge', 'logs') { New-Item -ItemType Directory -Force -Path (Join-Path $HomeDir $d) | Out-Null }
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    # 예전(v1.0.0) 설치가 있으면 결과물·백업·배운 내용을 옮겨 옴 (원본은 남겨 둠)
    if (Test-Path (Join-Path $OldHome 'knowledge')) {
        Merge-Dir (Join-Path $OldHome 'knowledge') (Join-Path $HomeDir 'knowledge')
        Merge-Dir (Join-Path $OldHome 'backups') (Join-Path $HomeDir 'backups')
        Merge-Dir (Join-Path $OldHome 'output') $OutDir
        Say "예전 설치($OldHome)의 결과물·백업·배운 내용을 옮겨 왔습니다." 'Gray'
    }
    $tokenFile = Join-Path $HomeDir 'sketchup_token.txt'
    $oldToken = Join-Path $OldHome 'sketchup_token.txt'
    if (-not (Test-Path $tokenFile) -and (Test-Path $oldToken)) { Copy-Item $oldToken $tokenFile }  # 켜져 있는 SketchUp과 계속 연결되게
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
    $env:CADHELPER_OUTPUT = $OutDir
    $env:CADHELPER_SKILLS_DIR = $Skills
    $env:CADHELPER_APP = $AppDir
    $probe = & $VenvPy -W ignore -c "import os,sys;a=os.environ['CADHELPER_APP'];sys.path[:0]=[a,os.path.join(a,'vendor')];import cadhelper_server as s;m=s.build();print('OK')" 2>$null
    $ErrorActionPreference = 'Stop'
    if (($probe | Select-Object -Last 1) -ne 'OK') { throw "프로그램 점검 실패: $probe (기록 폴더의 install.log 확인)" }
    Say "점검 통과" 'Gray'

    # 5. Codex 연결 -------------------------------------------------------------
    Step 5 "Codex에 연결 (work 폴더 안 .codex)"
    New-Item -ItemType Directory -Force -Path $ProjCodex | Out-Null
    $pcfg = Join-Path $ProjCodex 'config.toml'
    $text = [regex]::Replace((Read-Text $pcfg), $TomlBlock, "`n")
    if ($text -match '(?m)^\s*\[mcp_servers\.(cad-helper|"cad-helper")\]') {
        throw "$pcfg 에 'cad-helper'가 이미 다른 방식으로 들어 있습니다. 그 항목을 지우고 다시 실행해 주세요."
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
CADHELPER_OUTPUT = $(& $q $OutDir)
CADHELPER_SKILLS_DIR = $(& $q $Skills)
USERPROFILE = $(& $q $env:USERPROFILE)
SYSTEMROOT = $(& $q $env:SystemRoot)
# <<< cad-helper <<<
"@
    [IO.File]::WriteAllText($pcfg, ($text.TrimEnd() + "`n" + $block).TrimStart(), $Utf8NoBom)
    Say "Codex 연결 설정: $pcfg" 'Gray'

    # 사용자 폴더 설정: 예전 블록(v1.0.0의 전역 연결)을 지우고 "work 폴더 신뢰"만 남김
    New-Item -ItemType Directory -Force -Path $CodexHome | Out-Null
    $gcfg = Join-Path $CodexHome 'config.toml'
    $gtext = Read-Text $gcfg
    if ($gtext -and -not (Test-Path "$gcfg.bak-cadhelper")) { Copy-Item $gcfg "$gcfg.bak-cadhelper" }  # 처음 원본 보관
    $gtext = [regex]::Replace($gtext, $TomlBlock, "`n")
    $trust = ''
    if (-not (Get-TomlProjectPaths $gtext | Where-Object { $_.TrimEnd('\') -ieq $Work.TrimEnd('\') })) {
        $trust = "[projects.$(& $q $Work)]`ntrust_level = `"trusted`"`n"
    }
    if ($trust) { $gtext = $gtext.TrimEnd() + "`n`n# >>> cad-helper >>>`n" + $trust + "# <<< cad-helper <<<`n" }
    [IO.File]::WriteAllText($gcfg, $gtext.TrimStart(), $Utf8NoBom)

    # 6. 스킬과 규칙 ------------------------------------------------------------
    Step 6 "Codex 스킬과 안전 규칙 설치 (work 폴더 안)"
    New-Item -ItemType Directory -Force -Path $Skills | Out-Null
    Get-ChildItem (Join-Path $Pkg 'codex\skills') -Directory | ForEach-Object {
        $dst = Join-Path $Skills $_.Name
        if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
        Copy-Item -Recurse -Force $_.FullName $dst
    }
    # 예전 위치(사용자 폴더)의 스킬·규칙 정리: 기본 스킬은 지우고, 배운 스킬(ch-learned-*)은 work 로 옮김
    $gskills = Join-Path $CodexHome 'skills'
    foreach ($n in $Shipped) { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $gskills $n) }
    Get-ChildItem $gskills -Directory -Filter 'ch-learned-*' -ErrorAction SilentlyContinue | ForEach-Object {
        $dst = Join-Path $Skills $_.Name
        if (-not (Test-Path $dst)) { Copy-Item -Recurse -Force $_.FullName $dst }
        Remove-Item -Recurse -Force $_.FullName
    }
    $gagents = Join-Path $CodexHome 'AGENTS.md'
    if (Test-Path $gagents) { [IO.File]::WriteAllText($gagents, [regex]::Replace((Read-Text $gagents), $MdBlock, '').Trim() + "`n", $Utf8NoBom) }
    # work\AGENTS.md: 우리 블록만 교체, 사용자가 쓴 내용은 보존 (예전 버전이 통째로 만든 파일이면 새로 씀)
    $agents = Join-Path $Work 'AGENTS.md'
    $ours = Read-Text (Join-Path $Pkg 'codex\AGENTS.md')
    $cur = Read-Text $agents
    if ($cur -match '^\s*# (work|CAD작업) 폴더 \(CadHelper\)') { $cur = '' }
    $cur = [regex]::Replace($cur, $MdBlock, '')
    [IO.File]::WriteAllText($agents, ($ours.TrimEnd() + "`n`n" + $cur.Trim()).Trim() + "`n", $Utf8NoBom)

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
    # 플러그인에 실제 설치 위치를 적어 넣음 (Ruby 작은따옴표 문자열, / 구분자)
    $rubyHome = $HomeDir.Replace('\', '/').Replace("'", "\'")
    $rb = (Read-Text (Join-Path $AppDir 'sketchup_plugin\cadhelper_bridge.rb')).Replace('@@CADHELPER_HOME@@', $rubyHome)
    foreach ($y in $years) {
        $plug = Join-Path $su "$y\SketchUp\Plugins"
        New-Item -ItemType Directory -Force -Path $plug | Out-Null
        [IO.File]::WriteAllText((Join-Path $plug 'cadhelper_bridge.rb'), $rb, $Utf8NoBom)
        Say "$y 에 설치" 'Gray'
    }

    # 8. work 폴더 바로가기 ------------------------------------------------------
    Step 8 "work 폴더에 점검·설명서, 바탕화면에 work 바로가기"
    $sh = New-Object -ComObject WScript.Shell
    $lnk = $sh.CreateShortcut((Join-Path $Work 'CAD도우미 점검.lnk'))
    $lnk.TargetPath = $VenvPy
    $lnk.Arguments = '"' + (Join-Path $AppDir 'check.py') + '"'
    $lnk.WorkingDirectory = $AppDir
    $lnk.Save()
    foreach ($doc in Get-ChildItem $Pkg -Filter '*.pdf' -ErrorAction SilentlyContinue) {
        Copy-Item -Force $doc.FullName (Join-Path $Work $doc.Name)
        Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Desk $doc.Name)   # 예전 버전이 바탕화면에 둔 설명서
    }
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Work '결과물.lnk'), (Join-Path $Desk 'CAD도우미 결과물.lnk'), (Join-Path $Desk 'CAD도우미 점검.lnk'), (Join-Path $Desk 'CAD작업.lnk')
    if ($Work -ne (Join-Path $Desk 'work')) {
        $lnk = $sh.CreateShortcut((Join-Path $Desk 'work.lnk'))
        $lnk.TargetPath = $Work; $lnk.Save()
    }
    # 예전(v1.0.0) 프로그램은 지움. 결과물·백업·배운 내용은 옮겨 왔고 원본 폴더도 남겨 둠.
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $OldHome 'app'), (Join-Path $OldHome 'venv')

    Say ""
    Say "=============================================" 'Green'
    Say "   설치 완료!  모든 것이 $Work 안에 있습니다." 'Green'
    Say "   1) Codex를 완전히 껐다가 다시 켜 주세요." 'Green'
    Say "   2) 처음 한 번만: Codex 앱에서 '프로젝트 추가' -> '$Work' 폴더 선택" 'Green'
    Say "   3) SketchUp을 쓰려면 SketchUp도 껐다 켜 주세요." 'Green'
    Say "   4) $Work 의 'CAD도우미 점검'으로 확인할 수 있습니다." 'Green'
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
