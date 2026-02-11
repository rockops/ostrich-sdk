package main

import (
	"fmt"
	"os"
	"strings"
	"unicode/utf16"

	"gopkg.in/yaml.v3"
)

// pathJoin joins path parts using forward slashes for remote Linux paths
func pathJoin(parts ...string) string {
	return strings.Join(parts, "/")
}

// readEncodedFile reads a file and handles UTF-8 (with/without BOM) and UTF-16 (BE/LE)
func readEncodedFile(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}

	if len(data) >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF {
		// UTF-8 BOM
		return string(data[3:]), nil
	}

	if len(data) >= 2 {
		if data[0] == 0xFF && data[1] == 0xFE {
			// UTF-16LE
			u16 := make([]uint16, (len(data)-2)/2)
			for i := 0; i < len(u16); i++ {
				u16[i] = uint16(data[2+i*2]) | uint16(data[3+i*2])<<8
			}
			return string(utf16.Decode(u16)), nil
		} else if data[0] == 0xFE && data[1] == 0xFF {
			// UTF-16BE
			u16 := make([]uint16, (len(data)-2)/2)
			for i := 0; i < len(u16); i++ {
				u16[i] = uint16(data[2+i*2])<<8 | uint16(data[3+i*2])
			}
			return string(utf16.Decode(u16)), nil
		}
	}

	// Default to UTF-8
	return string(data), nil
}

// loadYaml loads a YAML file into a map, handling encodings
func loadYaml(path string) (map[string]interface{}, error) {
	content, err := readEncodedFile(path)
	if err != nil {
		return nil, err
	}

	var data map[string]interface{}
	err = yaml.Unmarshal([]byte(content), &data)
	if err != nil {
		return nil, err
	}

	return data, nil
}

// getYamlPathValue safely extracts a value from a nested map using a dot-separated path
func getYamlPathValue(data map[string]interface{}, path string) string {
	parts := strings.Split(path, ".")
	var current interface{} = data

	for _, part := range parts {
		m, ok := current.(map[string]interface{})
		if !ok {
			return ""
		}
		current, ok = m[part]
		if !ok {
			return ""
		}
	}

	if current == nil {
		return ""
	}
	return fmt.Sprintf("%v", current)
}
