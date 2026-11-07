param([switch]$NoPause)
# CAD도우미 제거. 현장 폴더(projects), 결과물, 백업·배운 내용(.cadhelper\knowledge, backups), 배운 스킬(ch-learned-*)은 남겨 둡니다.
$ErrorActionPreference = 'Continue'
$Desk      = [Environment]::GetFolderPath('Desktop')
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$TomlBlock = '(?s)\r?\n?# >>> cad-helper >>>.*?# <<< cad-helper <<<\r?\n?'
$MdBlock   = '(?s)<!-- >>> CAD도우미 \(CadHelper\) >>>.*?<!-- <<< CAD도우미 \(CadHelper\) <<< -->\r?\n?'
$Shipped   = 'ch-cad-area-qa', 'ch-estimate-excel', 'ch-3d-presentation', 'ch-sketchup', 'ch-cad-edit-safely', 'ch-self-improve', 'ch-projects', 'ch-presentation-ppt'

function Strip($path, $pattern, $sep) {
    if (Test-Path -LiteralPath $path) {
        $t = [regex]::Replace([IO.File]::ReadAllText($path), $pattern, $sep)
        [IO.File]::WriteAllText($path, $t.Trim() + "`n", $Utf8NoBom)
    }
}

$works = @((Join-Path ($env:SystemDrive + '\') 'work'), (Join-Path $Desk 'work')) | Where-Object { Test-Path (Join-Path $_ '.cadhelper') }
foreach ($w in $works) {
    Strip (Join-Path $w '.codex\config.toml') $TomlBlock "`n"
    Strip (Join-Path $w 'AGENTS.md') $MdBlock ''
    foreach ($n in $Shipped) { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $w ".codex\skills\$n") }
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $w 'CAD도우미 점검.lnk')
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $w '.cadhelper\app'), (Join-Path $w '.cadhelper\venv')
}
# 사용자 폴더: "work 신뢰" 블록과 예전(v1.0.0) 흔적
Strip (Join-Path $CodexHome 'config.toml') $TomlBlock "`n"
Strip (Join-Path $CodexHome 'AGENTS.md') $MdBlock ''
foreach ($n in $Shipped) { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path (Join-Path $CodexHome 'skills') $n) }
$old = Join-Path $env:USERPROFILE 'CadHelper'
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $old 'app'), (Join-Path $old 'venv')

Get-ChildItem (Join-Path $env:APPDATA 'SketchUp') -Directory -Filter 'SketchUp 20*' -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $_.FullName 'SketchUp\Plugins\cadhelper_bridge.rb')
}
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Desk 'work.lnk'), (Join-Path $Desk 'CAD도우미 결과물.lnk'), (Join-Path $Desk 'CAD도우미 점검.lnk'), (Join-Path $Desk 'CAD작업.lnk')

Write-Host "CAD도우미를 제거했습니다." -ForegroundColor Green
Write-Host "결과물, 백업, 배운 내용, 배운 스킬(ch-learned-*)은 work 폴더에 남겨 두었습니다. 다시 설치하면 그대로 이어서 씁니다."
if (-not $NoPause) { Read-Host "엔터를 누르면 닫힙니다" | Out-Null }
