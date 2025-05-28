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
function Test-Health {
    param (
        [string]$url,
        [string]$expectedContent
    )

    Write-Host "Checking $url ..."
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200 -and $response.Content -match $expectedContent) {
            Write-Host "Health check passed for $url"
        } else {
            Write-Error "Health check failed at ${url}. Status: $($response.StatusCode), Content: $($response.Content)"
            exit 1
        }
    } catch {
        Write-Error "Exception checking ${url}: $($_.Exception.Message)"
        exit 1
    }
}  
Test-Health -url "http://localhost/MyWebApp/health.html" -expectedContent "Health Check OK"
Test-Health -url "http://localhost/health.html" -expectedContent "Health Check OK"

exit 0