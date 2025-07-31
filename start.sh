#!/bin/bash
# start.sh

# Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

# Ejecutar la aplicación
uvicorn main:app --host 0.0.0.0 --port 10000
