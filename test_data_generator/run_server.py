"""Launches app.py with its own directory as the working directory, so its
relative paths (StaticFiles(directory="frontend"), etc.) resolve correctly
regardless of where this script is invoked from."""

import os
import uvicorn

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8420)