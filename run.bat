@echo off
echo Installing dependencies...
pip install -r requirements.txt
echo Starting FLL TMS Server...
python app.py
echo finding ip for this pc
ipconfig
pause
