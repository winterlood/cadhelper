@echo off
chcp 65001 >nul
if not exist "%~dp0app\uninstall.ps1" (
  echo.
  echo  [!] 압축 파일 안에서 바로 실행하셨습니다.
  echo      zip 파일을 오른쪽 클릭 - "압축 풀기" 로 먼저 푼 다음,
  echo      풀린 폴더 안의 "제거하기" 를 더블클릭해 주세요.
  echo.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\uninstall.ps1"
if errorlevel 1 pause
