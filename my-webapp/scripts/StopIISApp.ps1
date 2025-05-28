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
Import-Module WebAdministration
Write-Host "Stopping IIS website..."
Stop-Website -Name "Default Web Site" # 假设应用部署在Default Web Site
Write-Host "IIS website stopped."