package main

import (
	"fmt"
	"log/slog"
	"os"
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

	// Load YAML config
	configData, err := loadYaml(absConfigPath)
	if err != nil {
		slog.Error(fmt.Sprintf("Error parsing %s: %v", absConfigPath, err))
		os.Exit(1)
	}

	runOnRemote(func(c *SSHClient) error {
		// Sync configuration and input folders
		if _, err := c.DoSyncFile(configFile); err != nil {
			return err
		}

		// Get plugin name to determine remote directory
		pluginName := getYamlPathValue(configData, "plugin.name")
		if pluginName == "" || pluginName == "null" {
			pluginName = "unknown"
		}
		remoteDir := pathJoin(c.config.UUID, pluginName)
		configBase := filepath.Base(configFile)

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
