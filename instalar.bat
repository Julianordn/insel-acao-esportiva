
@echo off
title Instalador - INSEL Acao Esportiva
cd /d "%~dp0"

echo ========================================
echo   INSTALACAO DO INSEL ACAO ESPORTIVA
echo ========================================
echo.

echo Verificando Python...
python --version
if errorlevel 1 (
    echo ERRO: Python nao encontrado.
    echo Instale o Python e marque Add python.exe to PATH.
    pause
    exit /b 1
)

echo.
echo Verificando chave secreta...

if not exist ".env" (
    python -c "import secrets; open('.env','w',encoding='utf-8').write('FLASK_SECRET_KEY='+secrets.token_hex(32))"
    if errorlevel 1 (
        echo ERRO ao criar arquivo .env.
        pause
        exit /b 1
    )
    echo Chave secreta criada!
) else (
    echo Arquivo .env ja existe.
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
echo ========================================
echo   INSTALACAO CONCLUIDA COM SUCESSO!
echo ========================================
echo.
echo Agora execute o arquivo iniciar.bat.
echo.

pause
