import subprocess
import sys
from pathlib import Path


def main() -> None:
    app_path = Path(__file__).resolve().parents[1] / "src" / "dashboard" / "app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(app_path), *sys.argv[1:]]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
