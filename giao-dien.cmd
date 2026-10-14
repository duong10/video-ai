@echo off
rem Giao dien web de tao video (Windows). Chay: .\giao-dien.cmd   hoac   .\giao-dien.cmd --cong 9000
"%~dp0.venv\Scripts\python.exe" "%~dp0san_xuat\giao_dien.py" %*
