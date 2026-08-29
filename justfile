python := ".venv/bin/python"
pip := ".venv/bin/pip"

# List available recipes
default:
    @just --list

# Create .venv if needed and install dependencies from requirements.txt
install:
    python3 -m venv .venv
    {{pip}} install -r requirements.txt

# Run main.py using the project virtualenv
run:
    {{python}} main.py
