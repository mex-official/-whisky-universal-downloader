import os, subprocess, sys

def test_healthcheck_missing_token():
    env=dict(os.environ); env.pop("TELEGRAM_BOT_TOKEN",None)
    p=subprocess.run([sys.executable,"healthcheck.py"],env=env,capture_output=True,text=True)
    assert p.returncode == 1 and "NOT_CONFIGURED" in p.stdout

def test_healthcheck_configured_token():
    env=dict(os.environ); env["TELEGRAM_BOT_TOKEN"]="placeholder"
    p=subprocess.run([sys.executable,"healthcheck.py"],env=env,capture_output=True,text=True)
    assert p.returncode == 0 and p.stdout.strip()=="CONFIGURED"
