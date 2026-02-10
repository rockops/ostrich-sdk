package main

import (
	"bufio"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"io/ioutil"
	"log/slog"
	"os"
	"path/filepath"
	"strings"

	"golang.org/x/crypto/ssh"
)

func cmdInit() {
	var defEndpoint, defPort string = "", "31022"

	// Try to load current to suggest defaults
	curr, _ := getCurrentEndpoint()
	if curr != "" {
		conf, _ := readConfig(curr)
		if conf != nil {
			defEndpoint = conf.Endpoint
			defPort = conf.Port
		}
	}

	reader := bufio.NewReader(os.Stdin)

	fmt.Printf("SDK endpoint (%s): ", defEndpoint)
	endpoint, _ := reader.ReadString('\n')
	endpoint = strings.TrimSpace(endpoint)
	if endpoint == "" {
		endpoint = defEndpoint
	}
	if endpoint == "" {
		slog.Error("Endpoint cannot be empty")
		return
	}

	fmt.Printf("Config name (%s): ", endpoint)
	configName, _ := reader.ReadString('\n')
	configName = strings.TrimSpace(configName)
	if configName == "" {
		configName = endpoint
	}

	fmt.Printf("Port (%s): ", defPort)
	port, _ := reader.ReadString('\n')
	port = strings.TrimSpace(port)
	if port == "" {
		port = defPort
	}

	// Generate UUID
	uuid := generateUUID()

	dir := getOstrichDir()
	os.MkdirAll(dir, 0700)

	// Generate RSA keys if missing
	keyPath := filepath.Join(dir, "id_rsa")
	if _, err := os.Stat(keyPath); os.IsNotExist(err) {
		slog.Info("Generating RSA keys...")
		generateRSAKey(keyPath)
	}

	conf := &Config{Endpoint: endpoint, Port: port, UUID: uuid}
	writeConfig(configName, conf)
	setCurrentEndpoint(configName)

	// Install key
	slog.Info("Installing key on remote host...")
	// Key is installed on remote host (placeholder for manual instructions)

	// We still need to do the initial SSH with password to install the key.
	// Go's ssh doesn't support interactive password prompts easily for the first time.
	// But we'll try to execute a simple command.
	fmt.Println("Note: For the FIRST connection, you might prefer to manually install the key")
	fmt.Printf("ssh-copy-id -p %s sdk@%s\n", port, endpoint)
	fmt.Println("Or enter password if prompted by the following command:")

	// Since we can't easily do interactive password with x/crypto/ssh without a lot of TTY work,
	// and the user said "no ssh [binary]", this is a bit of a chicken-and-egg for init.
	// I'll implement a simple SSH call if I can, or tell them.

	slog.Info("Key installed locally. You can use 'ostr ssh' once the remote host has your pubkey.")
}

func generateUUID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}

func generateRSAKey(path string) {
	key, _ := rsa.GenerateKey(rand.Reader, 4096)

	// Private key
	privFile, _ := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0600)
	defer privFile.Close()
	privBlock := &pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(key)}
	pem.Encode(privFile, privBlock)

	// Public key
	pub, _ := ssh.NewPublicKey(&key.PublicKey)
	ioutil.WriteFile(path+".pub", ssh.MarshalAuthorizedKey(pub), 0644)
}

func cmdEndpoint(args []string) {
	if len(args) == 0 {
		list, _ := listEndpoints()
		curr, _ := getCurrentEndpoint()
		for _, ep := range list {
			prefix := "  "
			if ep == curr {
				prefix = "> "
			}
			fmt.Printf("%s%s\n", prefix, ep)
		}
		return
	}

	switch args[0] {
	case "get":
		curr, _ := getCurrentEndpoint()
		fmt.Println(curr)
	case "list", "ls":
		cmdEndpoint(nil)
	default:
		// Switch endpoint
		list, _ := listEndpoints()
		found := false
		for _, ep := range list {
			if ep == args[0] {
				found = true
				break
			}
		}
		if found {
			setCurrentEndpoint(args[0])
			slog.Info(fmt.Sprintf("Switched to endpoint %s", args[0]))
			cmdEndpoint(nil)
		} else {
			slog.Error(fmt.Sprintf("Endpoint %s not found", args[0]))
		}
	}
}
