# Run a queue command under Git Bash while keeping Windows from idle-sleeping (the 16 and 20 Oct
# queues died when the laptop slept on battery). Lid close, restart or shutdown still stop it.
# Usage: powershell -File scripts/queue_keepawake.ps1 -CmdFile logs/<queue>.cmd.txt
param([Parameter(Mandatory)][string]$CmdFile)
Add-Type -Namespace W -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
[W.Power]::SetThreadExecutionState(0x80000001) | Out-Null  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
& "C:\Program Files\Git\bin\bash.exe" -lc (Get-Content -Raw $CmdFile)
[W.Power]::SetThreadExecutionState(0x80000000) | Out-Null
