@echo off
chcp 65001 >nul
title Biology telefonga
rem Telefonni USB bilan ulang (Отладка по USB yoqilgan), ekran qulfini oching va shu faylni bosing.
rem Sayt va ikkala bot telefonga o'rnatiladi va ishga tushadi; kompyuterdagisi to'xtatiladi.
set "LOYIHA=D:\milliy_sertifikat"
set "PY=%LOYIHA%\.venv\Scripts\python.exe"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
cd /d "%LOYIHA%" || (echo XATO: %LOYIHA% topilmadi & pause & exit /b 1)
"%PY%" telefonga.py %*
echo.
pause
