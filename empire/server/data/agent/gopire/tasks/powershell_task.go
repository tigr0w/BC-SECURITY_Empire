package tasks

import (
	"bytes"
	"fmt"
	"io/ioutil"
	"os"
	"os/exec"
)

func RunPowerShellScript(script string) string {
	// Prepare the PowerShell command
	cmd := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", script)

	// Capture the output
	var out bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &stderr

	// Execute the command
	err := cmd.Run()
	if err != nil {
		return fmt.Sprintf("Error: %v, Output: %s", err, stderr.String())
	}

	return out.String()
}

func RunTempPowerShellScript(script string) string {
	// Create a temporary file to store the PowerShell script
	tmpFile, err := ioutil.TempFile("", "script-*.ps1")
	if err != nil {
		return fmt.Sprintf("Error creating temp file: %v", err)
	}

	// Write the PowerShell script to the temporary file
	_, err = tmpFile.Write([]byte(script))
	if err != nil {
		return fmt.Sprintf("Error writing to temp file: %v", err)
	}

	// Close the file so it can be read by the PowerShell process
	err = tmpFile.Close()
	if err != nil {
		return fmt.Sprintf("Error closing temp file: %v", err)
	}

	// Prepare the PowerShell command
	cmd := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", tmpFile.Name())

	// Capture the output
	var out bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &stderr

	// Execute the command
	err = cmd.Run()
	if err != nil {
		return fmt.Sprintf("Error: %v, Output: %s", err, stderr.String())
	}

	os.Remove(tmpFile.Name())
	return out.String()
}
