@echo off
chcp 65001 >nul
cd /d "%~dp0web"
if not exist node_modules ( call npm ci --no-audit --no-fund || call npm install --no-audit --no-fund )
start "" http://localhost:4200
npm start
