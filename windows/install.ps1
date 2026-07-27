$ErrorActionPreference = "Stop"
$Source = Split-Path -Parent $MyInvocation.MyCommand.Path
$VersionFile = Join-Path (Split-Path -Parent $Source) "VERSION"
if (-not (Test-Path $VersionFile)) {
    throw "File VERSION mancante: scarica l'archivio completo della repo Voce."
}
$Version = (Get-Content $VersionFile -Raw).Trim()
$AppDir = Join-Path $HOME "VoiceDettaturaWindows"
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
Copy-Item (Join-Path $Source "INSTALLA_CON_AI.md") $AppDir -Force
Copy-Item $VersionFile $AppDir -Force

function Assert-LastExit([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step non riuscito (codice $LASTEXITCODE). L'installazione non viene dichiarata completata."
    }
}

Write-Host "Voce LeaderAI $Version (Windows)"
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
    Write-Host "Python non trovato."
    Write-Host "Le istruzioni sono state copiate in $AppDir."
    Write-Host "Chiedi al tuo agente di installare Python 3, poi rilancia install.bat."
    exit 1
}

$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"

Copy-Item (Join-Path $Source "voice_dettatura_windows.py") $AppDir -Force
Copy-Item (Join-Path $Source "voce_hook.py") $AppDir -Force
Copy-Item (Join-Path $Source "requirements.txt") $AppDir -Force
& $PythonCommand.Source (Join-Path $Source "voce_hook.py") --merge-config (Join-Path $Source "config.json") (Join-Path $AppDir "config.json")
Assert-LastExit "Aggiornamento conservativo della configurazione"

& $PythonCommand.Source -m venv (Join-Path $AppDir ".venv")
Assert-LastExit "Creazione ambiente Python"
& $VenvPython -m pip install --upgrade pip
Assert-LastExit "Aggiornamento pip"
& $VenvPython -m pip install -r (Join-Path $AppDir "requirements.txt")
Assert-LastExit "Installazione dipendenze"

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

& $VenvPython -m py_compile (Join-Path $AppDir "voice_dettatura_windows.py") (Join-Path $AppDir "voce_hook.py")
Assert-LastExit "Verifica sintassi app"
& $VenvPython (Join-Path $AppDir "voce_hook.py") --install-hooks
Assert-LastExit "Collegamento voce a Claude Code/Codex"
& $VenvPython (Join-Path $AppDir "voce_hook.py") --check-hooks
Assert-LastExit "Verifica collegamento voce"
Write-Host "Voci italiane rilevate (la scelta e' consigliata, non imposta):"
& $VenvPython (Join-Path $AppDir "voce_hook.py") --list-voices
Assert-LastExit "Lettura voci italiane Windows"
& $VenvPython (Join-Path $AppDir "voce_hook.py") --test-voice
Assert-LastExit "Prova voce Windows"

Write-Host ""
Write-Host "Installazione completata."
Write-Host "Icona creata: 'Voce Dettatura' sulla Scrivania e nel Menu Start."
Write-Host "Voce agenti collegata a Claude Code/Codex e prova audio completata."
Write-Host "Il profilo LeaderAI consiglia di ascoltare le voci italiane disponibili e salvare quella preferita; non viene imposta una voce diversa dalla scelta del proprietario."
Write-Host ""
Write-Host "Uso:"
Write-Host "1. Clicca l'icona 'Voce Dettatura' (Scrivania o Menu Start)."
Write-Host "2. Si apre una piccola finestra: la Voce e' accesa."
Write-Host "3. In qualsiasi programma, tieni premuto Ctrl destro, parla, rilascia."
Write-Host "4. Compare in basso la pill 'salchiarenza.ai' col sorriso verde; il testo viene scritto dove hai il cursore."
Write-Host "5. Tasto Menu: accende/spegne la voce agenti, se configurata."
Write-Host "6. Per spegnerla: chiudi quella finestra."
