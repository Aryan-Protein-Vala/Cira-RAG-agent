@echo off
echo ========================================================
echo Creating RDP Deployment Package...
echo ========================================================
echo.
echo This will zip the Backend and Frontend folders, excluding 
echo heavy dependencies like node_modules and venv.

if exist cira_rdp_deploy.zip del cira_rdp_deploy.zip

powershell -Command "Add-Type -AssemblyName System.IO.Compression.FileSystem; $compressionLevel = [System.IO.Compression.CompressionLevel]::Optimal; $zipPath = 'cira_rdp_deploy.zip'; $tempDir = 'temp_cira_deploy'; if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }; New-Item -ItemType Directory -Path $tempDir | Out-Null; Copy-Item -Path 'Backend' -Destination \"$tempDir\\Backend\" -Recurse; Copy-Item -Path 'Frontend' -Destination \"$tempDir\\Frontend\" -Recurse; Get-ChildItem -Path $tempDir -Recurse | Where-Object { $_.FullName -match '\\\\venv\\\\' -or $_.FullName -match '\\\\node_modules\\\\' -or $_.FullName -match '\\\\.git\\\\' -or $_.FullName -match '\\\\.next\\\\' -or $_.FullName -match '__pycache__' } | Remove-Item -Recurse -Force; [System.IO.Compression.ZipFile]::CreateFromDirectory($tempDir, $zipPath, $compressionLevel, $false); Remove-Item -Recurse -Force $tempDir"

echo.
echo Done! You can now copy cira_rdp_deploy.zip to your RDP machine.
pause
