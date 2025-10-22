$ErrorActionPreference = "Stop"

#  Corrected ZIP URL
$ffmpegUrl = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-release-full.zip"
$zipPath = "$env:TEMP\ffmpeg-release-full.zip"
$targetDir = "C:\ffmpeg"

Write-Host "Downloading FFmpeg..."
Invoke-WebRequest -Uri $ffmpegUrl -OutFile $zipPath

if (-Not (Test-Path $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir | Out-Null
}

Write-Host "Extracting FFmpeg..."
Expand-Archive -Path $zipPath -DestinationPath $targetDir -Force

$ffmpegSub = Get-ChildItem $targetDir -Directory | Where-Object { $_.Name -like "ffmpeg-*" } | Select-Object -First 1
$binPath = Join-Path $ffmpegSub.FullName "bin"

$existingPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($existingPath -notlike "*$binPath*") {
    Write-Host "Adding FFmpeg to system PATH..."
    $newPath = "$existingPath;$binPath"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
} else {
    Write-Host "FFmpeg path already exists in PATH."
}

Write-Host "Verifying FFmpeg installation..."
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
Start-Sleep -Seconds 1
ffmpeg -version
