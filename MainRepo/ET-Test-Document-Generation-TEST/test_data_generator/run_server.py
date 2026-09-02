"""Entry point. Runs app.py with this directory as the working directory so its
relative paths resolve no matter where the script is invoked from."""

import os

import uvicorn

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8420")),
    )
