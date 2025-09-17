#!/usr/bin/env python3
"""
Setup script for the RPG client - creates virtual environment and installs dependencies.
"""

import subprocess
import sys
import os
import venv
from pathlib import Path


def create_venv():
    """Create a virtual environment for the client."""
    venv_path = Path("client_venv")

    if venv_path.exists():
        print("🔄 Virtual environment already exists, removing old one...")
        import shutil

        shutil.rmtree(venv_path)

    print("📦 Creating virtual environment...")
    venv.create(venv_path, with_pip=True)

    # Get the python executable path
    if sys.platform == "win32":
        python_exe = venv_path / "Scripts" / "python.exe"
        pip_exe = venv_path / "Scripts" / "pip.exe"
    else:
        python_exe = venv_path / "bin" / "python"
        pip_exe = venv_path / "bin" / "pip"

    return python_exe, pip_exe


def install_dependencies(python_exe):
    """Install required dependencies using poetry."""
    print("📦 Installing dependencies with poetry...")

    # Get current working directory (should be the project root)
    project_root = Path.cwd()

    # Check if poetry is available in the venv
    try:
        result = subprocess.run(
            [str(python_exe), "-m", "poetry", "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print("   Installing poetry...")
            subprocess.run(
                [str(python_exe), "-m", "pip", "install", "poetry"],
                check=True,
                capture_output=True,
            )
    except Exception as e:
        print(f"   Installing poetry: {e}")
        subprocess.run(
            [str(python_exe), "-m", "pip", "install", "poetry"],
            check=True,
            capture_output=True,
        )

    # Install client dependencies with poetry
    print("   Installing client dependencies...")
    try:
        # Run poetry install from the project root
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = str(python_exe.parent.parent)  # Set venv path

        subprocess.run(
            [str(python_exe), "-m", "poetry", "install", "--only=client"],
            check=True,
            capture_output=True,
            cwd=str(project_root),
            env=env,
        )
        print("   ✅ Client dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed to install dependencies with poetry: {e}")
        print("   Falling back to pip...")
        # Fallback to pip installation
        deps = [
            "pygame>=2.5.0",
            "websockets>=11.0",
            "aiohttp>=3.8.0",
            "msgpack>=1.0.0",
            "pydantic>=2.0.0",
        ]

        pip_exe = python_exe.parent / "pip"
        for dep in deps:
            print(f"   Installing {dep}...")
            try:
                subprocess.run(
                    [str(pip_exe), "install", dep], check=True, capture_output=True
                )
                print(f"   ✅ {dep} installed")
            except subprocess.CalledProcessError as pip_e:
                print(f"   ❌ Failed to install {dep}: {pip_e}")
                return False
        print("   ✅ All dependencies installed via pip")

    return True


def create_run_script(python_exe):
    """Create a run script for the client."""
    if sys.platform == "win32":
        script_content = f"""@echo off
echo 🎮 Starting RPG Client...
echo Make sure the server is running on localhost:8000
echo Use WASD or arrow keys to move
echo Press Ctrl+C to quit
echo.
"{python_exe}" client/src/client.py
pause
"""
        script_path = "run_client.bat"
    else:
        script_content = f"""#!/bin/bash
echo "🎮 Starting RPG Client..."
echo "Make sure the server is running on localhost:8000"
echo "Use WASD or arrow keys to move"
echo "Press Ctrl+C to quit"
echo ""
"{python_exe}" client/src/client.py
"""
        script_path = "run_client.sh"

    with open(script_path, "w") as f:
        f.write(script_content)

    if sys.platform != "win32":
        os.chmod(script_path, 0o755)

    print(f"✅ Created {script_path}")
    return script_path


def main():
    """Main setup function."""
    print("🎮 RPG CLIENT SETUP")
    print("=" * 30)

    # Check if we're in the right directory
    if not Path("client/src/client.py").exists():
        print("❌ Please run this script from the rpg2 root directory")
        return

    try:
        # Create virtual environment
        python_exe, pip_exe = create_venv()

        # Install dependencies
        if not install_dependencies(python_exe):
            print("❌ Failed to install dependencies")
            return

        # Create run script
        script_path = create_run_script(python_exe)

        print("\n🎉 SETUP COMPLETE!")
        print("✅ Virtual environment created")
        print("✅ Dependencies installed")
        print("✅ Run script created")
        print(f"\n🚀 To start the client, run: ./{script_path}")
        print("\nMake sure the server is running first:")
        print("  cd docker && docker compose up server -d")

    except Exception as e:
        print(f"❌ Setup failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
