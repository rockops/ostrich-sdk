package main

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
)

func cmdCert(args []string) {
	if len(args) < 2 || args[0] != "install" {
		fmt.Println("Usage: ostr cert install <file>")
		os.Exit(1)
	}

	certFile := args[1]
	if _, err := os.Stat(certFile); os.IsNotExist(err) {
		slog.Error(fmt.Sprintf("Certificate file not found: %s", certFile))
		os.Exit(1)
	}

	runOnRemote(func(c *SSHClient) error {
		fileName := filepath.Base(certFile)
		remoteCertsDir := "/home/sdk/.certs"
		remotePath := pathJoin(remoteCertsDir, fileName)

		slog.Info(fmt.Sprintf("Uploading certificate %s to %s...", fileName, remoteCertsDir))

		// Ensure remote certs dir exists and is writable
		if err := c.Run(fmt.Sprintf("sudo mkdir -p %s && sudo chown $(id -un) %s", remoteCertsDir, remoteCertsDir)); err != nil {
			return fmt.Errorf("failed to create remote directory %s: %v", remoteCertsDir, err)
		}

		// Upload file
		if err := c.PutFile(certFile, remotePath); err != nil {
			return fmt.Errorf("failed to upload certificate: %v", err)
		}

		slog.Info("Copying certificate to trusted store...")
		// Use sudo to copy to /usr/local/share/ca-certificates
		// We use -f to overwrite if exists
		installCmd := fmt.Sprintf("sudo cp %s /usr/local/share/ca-certificates/%s", remotePath, fileName)
		if err := c.Run(installCmd); err != nil {
			return fmt.Errorf("failed to copy certificate to trusted store: %v", err)
		}

		slog.Info("Updating CA certificates...")
		if err := c.Run("sudo update-ca-certificates"); err != nil {
			return fmt.Errorf("failed to update CA certificates: %v", err)
		}

		slog.Info("Certificate installed successfully.")
		return nil
	})
}
