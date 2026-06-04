@echo off
chcp 65001
echo Checking and initializing Python virtual environment...
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo Installing local Node dependencies...
call npm install zsxq-cli

echo Installing Python dependencies...
pip install -r requirements.txt

echo Installing Playwright browser dependencies...
playwright install chromium

echo Starting Streamlit web service...
streamlit run app.py --server.port 3000 --server.address 0.0.0.0
