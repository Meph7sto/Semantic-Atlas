# Shared .env helpers for local startup scripts.

function ConvertTo-EnvQuotedValue {
  param([AllowNull()][string]$Value)
  if ($null -eq $Value) { return '""' }
  $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
  return "`"$escaped`""
}

function ConvertFrom-EnvValue {
  param([AllowNull()][string]$Value)
  if ($null -eq $Value) { return "" }

  $trimmed = $Value.Trim()
  if ($trimmed.Length -ge 2 -and $trimmed.StartsWith('"') -and $trimmed.EndsWith('"')) {
    $inner = $trimmed.Substring(1, $trimmed.Length - 2)
    return $inner.Replace('\"', '"').Replace('\\', '\')
  }
  if ($trimmed.Length -ge 2 -and $trimmed.StartsWith("'") -and $trimmed.EndsWith("'")) {
    return $trimmed.Substring(1, $trimmed.Length - 2)
  }

  return $trimmed
}

function Load-EnvFile {
  param([Parameter(Mandatory = $true)][string]$EnvFile)

  if (-not (Test-Path $EnvFile)) {
    return
  }

  Write-Host "[start] Loading secrets from .env..." -ForegroundColor Cyan
  Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
      $name = $matches[1].Trim()
      $value = ConvertFrom-EnvValue $matches[2]
      if (-not [Environment]::GetEnvironmentVariable($name)) {
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
      }
    }
  }
}

function Save-EnvValue {
  param(
    [Parameter(Mandatory = $true)][string]$EnvFile,
    [Parameter(Mandatory = $true)][string]$Name,
    [AllowNull()][string]$Value
  )

  $parent = Split-Path -Parent $EnvFile
  if ($parent -and -not (Test-Path $parent)) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
  }

  $pattern = '^\s*' + [regex]::Escape($Name) + '\s*='
  if ((Test-Path $EnvFile) -and (Select-String -Path $EnvFile -Pattern $pattern -Quiet)) {
    return $false
  }

  Add-Content -Path $EnvFile -Value "$Name=$(ConvertTo-EnvQuotedValue $Value)" -Encoding UTF8
  return $true
}
