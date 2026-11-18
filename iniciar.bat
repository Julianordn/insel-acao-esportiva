
@echo off
title INSEL Acao Esportiva
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo ERRO: Execute primeiro o arquivo instalar.bat.
    pause
    exit /b 1
)

if not exist "app.py" (
    echo ERRO: Arquivo app.py nao encontrado.
    pause
    exit /b 1
)

echo Iniciando o INSEL Acao Esportiva...
echo.
echo Quando o sistema estiver iniciado, abra o navegador em:
echo http://127.0.0.1:5000
echo.
echo Para encerrar o sistema, feche esta janela com Ctrl+C.
echo.

"venv\Scripts\python.exe" app.py

echo.
echo O sistema foi encerrado.
pause
