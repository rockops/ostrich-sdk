package main

import (
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

func cmdRun(args []string) {
	configFile := "ostrich.yaml"

	// Parse flags and task args
	var flags []string
	var taskArgs []string

	for i := 0; i < len(args); i++ {
		arg := args[i]
		if arg == "-f" || arg == "--file" {
			if i+1 < len(args) {
				configFile = args[i+1]
				i++
			}
			continue
		}
		if strings.HasPrefix(arg, "-") {
			flags = append(flags, arg)
			// Handle other flags with values if necessary. For now, we assume simple flags like -d
			// If we need to support more, we should add them here.
			continue
		}
		taskArgs = append(taskArgs, arg)
	}

	// Read config file locally
	absConfigPath, err := filepath.Abs(configFile)
	if err != nil {
		slog.Error(fmt.Sprintf("Error getting absolute path of config file: %v", err))
		os.Exit(1)
	}

	if _, err := os.Stat(absConfigPath); os.IsNotExist(err) {
		slog.Error(fmt.Sprintf("Error: Config file %s not found", configFile))
		os.Exit(1)
	}

	configDir := filepath.Dir(absConfigPath)

	// Get plugin name and input folder using yq
	pluginName := getYqValue(absConfigPath, ".plugin.name")
	if pluginName == "" || pluginName == "null" {
		pluginName = "unknown"
	}

	inputFolder := getYqValue(absConfigPath, ".template.input")

	runOnRemote(func(c *SSHClient) error {
		// Use UUID and pluginName for the remote directory to avoid collisions
		remoteDir := filepath.Join(c.config.UUID, pluginName)

		slog.Debug(fmt.Sprintf("Preparing remote directory: %s", remoteDir))
		if err := c.Run(fmt.Sprintf("mkdir -p %s", remoteDir)); err != nil {
			return err
		}

		// Sync config file to the remote directory
		// We use the same name as the local config file for consistency
		configBase := filepath.Base(configFile)
		remoteConfigPath := filepath.Join(remoteDir, configBase)
		slog.Debug(fmt.Sprintf("Syncing config file: %s -> %s", configFile, remoteConfigPath))
		if err := c.PutFile(absConfigPath, remoteConfigPath); err != nil {
			return err
		}

		// Sync input folder if it exists
		if inputFolder != "" && inputFolder != "null" {
			absInputPath := filepath.Join(configDir, inputFolder)
			// Check if local input folder exists
			if info, err := os.Stat(absInputPath); err == nil && info.IsDir() {
				remoteInputPath := filepath.Join(remoteDir, inputFolder)
				slog.Debug(fmt.Sprintf("Syncing input folder: %s -> %s", inputFolder, remoteInputPath))
				if err := c.Sync(absInputPath, remoteInputPath); err != nil {
					return err
				}
			} else if err != nil {
				slog.Warn(fmt.Sprintf("Input folder %s not found or not a directory: %v", inputFolder, err))
			}
		}

		// Execute ost run remotely using the full path /sdk/ost
		// We pass the same -f flag if it was provided, or default to ostrich.yaml
		remoteFlags := ""
		if len(flags) > 0 {
			remoteFlags = strings.Join(flags, " ") + " "
		}
		remoteCmd := fmt.Sprintf(". /etc/profile.d/sdk.sh && cd %s && /sdk/ost %s-f %s run %s", remoteDir, remoteFlags, configBase, strings.Join(taskArgs, " "))
		slog.Debug(fmt.Sprintf("Executing remote command: %s", remoteCmd))
		return c.RunInteractive(remoteCmd)
	})
}

func getYqValue(file, query string) string {
	cmd := exec.Command("yq", "-r", query, file)
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}
