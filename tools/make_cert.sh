#!/bin/sh
# Self-signed HTTPS certificate so Phone 2's browser allows the microphone.
# Run once from the project folder:   sh tools/make_cert.sh
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout certs/robot.key -out certs/robot.crt \
  -subj "/CN=pitop-robot" \
  -addext "subjectAltName=DNS:pitop-robot,DNS:localhost,IP:127.0.0.1"
echo "Done. Restart main.py; open https://<pi-ip>:8000/face and accept the certificate warning once."
