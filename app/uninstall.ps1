param([switch]$NoPause)
# CAD도우미 제거. 결과물(output), 백업(backups), 배운 내용(knowledge)은 남겨 둡니다.
$ErrorActionPreference = 'Continue'
$HomeDir   = Join-Path $env:USERPROFILE 'CadHelper'
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

$cfg = Join-Path $CodexHome 'config.toml'
if (Test-Path $cfg) {
    $t = [IO.File]::ReadAllText($cfg)
    [IO.File]::WriteAllText($cfg, [regex]::Replace($t, '(?s)\r?\n?# >>> cad-helper >>>.*?# <<< cad-helper <<<\r?\n?', "`n"), $Utf8NoBom)
}
$agents = Join-Path $CodexHome 'AGENTS.md'
if (Test-Path $agents) {
    $t = [IO.File]::ReadAllText($agents)
    [IO.File]::WriteAllText($agents, [regex]::Replace($t, '(?s)<!-- >>> CAD도우미 \(CadHelper\) >>>.*?<!-- <<< CAD도우미 \(CadHelper\) <<< -->\r?\n?', ''), $Utf8NoBom)
}
foreach ($n in 'ch-cad-area-qa', 'ch-estimate-excel', 'ch-3d-presentation', 'ch-sketchup', 'ch-cad-edit-safely', 'ch-self-improve') {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path (Join-Path $CodexHome 'skills') $n)
}
Get-ChildItem (Join-Path $env:APPDATA 'SketchUp') -Directory -Filter 'SketchUp 20*' -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $_.FullName 'SketchUp\Plugins\cadhelper_bridge.rb')
}
$desk = [Environment]::GetFolderPath('Desktop')
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $desk 'CAD도우미 결과물.lnk'), (Join-Path $desk 'CAD도우미 점검.lnk')
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $HomeDir 'app'), (Join-Path $HomeDir 'venv')
Write-Host "CAD도우미를 제거했습니다. 결과물·백업·배운 내용은 $HomeDir 에 남아 있습니다." -ForegroundColor Green
Write-Host "(배운 스킬 ch-learned-* 도 남겨 두었습니다. 다시 설치하면 그대로 이어서 씁니다.)"
if (-not $NoPause) { Read-Host "엔터를 누르면 닫힙니다" | Out-Null }
