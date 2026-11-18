
@echo off
title Instalador - INSEL Acao Esportiva
cd /d "%~dp0"

echo ========================================
echo   INSTALACAO DO INSEL ACAO ESPORTIVA
echo ========================================
echo.

python --version
if errorlevel 1 (
    echo ERRO: Python nao encontrado.
    echo Instale o Python e marque Add python.exe to PATH.
    pause
    exit /b 1
)

echo.
echo Criando ambiente virtual...
if not exist "venv" (
    python -m venv venv
    if errorlevel 1 (
        echo ERRO ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

echo.
echo Instalando bibliotecas...
"venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERRO ao atualizar o pip.
    pause
    exit /b 1
)

"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERRO ao instalar as bibliotecas.
    pause
    exit /b 1
)

echo.
echo Instalacao concluida!
echo.
pause
