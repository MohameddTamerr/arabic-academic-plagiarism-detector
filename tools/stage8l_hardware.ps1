param([Parameter(Mandatory=$true)][string]$OutputFile)
$ErrorActionPreference='Stop'
$record=@{
    collected_utc=[DateTime]::UtcNow.ToString('o')
    cpu=@(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
    computer=Get-CimInstance Win32_ComputerSystem | Select-Object Model,TotalPhysicalMemory,AutomaticManagedPagefile
    windows=Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,FreePhysicalMemory,TotalVirtualMemorySize,FreeVirtualMemory
    pagefile_settings=@(Get-CimInstance Win32_PageFileSetting | Select-Object Name,InitialSize,MaximumSize)
    pagefile_usage=@(Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage,PeakUsage)
    storage=@()
}
try { $record.storage=@(Get-PhysicalDisk | Select-Object MediaType,BusType,Size,HealthStatus) }
catch { $record.storage_error=$_.Exception.Message }
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputFile -Encoding UTF8
