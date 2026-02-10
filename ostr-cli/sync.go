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

			// Exclude .git and other common patterns (simplified .gitignore)
			if strings.HasPrefix(rel, ".git") || strings.Contains(rel, "__pycache__") {
				if info.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}

			header, err := tar.FileInfoHeader(info, rel)
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

func (c *SSHClient) DoSync() error {
	slog.Info("Syncing sources")

	// Get plugin name from ostrich.yaml
	pluginName := c.getRemoteValue("cat ostrich.yaml | yq -r '.plugin.name'")
	if pluginName == "" {
		pluginName = "unknown"
	}

	remoteDir := filepath.Join(c.config.UUID, pluginName)
	srcDir := c.getRemoteValue("cat ostrich.yaml | yq -r '.template.params.src_dir'")
	if srcDir == "" || srcDir == "null" {
		srcDir = "."
	}

	slog.Info(fmt.Sprintf("Local: %s -> Remote: %s", srcDir, remoteDir))
	return c.Sync(srcDir, remoteDir)
}
