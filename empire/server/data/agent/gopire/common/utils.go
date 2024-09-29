package common

import (
	"fmt"
	"math/rand"
	"os/exec"
	"runtime"
	"strconv"
)

func RunCommand(command string) string {
	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		cmd = exec.Command("powershell", "-Command", command)
	} else {
		cmd = exec.Command("sh", "-c", command)
	}

	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Sprintf("Error: %v, Output: %s", err, string(output))
	}
	return string(output)
}

func Atoi(s string) int {
	i, _ := strconv.Atoi(s)
	return i
}

func RandomInt(min, max int) int {
	if max <= min {
		return min
	}
	return rand.Intn(max-min) + min
}
