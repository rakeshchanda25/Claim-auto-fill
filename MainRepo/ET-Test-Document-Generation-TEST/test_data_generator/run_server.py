"""Entry point. Runs app.py with this directory as the working directory so its
relative paths resolve no matter where the script is invoked from."""

import os

import uvicorn

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from app import APP_HOST, APP_PORT

    uvicorn.run("app:app", host=APP_HOST, port=APP_PORT)
