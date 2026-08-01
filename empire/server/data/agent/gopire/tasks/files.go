package tasks

import (
	"bytes"
	"compress/zlib"
	"encoding/base64"
	"encoding/binary"
	"fmt"
	"hash/crc32"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// FileUpload writes uploaded file data to disk.
// Supports chunked format "index|total|path|data" or legacy format "path|data".
func FileUpload(data string) (string, error) {
	parts := strings.SplitN(data, "|", 4)

	var chunkIndex, totalChunks int
	var filePath, base64Part string

	if len(parts) == 4 && isDigit(parts[0]) {
		if _, err := fmt.Sscanf(parts[0], "%d", &chunkIndex); err != nil {
			return "", fmt.Errorf("invalid chunk index: %v", err)
		}
		if _, err := fmt.Sscanf(parts[1], "%d", &totalChunks); err != nil {
			return "", fmt.Errorf("invalid total chunks: %v", err)
		}
		filePath = parts[2]
		base64Part = parts[3]
	} else if len(parts) >= 2 {
		chunkIndex = 0
		totalChunks = 1
		filePath = parts[0]
		base64Part = parts[1]
	} else {
		return "", fmt.Errorf("invalid data format for file upload")
	}

	dir := filepath.Dir(filePath)
	if _, err := os.Stat(dir); os.IsNotExist(err) {
		err := os.MkdirAll(dir, 0755)
		if err != nil {
			return "", fmt.Errorf("failed to create directory: %v", err)
		}
	}

	fileInfo, err := os.Stat(filePath)
	if err == nil && fileInfo.IsDir() {
		return "", fmt.Errorf("the provided path is a directory, not a file: %s", filePath)
	}

	rawData, err := base64.StdEncoding.DecodeString(base64Part)
	if err != nil {
		return "", fmt.Errorf("failed to decode base64 content: %v", err)
	}

	var flags int
	if chunkIndex == 0 {
		flags = os.O_CREATE | os.O_WRONLY | os.O_TRUNC
	} else {
		flags = os.O_APPEND | os.O_CREATE | os.O_WRONLY
	}
	file, err := os.OpenFile(filePath, flags, 0644)
	if err != nil {
		return "", fmt.Errorf("failed to open file: %v", err)
	}
	defer file.Close()

	if _, err := file.Write(rawData); err != nil {
		return "", fmt.Errorf("failed to write data to file: %v", err)
	}

	return fmt.Sprintf("[*] Upload of %s successful (chunk %d/%d)", filePath, chunkIndex+1, totalChunks), nil
}

func GetFileList(filePath string) ([]string, error) {
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

func GetFilePart(filePath string, offset int, chunkSize int) ([]byte, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, fmt.Errorf("could not open file: %w", err)
	}
	defer file.Close()

	_, err = file.Seek(int64(offset), io.SeekStart)
	if err != nil {
		return nil, fmt.Errorf("could not seek to offset: %w", err)
	}

	buffer := make([]byte, chunkSize)
	bytesRead, err := file.Read(buffer)
	if err != nil && err != io.EOF {
		return nil, fmt.Errorf("could not read file: %w", err)
	}

	return buffer[:bytesRead], nil
}

// CompressData compresses data using zlib and calculates CRC32 checksum.
func CompressData(data []byte) ([]byte, error) {
	crc := crc32.ChecksumIEEE(data)

	var compressedBuffer bytes.Buffer
	writer, err := zlib.NewWriterLevel(&compressedBuffer, zlib.BestCompression) // Compression level 9
	if err != nil {
		return nil, fmt.Errorf("failed to create zlib writer: %w", err)
	}
	_, err = writer.Write(data)
	if err != nil {
		return nil, fmt.Errorf("failed to compress data: %w", err)
	}
	writer.Close()

	crcHeader := make([]byte, 4)
	binary.BigEndian.PutUint32(crcHeader, crc)
	builtData := append(crcHeader, compressedBuffer.Bytes()...)

	return builtData, nil
}

func isDigit(s string) bool {
	if s == "" {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}
