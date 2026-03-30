Run it now

cd trading_bot_v7
python setup.py          # install packages once
python login.py          # every morning

python paper_trading.py  # safe mode — asks for your parameters
# Enter: capital, daily target, max loss, stop loss %, positions
# Open http://localhost:8050

python live_trading.py   # real money — same parameter setup
