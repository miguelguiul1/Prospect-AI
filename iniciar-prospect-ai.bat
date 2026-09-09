@echo off
setlocal enabledelayedexpansion
title Prospect AI - Inicializando...

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo ============================================
echo   Prospect AI - Inicializando ambiente local
echo ============================================
echo.

REM --- Postgres (servico "postgresql-x64-18") ---
sc query "postgresql-x64-18" | find "RUNNING" >nul 2>&1
if errorlevel 1 (
    echo [Postgres] Nao esta rodando. Tentando iniciar o servico...
    net start "postgresql-x64-18" >nul 2>&1
    if errorlevel 1 (
        echo [Postgres] ATENCAO: nao foi possivel iniciar o servico automaticamente.
        echo            Talvez seja necessario rodar este .bat como Administrador,
        echo            ou iniciar o servico "postgresql-x64-18" manualmente pelo services.msc.
    ) else (
        echo [Postgres] Servico iniciado com sucesso.
    )
) else (
    echo [Postgres] Ja esta rodando.
)

echo.

REM --- Redis / Memurai (servico "Memurai") ---
sc query "Memurai" | find "RUNNING" >nul 2>&1
if errorlevel 1 (
    echo [Redis/Memurai] Nao esta rodando. Tentando iniciar o servico...
    net start "Memurai" >nul 2>&1
    if errorlevel 1 (
        echo [Redis/Memurai] ATENCAO: nao foi possivel iniciar o servico automaticamente.
        echo                 Talvez seja necessario rodar este .bat como Administrador,
        echo                 ou iniciar o servico "Memurai" manualmente pelo services.msc.
    ) else (
        echo [Redis/Memurai] Servico iniciado com sucesso.
    )
) else (
    echo [Redis/Memurai] Ja esta rodando.
)

echo.
echo Abrindo backend e frontend em janelas separadas...
echo.

REM "conhost.exe" antes do "cmd" forca uma janela de console classica de
REM verdade, mesmo em maquinas (como esta) onde o Windows Terminal esta
REM configurado como terminal padrao do Windows 11 -- sem isso, os dois
REM "start" abririam como duas ABAS de uma unica janela do Windows
REM Terminal, em vez de duas janelas separadas de verdade (testado nesta
REM mesma maquina antes de decidir por esta abordagem).
start "Prospect AI - Backend" /D "%ROOT%\backend" conhost.exe cmd /k "call .venv\Scripts\activate.bat && uvicorn app.main:app --reload"

start "Prospect AI - Frontend" /D "%ROOT%\frontend" conhost.exe cmd /k "npm run dev"

echo Aguardando o frontend subir (alguns segundos)...
timeout /t 8 /nobreak >nul

start "" "http://localhost:3000"

echo.
echo ============================================
echo   Prospect AI esta rodando.
echo.
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo.
echo   Para DESLIGAR tudo, feche as duas janelas de
echo   terminal que foram abertas ("Prospect AI - Backend"
echo   e "Prospect AI - Frontend"). Fechar esta janela
echo   nao desliga nada.
echo ============================================
echo.
pause
