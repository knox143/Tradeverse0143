@echo off
title Upload TradeVerse to GitHub
cls
echo ========================================================
echo        TradeVerse - GitHub Push Assistant
echo ========================================================
echo.
echo Please create a new empty repository on GitHub:
echo 1. Go to https://github.com/new
echo 2. Give it a name (e.g. TradeVerse)
echo 3. Do NOT check "Add a README" or .gitignore
echo 4. Click "Create repository"
echo 5. Copy the HTTPS repository URL
echo.
echo ========================================================
set /p REPO_URL="Paste your GitHub Repository URL here: "

if "%REPO_URL%"=="" (
    echo [ERROR] No URL provided. Aborted.
    pause
    exit /b
)

echo.
echo [1/4] Adding all files to git...
git add .

echo [2/4] Committing changes...
git commit -m "TradeVerse: Real-time paper trading platform with dual currency, candlestick charts, and trade timeline"

echo [3/4] Setting main branch and remote origin...
git branch -M main
git remote remove origin 2>nul
git remote add origin %REPO_URL%

echo [4/4] Pushing to GitHub...
git push -u origin main

echo.
if %ERRORLEVEL% equ 0 (
    echo ========================================================
    echo  SUCCESS! Your TradeVerse project is now live on GitHub!
    echo ========================================================
) else (
    echo ========================================================
    echo  [NOTE] If git requested credentials, please log in with
    echo  your GitHub Personal Access Token or GitHub CLI.
    echo ========================================================
)
echo.
pause
