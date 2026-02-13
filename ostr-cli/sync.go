package main

import (
	"archive/tar"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
)

func (c *SSHClient) Sync(localDir, remoteDir string) error {
	slog.Debug(fmt.Sprintf("Syncing %s to %s", localDir, remoteDir))
	session, err := c.client.NewSession()
	if err != nil {
		return err
	}
	defer session.Close()

	// Ensure remote directory exists
	if err := c.Run(fmt.Sprintf("mkdir -p %s", remoteDir)); err != nil {
		return err
	}

	stdin, err := session.StdinPipe()
	if err != nil {
		return err
	}

	// We'll use tar over SSH for syncing. This is portable and efficient.
	// It avoids the need for a separate SFTP library or the rsync binary.
	// This implements a one-way sync (local to remote) and doesn't delete
	// remote files that are not present locally, as requested.
	go func() {
		defer stdin.Close()
		tw := tar.NewWriter(stdin)
		defer tw.Close()

		filepath.Walk(localDir, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}

			// Get relative path
			rel, err := filepath.Rel(localDir, path)
			if err != nil {
				return err
			}
			if rel == "." {
				return nil
			}

			// Exclude .git and common patterns
			if strings.HasPrefix(rel, ".git") || strings.Contains(rel, "__pycache__") || strings.Contains(rel, ".idea") || strings.Contains(rel, ".vscode") {
				if info.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}

			header, err := tar.FileInfoHeader(info, "")
			if err != nil {
				return err
			}
			header.Name = rel

			if err := tw.WriteHeader(header); err != nil {
				return err
			}

			if !info.IsDir() {
				f, err := os.Open(path)
				if err != nil {
					return err
				}
				defer f.Close()
				_, err = io.Copy(tw, f)
				return err
			}
			return nil
		})
	}()

	return session.Run(fmt.Sprintf("tar -C %s -xf -", remoteDir))
}

func (c *SSHClient) PutFile(localPath, remotePath string) error {
	session, err := c.client.NewSession()
	if err != nil {
		return err
	}
	defer session.Close()

	stdin, err := session.StdinPipe()

	if err != nil {
		return err
	}

	go func() {
		defer stdin.Close()
		f, _ := os.Open(localPath)
		defer f.Close()
		io.Copy(stdin, f)
	}()

	return session.Run(fmt.Sprintf("cat > %s", remotePath))
}

func (c *SSHClient) getRemoteValue(cmd string) string {
	session, err := c.client.NewSession()
	if err != nil {
		return ""
	}
	defer session.Close()

	out, err := session.Output(cmd)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func (c *SSHClient) DoSync() (string, error) {
	return c.DoSyncFile("ostrich.yaml")
}

func (c *SSHClient) DoSyncFile(configFile string) (string, error) {
	slog.Info(fmt.Sprintf("Syncing sources from %s", configFile))

	configData, err := loadYaml(configFile)
	if err != nil {
		return "", fmt.Errorf("error loading %s: %v", configFile, err)
	}

	// Get plugin name from config
	pluginName := getYamlPathValue(configData, "plugin.name")
	if pluginName == "" {
		pluginName = "unknown"
	}

	remoteDir := pathJoin(c.config.UUID, pluginName)
	configDir := filepath.Dir(configFile)

	// Ensure remote directory exists
	if err := c.Run(fmt.Sprintf("mkdir -p %s", remoteDir)); err != nil {
		return "", err
	}

	// Sync config file itself
	remoteConfigPath := pathJoin(remoteDir, filepath.Base(configFile))
	if err := c.PutFile(configFile, remoteConfigPath); err != nil {
		return "", fmt.Errorf("error syncing config file: %v", err)
	}

	// Determine what to sync - Fetch merged values from remote
	slog.Info("Fetching merged values from remote to identify input folders...")
	remoteValuesCmd := fmt.Sprintf(". /etc/profile.d/sdk.sh && cd %s && ost -f %s template values", remoteDir, filepath.Base(configFile))
	remoteYaml := c.getRemoteValue(remoteValuesCmd)
	if remoteYaml != "" {
		mergedConfig, err := parseYaml(remoteYaml)
		if err == nil {
			configData = mergedConfig
		} else {
			slog.Warn(fmt.Sprintf("Could not parse remote values, falling back to local config: %v", err))
		}
	} else {
		slog.Warn("Could not fetch remote values, falling back to local config")
	}

	// Determine what to sync
	srcDir := getYamlPathValue(configData, "template.params.src_dir")
	inputs := getYamlPathMap(configData, "template.params.input")

	// If src_dir is specified, sync it
	if srcDir != "" && srcDir != "null" {
		localSrcPath := filepath.Join(configDir, srcDir)
		remoteSrcPath := pathJoin(remoteDir, srcDir)
		slog.Info(fmt.Sprintf("Syncing src_dir: %s -> %s", srcDir, remoteSrcPath))
		if err := c.Sync(localSrcPath, remoteSrcPath); err != nil {
			return "", err
		}
	} else if len(inputs) == 0 {
		// Default to syncing everything if no specific folders are specified
		slog.Info(fmt.Sprintf("No specific input folders, syncing current directory: . -> %s", remoteDir))
		if err := c.Sync(configDir, remoteDir); err != nil {
			return "", err
		}
	}

	// Always sync input folders if specified
	for _, folder := range inputs {
		if folder == "" || folder == "null" {
			continue
		}
		localPath := filepath.Join(configDir, folder)
		remotePath := pathJoin(remoteDir, folder)
		slog.Info(fmt.Sprintf("Syncing input folder: %s -> %s", folder, remotePath))
		if err := c.Sync(localPath, remotePath); err != nil {
			return "", fmt.Errorf("error syncing input folder %s: %v", folder, err)
		}
	}

	return remoteDir, nil
}
