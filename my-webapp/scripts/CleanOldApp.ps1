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
$appPath = "C:\inetpub\wwwroot\MyWebApp"
Write-Host "Cleaning old application files from $appPath"
if (Test-Path $appPath) {
    Remove-Item -Path "$appPath\*" -Recurse -Force
    Write-Host "Old application files removed."
} else {
    Write-Host "Application path $appPath does not exist. No old files to clean."
}