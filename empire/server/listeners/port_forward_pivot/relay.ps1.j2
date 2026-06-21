$ErrorActionPreference = "Stop"

$listenAddress = [System.Net.IPAddress]::Parse("{{ listen_host }}")
$connectHost = "{{ connect_host }}"
$connectPort = {{ connect_port }}

try {
    $listener = [System.Net.Sockets.TcpListener]::new($listenAddress, {{ listen_port }})
    $listener.Start()
    Write-Output "[port_forward_pivot] LISTEN_OK {{ listen_host }}:{{ listen_port }}"
} catch {
    Write-Output "[port_forward_pivot] LISTEN_FAIL {{ listen_host }}:{{ listen_port }}: $_"
    return
}

$pool = [runspacefactory]::CreateRunspacePool(1, 32)
$pool.Open()

$handler = {
    param($client, $connectHost, $connectPort)
    $upstream = $null
    try {
        $upstream = [System.Net.Sockets.TcpClient]::new()
        $upstream.Connect($connectHost, $connectPort)
        $cs = $client.GetStream()
        $us = $upstream.GetStream()
        $t1 = $cs.CopyToAsync($us)
        $t2 = $us.CopyToAsync($cs)
        [System.Threading.Tasks.Task]::WaitAny(@($t1, $t2)) | Out-Null
    } catch {
        Write-Output "[port_forward_pivot] upstream error: $_"
    } finally {
        if ($client) { $client.Close() }
        if ($upstream) { $upstream.Close() }
    }
}

$inflight = New-Object System.Collections.Generic.List[object]

while ($true) {
    try {
        $client = $listener.AcceptTcpClient()
    } catch {
        Write-Output "[port_forward_pivot] accept loop terminated: $_"
        break
    }

    for ($i = $inflight.Count - 1; $i -ge 0; $i--) {
        if ($inflight[$i].handle.IsCompleted) {
            try { $inflight[$i].ps.EndInvoke($inflight[$i].handle) } catch {}
            $inflight[$i].ps.Dispose()
            $inflight.RemoveAt($i)
        }
    }

    $ps = [powershell]::Create()
    $ps.RunspacePool = $pool
    [void]$ps.AddScript($handler).AddArgument($client).AddArgument($connectHost).AddArgument($connectPort)
    $handle = $ps.BeginInvoke()
    $inflight.Add(@{ ps = $ps; handle = $handle })
}
