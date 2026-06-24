@echo off
chcp 65001

set FORCE_INSTALL=0
if "%1"=="--force" (
    set FORCE_INSTALL=1
    echo [FORCE] Force reinstall of all dependencies requested.
)

echo Checking and initializing Python virtual environment...
if not exist ".venv" (
    python -m venv .venv
    set FORCE_INSTALL=1
)
call .venv\Scripts\activate.bat

echo Checking and linking skills directory to .agents/skills...
if not exist ".agents" mkdir .agents
if not exist ".agents\skills" (
    echo Creating Directory Junction: .agents\skills -^> skills
    mklink /J ".agents\skills" "skills"
)

echo Running pre-commit guard...
python pre_commit_guard.py
if %errorlevel% neq 0 (
    echo [ERROR] Pre-commit guard failed. Aborting startup.
    exit /b %errorlevel%
)

echo Installing Dreamina CLI...
if not exist "dreamina.exe" (
    curl.exe -fLo dreamina.exe https://lf3-static.bytednsdoc.com/obj/eden-cn/psj_hupthlyk/ljhwZthlaukjlkulzlp/dreamina_cli_beta/dreamina_cli_windows_amd64.exe
)

echo Checking Node dependencies...
if not exist "node_modules" (
    echo Installing local Node dependencies...
    call npm install zsxq-cli
) else (
    if "%FORCE_INSTALL%"=="1" (
        echo Force installing local Node dependencies...
        call npm install zsxq-cli
    ) else (
        echo Node dependencies already installed. Skipping.
    )
)

echo Checking Python dependencies...
if not exist ".venv\.pip_install_done" (
    echo Installing Python dependencies...
    pip install -r requirements.txt
    if %errorlevel% equ 0 (
        echo done > .venv\.pip_install_done
    )
) else (
    if "%FORCE_INSTALL%"=="1" (
        echo Force installing Python dependencies...
        pip install -r requirements.txt
        if %errorlevel% equ 0 (
            echo done > .venv\.pip_install_done
        )
    ) else (
        echo Python dependencies already installed. Skipping.
    )
)

echo Checking Playwright browser dependencies...
if not exist ".venv\.playwright_install_done" (
    echo Installing Playwright browser dependencies...
    playwright install chromium
    if %errorlevel% equ 0 (
        echo done > .venv\.playwright_install_done
    )
) else (
    if "%FORCE_INSTALL%"=="1" (
        echo Force installing Playwright browser dependencies...
        playwright install chromium
        if %errorlevel% equ 0 (
            echo done > .venv\.playwright_install_done
        )
    ) else (
        echo Playwright browser already installed. Skipping.
    )
)

echo Starting Streamlit web service...
streamlit run app.py --server.port 3000 --server.address 0.0.0.0
