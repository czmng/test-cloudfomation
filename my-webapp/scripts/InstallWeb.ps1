# Ensure the script is running in 64-bit PowerShell (required for WebAdministration / IIS)
if ($PSHOME -like "*SysWOW64*")
{
  Write-Warning "Restarting this script under 64-bit Windows PowerShell."

  # Restart this script under 64-bit Windows PowerShell.
  #   (\SysNative\ redirects to \System32\ for 64-bit mode)

  & (Join-Path ($PSHOME -replace "SysWOW64", "SysNative") powershell.exe) -File `
    (Join-Path $PSScriptRoot $MyInvocation.MyCommand) @args

  # Exit 32-bit script.

  Exit $LastExitCode
}
# Destination path where files are ALREADY copied by appspec.yml's "files" section
$destinationPath = "C:\inetpub\wwwroot\MyWebApp"

# Path to the root of the unzipped deployment bundle.
# $PSScriptRoot is the 'scripts' directory within the bundle.
# So, the parent of $PSScriptRoot is the bundle's root.
$bundleRootPath = Split-Path -Path $PSScriptRoot -Parent

Write-Host "PSScriptRoot (script location): $PSScriptRoot"
Write-Host "BundleRootPath (deployment package root): $bundleRootPath"
Write-Host "DestinationPath (IIS physical path, files already copied here by CodeDeploy): $destinationPath"

# Ensure application directory exists (CodeDeploy's 'files' section should create it, but -Force makes this safe)
Write-Host "Ensuring application directory $destinationPath exists..."
New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null

# Try importing IIS module
try {
    Import-Module WebAdministration -ErrorAction Stop
} catch {
    Write-Error "Failed to import WebAdministration module. Ensure IIS is installed and PowerShell module is available."
    exit 1
}

$siteName = "Default Web Site"
$appPoolName = "MyAppPool"
# The application path in IIS, e.g., /MyWebApp. The name part 'MyWebApp' is also used for New-WebApplication
$iisAppPathName = "MyWebApp" # This will be used for the -Name parameter and in the IIS path

# Ensure Default Web Site exists
if (-not (Test-Path "IIS:\Sites\$siteName")) {
    Write-Error "Default Web Site '$siteName' does not exist. Ensure IIS is installed and created."
    exit 1
}

# Create or reuse App Pool
if (-not (Test-Path "IIS:\AppPools\$appPoolName")) {
    Write-Host "Creating App Pool: $appPoolName"
    New-WebAppPool -Name $appPoolName
    Set-ItemProperty -Path "IIS:\AppPools\$appPoolName" -Name managedRuntimeVersion -Value "v4.0"
} else {
    Write-Host "App Pool '$appPoolName' already exists."
    Set-ItemProperty -Path "IIS:\AppPools\$appPoolName" -Name managedRuntimeVersion -Value "v4.0" -ErrorAction SilentlyContinue
}

# Create or update Web Application
$fullIisAppPath = "IIS:\Sites\$siteName\$iisAppPathName"

if (-not (Test-Path $fullIisAppPath)) {
    Write-Host "Creating Web Application: $iisAppPathName under $siteName"
    New-WebApplication -Name $iisAppPathName -Site $siteName -PhysicalPath $destinationPath -ApplicationPool $appPoolName
} else {
    Write-Host "Web Application $iisAppPathName already exists. Updating path and app pool."
    Set-ItemProperty -Path $fullIisAppPath -Name PhysicalPath -Value $destinationPath
    Set-ItemProperty -Path $fullIisAppPath -Name applicationPool -Value $appPoolName
}

# Version tagging
$appVersion = "UnknownVersion"
$versionFile = Join-Path $bundleRootPath "version.txt"
Write-Host "Looking for version file at: ${versionFile}"

if (Test-Path $versionFile) {
    $appVersion = (Get-Content $versionFile -Raw).Trim()
    Write-Host "Version read from ${versionFile}: $appVersion"
} else {
    $appVersion = "Dynamic-" + (Get-Date -Format "yyyyMMddHHmmss")
    Write-Host "version.txt not found at '${versionFile}'. Using dynamic version: $appVersion"
}

$versionSuffix = "-Canary" # Default suffix
$versionSuffixToSetColor = $null

if ($appVersion -match "^\d+\.\d+\.\d+$") {
    $major = [int]($appVersion.Split('.')[0])
    if ($major % 2 -eq 0) {
        $versionSuffix = "-GREEN"
    } else {
        $versionSuffix = "-BLUE"
    }
} elseif ($appVersion -match "(-GREEN|-BLUE)$") {
    $versionSuffix = ""
    if ($appVersion -match "-GREEN$") { $versionSuffixToSetColor = "-GREEN" }
    if ($appVersion -match "-BLUE$")  { $versionSuffixToSetColor = "-BLUE" }
} else {
    Write-Host "Version '$appVersion' is not in X.Y.Z format. Using default suffix '$versionSuffix'."
    $versionSuffixToSetColor = $versionSuffix
}

if ($versionSuffixToSetColor -eq $null -and $versionSuffix -ne "") {
    $versionSuffixToSetColor = $versionSuffix
}

[System.Environment]::SetEnvironmentVariable("APP_VERSION", "$appVersion$versionSuffix", "Machine")
Write-Host "APP_VERSION set to: $appVersion$versionSuffix"

$appVersionColor = "orange" # Default for Canary or unknown
if ($versionSuffixToSetColor -eq "-BLUE") {
    $appVersionColor = "blue"
} elseif ($versionSuffixToSetColor -eq "-GREEN") {
    $appVersionColor = "green"
}
[System.Environment]::SetEnvironmentVariable("APP_VERSION_COLOR", $appVersionColor, "Machine")
Write-Host "APP_VERSION_COLOR set to: $appVersionColor"

# Health check file inside the app folder
$rootHealthFilePath = Join-Path $destinationPath "health.html"
"<html><body><h1>Application Health Check OK! ($appVersion$versionSuffix)</h1></body></html>" | Out-File $rootHealthFilePath -Encoding UTF8 -Force

Copy-Item -Path $rootHealthFilePath -Destination "C:\inetpub\wwwroot\health.html" -Force
Write-Host "Copied health.html to C:\inetpub\wwwroot\health.html for root health check."