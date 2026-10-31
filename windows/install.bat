@echo off
setlocal
title Installazione Voce LeaderAI
echo Voce LeaderAI per Windows
echo Installazione nel profilo di questo utente.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set "VOCE_EXIT=%ERRORLEVEL%"
echo.
if "%VOCE_EXIT%"=="0" (
  echo Installazione conclusa. Torna in Claude Code per il collaudo.
) else (
  echo Installazione interrotta con codice %VOCE_EXIT%.
  echo Lascia aperta questa finestra e mostra il messaggio a Claude Code.
)
pause
exit /b %VOCE_EXIT%
