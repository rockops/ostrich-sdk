package main

import (
	"fmt"
	"io/ioutil"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type Config struct {
	Endpoint string
	Port     string
	UUID     string
}

func getOstrichDir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".ostrich")
}

func readConfig(name string) (*Config, error) {
	path := filepath.Join(getOstrichDir(), name+".conf")
	data, err := ioutil.ReadFile(path)
	if err != nil {
		return nil, err
	}

	conf := &Config{}
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		parts := strings.SplitN(line, "=", 2)
		if len(parts) == 2 {
			key := strings.TrimSpace(parts[0])
			val := strings.TrimSpace(parts[1])
			switch key {
			case "DEFENDPOINT":
				conf.Endpoint = val
			case "DEFPORT":
				conf.Port = val
			case "EPUUID":
				conf.UUID = val
			}
		}
	}
	return conf, nil
}

func writeConfig(name string, conf *Config) error {
	dir := getOstrichDir()
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}

	path := filepath.Join(dir, name+".conf")
	content := fmt.Sprintf("DEFENDPOINT=%s\nDEFPORT=%s\nEPUUID=%s\n", conf.Endpoint, conf.Port, conf.UUID)
	return ioutil.WriteFile(path, []byte(content), 0600)
}

func getCurrentEndpoint() (string, error) {
	data, err := ioutil.ReadFile(filepath.Join(getOstrichDir(), "current"))
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(data)), nil
}

func setCurrentEndpoint(name string) error {
	return ioutil.WriteFile(filepath.Join(getOstrichDir(), "current"), []byte(name), 0600)
}

func listEndpoints() ([]string, error) {
	files, err := ioutil.ReadDir(getOstrichDir())
	if err != nil {
		return nil, err
	}

	var endpoints []string
	for _, f := range files {
		if strings.HasSuffix(f.Name(), ".conf") {
			endpoints = append(endpoints, strings.TrimSuffix(f.Name(), ".conf"))
		}
	}
	sort.Strings(endpoints)
	return endpoints, nil
}
