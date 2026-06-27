$ErrorActionPreference = "Stop"

Write-Host "Voice Dettatura Windows v1.2"
Write-Host ""

if ($env:OS -ne "Windows_NT") {
    Write-Host "Questo installer e' pensato per Windows."
    exit 1
}

$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    $PythonCommand = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $PythonCommand) {
    Write-Host "Python non trovato. Installa Python 3 da python.org o Microsoft Store, poi rilancia."
    exit 1
}

$Source = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $HOME "VoiceDettaturaWindows"
$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

Copy-Item (Join-Path $Source "voice_dettatura_windows.py") $AppDir -Force
Copy-Item (Join-Path $Source "config.json") $AppDir -Force
Copy-Item (Join-Path $Source "requirements.txt") $AppDir -Force

& $PythonCommand.Source -m venv (Join-Path $AppDir ".venv")
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $AppDir "requirements.txt")

# Launcher: avvia l'app dentro la sua cartella. La finestra che si apre
# e' l'app accesa: si chiude per fermare la dettatura.
$LauncherBat = Join-Path $AppDir "Voce Dettatura.bat"
$LauncherContent = @"
@echo off
title Voce Dettatura
cd /d "$AppDir"
"$VenvPython" voice_dettatura_windows.py
"@
Set-Content -Path $LauncherBat -Value $LauncherContent -Encoding ASCII

# Icona cliccabile vera (.lnk) su Scrivania e nel Menu Start, cosi' il cliente
# non apre mai il terminale: clicca l'icona "Voce Dettatura".
$Shell = New-Object -ComObject WScript.Shell
$IconSource = $VenvPython   # icona dell'app (logo Python), riconoscibile come applicazione

function New-VoceShortcut($Path) {
    $lnk = $Shell.CreateShortcut($Path)
    $lnk.TargetPath = $LauncherBat
    $lnk.WorkingDirectory = $AppDir
    $lnk.IconLocation = $IconSource
    $lnk.Description = "Voce Dettatura - tieni premuto Ctrl destro e parla"
    $lnk.Save()
}

$DesktopLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Voce Dettatura.lnk"
New-VoceShortcut $DesktopLnk

$StartDir = [Environment]::GetFolderPath("Programs")
$StartLnk = Join-Path $StartDir "Voce Dettatura.lnk"
New-VoceShortcut $StartLnk

& $VenvPython -m py_compile (Join-Path $AppDir "voice_dettatura_windows.py")

Write-Host ""
Write-Host "Installazione completata."
Write-Host "Icona creata: 'Voce Dettatura' sulla Scrivania e nel Menu Start."
Write-Host ""
Write-Host "Uso:"
Write-Host "1. Clicca l'icona 'Voce Dettatura' (Scrivania o Menu Start)."
Write-Host "2. Si apre una piccola finestra: la Voce e' accesa."
Write-Host "3. In qualsiasi programma, tieni premuto Ctrl destro, parla, rilascia."
Write-Host "4. Compare in basso la pill 'salchiarenza.ai' col sorriso verde; il testo viene scritto dove hai il cursore."
Write-Host "5. Tasto Menu: accende/spegne la voce agenti, se configurata."
Write-Host "6. Per spegnerla: chiudi quella finestra."
