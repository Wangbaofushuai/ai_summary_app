@echo off
chcp 65001
echo Checking and initializing Python virtual environment...
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

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


echo Installing local Node dependencies...
call npm install zsxq-cli

echo Installing Python dependencies...
pip install -r requirements.txt

echo Installing Playwright browser dependencies...
playwright install chromium

echo Starting Streamlit web service...
streamlit run app.py --server.port 3000 --server.address 0.0.0.0
