@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1

rem ---- 설정 파일 준비 ----
if not exist config.bat (
  copy /y config.example.bat config.bat >nul
  echo.
  echo [안내] 처음 실행입니다. 메모장에서 녹취 공유 폴더 경로를 입력하고 저장한 뒤
  echo        start.bat 을 다시 실행하세요.
  echo.
  notepad config.bat
  exit /b 0
)
call config.bat
if not defined CTI_PORT set CTI_PORT=8080

rem ---- 파이썬 찾기 ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo [오류] 파이썬이 설치되어 있지 않습니다.
  echo        https://www.python.org/downloads/ 에서 설치하세요.
  echo        설치 첫 화면에서 Add python.exe to PATH 를 꼭 체크하세요.
  pause
  exit /b 1
)

rem ---- 녹취 폴더 확인 ----
if not exist "%CTI_SYNC_ROOT%\" (
  echo [오류] 녹취 폴더를 찾을 수 없습니다: %CTI_SYNC_ROOT%
  echo        Google Drive 데스크톱 앱이 켜져 있는지, config.bat 의 경로가 맞는지 확인하세요.
  pause
  exit /b 1
)

rem ---- 첫 실행이면 관리자 계정 만들기 ----
%PY% -m scripts.create_user --if-none
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo 대시보드를 켭니다. 이 창을 닫으면 대시보드도 꺼집니다.
echo 녹취 폴더: %CTI_SYNC_ROOT%
echo.
start "" http://127.0.0.1:%CTI_PORT%
%PY% -m cti.app
pause
