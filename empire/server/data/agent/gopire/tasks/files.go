package tasks

import (
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func FileUpload(data string) (string, error) {
	// Split the data into file path and base64 content
	parts := strings.Split(data, "|")
	if len(parts) != 2 {
		return "", fmt.Errorf("invalid data format for file upload")
	}

	// First part is the file path
	filePath := parts[0]

	// Second part is the base64-encoded file content
	base64Part := parts[1]

	// Ensure the directory exists
	dir := filepath.Dir(filePath)
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		err := os.MkdirAll(dir, 0755) // Create the directory if it doesn't exist
		if err != nil {
			return "", fmt.Errorf("failed to create directory: %v", err)
		}
	}

	// Check if the filePath is a directory
	fileInfo, err := os.Stat(filePath)
	if err == nil && fileInfo.IsDir() {
		return "", fmt.Errorf("the provided path is a directory, not a file: %s", filePath)
	}

	// Decode the base64 content
	rawData, err := base64.StdEncoding.DecodeString(base64Part)
	if err != nil {
		return "", fmt.Errorf("failed to decode base64 content: %v", err)
	}

	// Append to the file
	file, err := os.OpenFile(filePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return "", fmt.Errorf("failed to open file: %v", err)
	}
	defer file.Close()

	if _, err := file.Write(rawData); err != nil {
		return "", fmt.Errorf("failed to write data to file: %v", err)
	}

	return fmt.Sprintf("Upload of %s successful", filePath), nil
}

func FileDownload(filePath string) ([]string, error) {
	absPath, err := filepath.Abs(filePath)
	if err != nil || !fileExists(absPath) {
		return nil, err
	}

	var fileList []string
	if !isDir(absPath) {
		fileList = append(fileList, absPath)
	} else {
		err := filepath.Walk(absPath, func(path string, info os.FileInfo, err error) error {
			if err == nil && !info.IsDir() {
				fileList = append(fileList, path)
			}
			return nil
		})
		if err != nil {
			return nil, err
		}
	}

	return fileList, nil
}

func GetFileSize(path string) int64 {
	info, err := os.Stat(path)
	if err != nil {
		return 0
	}
	return info.Size()
}

func GetFilePart(filePath string, offset int) ([]byte, error) {
	// Implement the logic to get the file part based on the offset
	// This function should return the file part that packet_handler.go will process
	return nil, nil
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func isDir(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return info.IsDir()
}
