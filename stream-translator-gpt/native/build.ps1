param([string]$OutputDirectory = (Join-Path $PSScriptRoot '../stream_translator_gpt/native'))
$ErrorActionPreference = 'Stop'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (!(Test-Path $vswhere)) { throw 'Visual Studio Build Tools with Desktop C++ is required.' }
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$installation) { throw 'No Visual Studio C++ toolchain was found.' }
$vcvars = Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force $output | Out-Null
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ('floatwindow-process-audio-' + [guid]::NewGuid())
New-Item -ItemType Directory $temp | Out-Null
try {
    $source = Join-Path $PSScriptRoot 'process_audio_capture.cpp'
    $dll = Join-Path $output 'process_audio_capture.dll'
    # All paths passed to cmd are fixed filesystem paths, not enumerated delete targets.
    $command = 'call "' + $vcvars + '" >nul && cl /nologo /std:c++17 /EHsc /O2 /W4 /MT /LD "' + $source + '" /Fo"' + (Join-Path $temp 'capture.obj') + '" /link /OUT:"' + $dll + '" /IMPLIB:"' + (Join-Path $temp 'capture.lib') + '" ole32.lib Mmdevapi.lib'
    & $env:ComSpec /d /c $command
    if ($LASTEXITCODE -ne 0) { throw "Native compilation failed ($LASTEXITCODE)." }
    Write-Output "Built $dll"
} finally {
    # This unique directory was created by this build and stays under the temp root.
    if (([System.IO.Path]::GetFullPath($temp)).StartsWith([System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()), [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $temp -Recurse -Force
    }
}
