#!/bin/bash

# Avoid problems with ownership by container versus host user
git config --global --add safe.directory '*'

sudo apt-get update
sudo apt-get install tesseract-ocr poppler-utils

# Ensure the Docker daemon socket is available to the vscode user
sudo chown root:docker /var/run/docker.sock
sudo chmod 660 /var/run/docker.sock
sudo usermod -aG docker vscode

# Make ruff etcetera available to the vscode user
pip install --upgrade pip
pip install -r ./.devcontainer/dev-requirements.txt
