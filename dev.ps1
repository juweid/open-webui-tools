# Set the development environment variables
$env:DATA_DIR="./data"
$env:WEBUI_AUTH="False"

# Check if the executable exists, then launch it directly
if (Test-Path ".\.venv\Scripts\open-webui.exe") {
    Write-Host "Launching Open WebUI in Dev Mode..." -ForegroundColor Green
    .\.venv\Scripts\open-webui serve
} else {
    Write-Host "Error: Could not find Open WebUI inside .venv\Scripts\" -ForegroundColor Red
    Write-Host "Please make sure you ran 'uv pip install open-webui' inside this folder." -ForegroundColor Yellow
}
