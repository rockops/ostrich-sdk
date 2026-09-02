package main

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
)

func cmdRun(args []string) {
	var configFiles []string

	// Parse flags and task args
	var flags []string
	var taskArgs []string

	for i := 0; i < len(args); i++ {
		arg := args[i]
		if arg == "-f" || arg == "--file" {
			if i+1 < len(args) {
				configFiles = append(configFiles, args[i+1])
				flags = append(flags, fmt.Sprintf("-f %s", args[i+1]))
				i++
			}
			continue
		}
		if strings.HasPrefix(arg, "--file=") {
			configFiles = append(configFiles, arg[len("--file="):])
			flags = append(flags, arg)
			continue
		}
		if arg == "--set" {
			if i+1 < len(args) {
				flags = append(flags, fmt.Sprintf("--set %s", args[i+1]))
				i++
			}
			continue
		}
		if strings.HasPrefix(arg, "--set=") {
			flags = append(flags, arg)
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

	primaryConfigFile := "ostrich.yaml"
	if len(configFiles) > 0 {
		primaryConfigFile = configFiles[0]
	}

	// Read primary config file locally to determine plugin name
	absConfigPath, err := filepath.Abs(primaryConfigFile)
	if err != nil {
		slog.Error(fmt.Sprintf("Error getting absolute path of config file %s: %v", primaryConfigFile, err))
		os.Exit(1)
	}

	if _, err := os.Stat(absConfigPath); os.IsNotExist(err) {
		slog.Error(fmt.Sprintf("Error: Config file %s not found", primaryConfigFile))
		os.Exit(1)
	}

	// Load YAML config to get plugin name
	configData, err := loadYaml(absConfigPath)
	if err != nil {
		slog.Error(fmt.Sprintf("Error parsing %s: %v", absConfigPath, err))
		os.Exit(1)
	}

	runOnRemote(func(c *SSHClient) error {
		// Sync ostrich.yaml if it exists locally
		if _, err := os.Stat("ostrich.yaml"); err == nil {
			if _, err := c.DoSyncFile("ostrich.yaml"); err != nil {
				return err
			}
		}
		// Sync all specified config files
		for _, cfg := range configFiles {
			if cfg != "ostrich.yaml" {
				if _, err := c.DoSyncFile(cfg); err != nil {
					return err
				}
			}
		}

		// Get plugin name to determine remote directory
		pluginName := getYamlPathValue(configData, "plugin.name")
		if pluginName == "" || pluginName == "null" {
			pluginName = "unknown"
		}
		remoteDir := pathJoin(c.config.UUID, pluginName)

		// Execute ost run remotely using the full path /sdk/ost
		remoteFlags := ""
		if len(flags) > 0 {
			remoteFlags = strings.Join(flags, " ") + " "
		}
		remoteCmd := fmt.Sprintf(". /etc/profile.d/sdk.sh && cd %s && /sdk/ost %srun %s", remoteDir, remoteFlags, strings.Join(taskArgs, " "))
		slog.Debug(fmt.Sprintf("Executing remote command: %s", remoteCmd))
		return c.RunInteractive(remoteCmd)
	})
}
