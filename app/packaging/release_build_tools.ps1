function Resolve-SevenZipPath {
    param([string]$RequestedPath = "")

    $candidates = @(@(
        $RequestedPath,
        (Join-Path $env:ProgramFiles "7-Zip\7z.exe"),
        (Join-Path $env:ProgramFiles "7-Zip\7zz.exe"),
        (Get-Command 7z.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
    ) | Where-Object { $_ -and (Test-Path $_) })

    if (-not $candidates) {
        throw "7-Zip was not found. Install 7-Zip or pass -SevenZipPath."
    }
    return (Resolve-Path $candidates[0]).Path
}

function Remove-BuildDirectoryFast {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$AllowedRoot
    )

    if (-not (Test-Path -LiteralPath $Path)) { return }
    $resolvedPath = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path).TrimEnd('\')
    $resolvedRoot = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $AllowedRoot).Path).TrimEnd('\')
    if (-not $resolvedPath.StartsWith($resolvedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear build directory outside allowed root: $resolvedPath"
    }

    $emptyDir = Join-Path $resolvedRoot (".empty-build-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $emptyDir -Force | Out-Null
    try {
        & robocopy.exe $emptyDir $resolvedPath /MIR /R:0 /W:0 /NFL /NDL /NP /NJH /NJS
        $robocopyExitCode = $LASTEXITCODE
        if ($robocopyExitCode -ge 8) {
            throw "Robocopy cleanup failed with exit code $robocopyExitCode`: $resolvedPath"
        }
    } finally {
        if (Test-Path -LiteralPath $emptyDir) {
            Remove-Item -LiteralPath $emptyDir -Force
        }
    }
    Remove-Item -LiteralPath $resolvedPath -Force
    $global:LASTEXITCODE = 0
}

function Invoke-FastDirectoryCopy {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [ValidateRange(1, 128)][int]$Threads = 16
    )

    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "Copy source directory not found: $Source"
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    & robocopy.exe $Source $Destination /E "/MT:$Threads" /R:2 /W:1 /NFL /NDL /NP /NJH /NJS
    $robocopyExitCode = $LASTEXITCODE
    if ($robocopyExitCode -ge 8) {
        throw "Robocopy failed with exit code $robocopyExitCode`: $Source -> $Destination"
    }
    $global:LASTEXITCODE = 0
}

function Invoke-FastDirectoryCopyExcluding {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string[]]$Exclude = @(),
        [ValidateRange(1, 128)][int]$Threads = 16
    )

    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "Copy source directory not found: $Source"
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    $arguments = @($Source, $Destination, "/E", "/MT:$Threads", "/R:2", "/W:1", "/NFL", "/NDL", "/NP", "/NJH", "/NJS")
    if ($Exclude.Count -gt 0) {
        $arguments += "/XD"
        $arguments += $Exclude
        $arguments += "/XF"
        $arguments += $Exclude
    }
    & robocopy.exe @arguments
    $robocopyExitCode = $LASTEXITCODE
    if ($robocopyExitCode -ge 8) {
        throw "Robocopy failed with exit code $robocopyExitCode`: $Source -> $Destination"
    }
    $global:LASTEXITCODE = 0
}

function Compress-ReleaseDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$SevenZipPath,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$ItemName,
        [Parameter(Mandatory = $true)][string]$Destination,
        [ValidateRange(0, 9)][int]$CompressionLevel = 7
    )

    if (-not (Test-Path -LiteralPath (Join-Path $WorkingDirectory $ItemName))) {
        throw "Archive input not found: $(Join-Path $WorkingDirectory $ItemName)"
    }
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Force
    }

    Push-Location $WorkingDirectory
    try {
        & $SevenZipPath a -tzip -mm=Deflate "-mx=$CompressionLevel" -mmt=on $Destination $ItemName | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "7-Zip compression failed with exit code $LASTEXITCODE`: $Destination"
        }
    } finally {
        Pop-Location
    }
}

function Test-ReleaseZip {
    param(
        [Parameter(Mandatory = $true)][string]$SevenZipPath,
        [Parameter(Mandatory = $true)][string]$Path
    )

    & $SevenZipPath t $Path | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "7-Zip archive validation failed: $Path"
    }
}

function Split-ReleaseFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [ValidateRange(64, 2047)][int]$PartSizeMiB = 1900
    )

    $source = Get-Item -LiteralPath $Path
    $partSize = [int64]$PartSizeMiB * 1MB
    $partCount = [int][Math]::Ceiling($source.Length / [double]$partSize)
    $partWidth = [Math]::Max(2, $partCount.ToString().Length)
    $directory = $source.DirectoryName
    $prefix = "$($source.Name).part"

    Get-ChildItem -LiteralPath $directory -File |
        Where-Object { $_.Name -match "^$([regex]::Escape($prefix))\d+$" } |
        Remove-Item -Force

    $buffer = New-Object byte[] (8MB)
    $input = [IO.File]::OpenRead($source.FullName)
    $parts = @()
    try {
        for ($partIndex = 1; $partIndex -le $partCount; $partIndex++) {
            $partPath = Join-Path $directory ($prefix + $partIndex.ToString("D$partWidth"))
            $output = [IO.File]::Create($partPath)
            try {
                $remaining = [Math]::Min($partSize, $source.Length - $input.Position)
                while ($remaining -gt 0) {
                    $requested = [int][Math]::Min($buffer.Length, $remaining)
                    $read = $input.Read($buffer, 0, $requested)
                    if ($read -le 0) { throw "Unexpected end of file while splitting $Path" }
                    $output.Write($buffer, 0, $read)
                    $remaining -= $read
                }
            } finally {
                $output.Dispose()
            }
            $parts += Get-Item -LiteralPath $partPath
        }
    } finally {
        $input.Dispose()
    }
    return $parts
}

function Test-SplitReleaseFile {
    param(
        [Parameter(Mandatory = $true)][string]$OriginalPath,
        [Parameter(Mandatory = $true)][System.IO.FileInfo[]]$Parts,
        [Parameter(Mandatory = $true)][string]$SevenZipPath
    )

    $original = Get-Item -LiteralPath $OriginalPath
    $recombinedPath = Join-Path $original.DirectoryName "$($original.Name).recombined.tmp"
    if (Test-Path -LiteralPath $recombinedPath) {
        Remove-Item -LiteralPath $recombinedPath -Force
    }

    $output = [IO.File]::Create($recombinedPath)
    try {
        foreach ($part in ($Parts | Sort-Object Name)) {
            $input = [IO.File]::OpenRead($part.FullName)
            try { $input.CopyTo($output) } finally { $input.Dispose() }
        }
    } finally {
        $output.Dispose()
    }

    try {
        $originalHash = (Get-FileHash -LiteralPath $original.FullName -Algorithm SHA256).Hash
        $recombinedHash = (Get-FileHash -LiteralPath $recombinedPath -Algorithm SHA256).Hash
        if ($originalHash -ne $recombinedHash) {
            throw "Split package recombination hash mismatch: $($original.Name)"
        }
        Test-ReleaseZip -SevenZipPath $SevenZipPath -Path $recombinedPath | Out-Host
        return $originalHash
    } finally {
        if (Test-Path -LiteralPath $recombinedPath) {
            Remove-Item -LiteralPath $recombinedPath -Force
        }
    }
}
