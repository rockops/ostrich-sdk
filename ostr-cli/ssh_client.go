package main

import (
	"fmt"
	"io/ioutil"
	"net"

	"os"
	"path/filepath"

	"golang.org/x/crypto/ssh"
	"golang.org/x/term"
)

type SSHClient struct {
	client *ssh.Client
	config *Config
}

func getPrivateKey() (ssh.Signer, error) {
	home, _ := os.UserHomeDir()
	keyPath := filepath.Join(home, ".ostrich", "id_rsa")
	key, err := ioutil.ReadFile(keyPath)
	if err != nil {
		return nil, fmt.Errorf("unable to read private key: %v", err)
	}
	return ssh.ParsePrivateKey(key)
}

func newSSHClient(conf *Config) (*SSHClient, error) {
	signer, err := getPrivateKey()
	if err != nil {
		return nil, err
	}

	sshConfig := &ssh.ClientConfig{
		User: "sdk",
		Auth: []ssh.AuthMethod{
			ssh.PublicKeys(signer),
		},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(), // Simplification for dev env
	}

	addr := net.JoinHostPort(conf.Endpoint, conf.Port)
	client, err := ssh.Dial("tcp", addr, sshConfig)
	if err != nil {
		return nil, err
	}

	return &SSHClient{client: client, config: conf}, nil
}

func (c *SSHClient) Run(cmd string) error {
	session, err := c.client.NewSession()
	if err != nil {
		return err
	}
	defer session.Close()

	session.Stdout = os.Stdout
	session.Stderr = os.Stderr
	session.Stdin = os.Stdin

	return session.Run(cmd)
}

func (c *SSHClient) RunInteractive(cmd string) error {
	if !term.IsTerminal(int(os.Stdin.Fd())) {
		return c.Run(cmd)
	}

	session, err := c.client.NewSession()
	if err != nil {
		return err
	}
	defer session.Close()

	fd := int(os.Stdin.Fd())
	state, err := term.MakeRaw(fd)
	if err != nil {
		return err
	}
	defer term.Restore(fd, state)

	w, h, err := term.GetSize(fd)
	if err != nil {
		return err
	}

	modes := ssh.TerminalModes{
		ssh.ECHO:          1,
		ssh.TTY_OP_ISPEED: 14400,
		ssh.TTY_OP_OSPEED: 14400,
	}

	if err := session.RequestPty("xterm-256color", h, w, modes); err != nil {
		return err
	}

	session.Stdout = os.Stdout
	session.Stderr = os.Stderr
	session.Stdin = os.Stdin

	return session.Run(cmd)
}

func (c *SSHClient) Shell() error {
	session, err := c.client.NewSession()
	if err != nil {
		return err
	}
	defer session.Close()

	fd := int(os.Stdin.Fd())
	state, err := term.MakeRaw(fd)
	if err != nil {
		return err
	}
	defer term.Restore(fd, state)

	w, h, err := term.GetSize(fd)
	if err != nil {
		return err
	}

	modes := ssh.TerminalModes{
		ssh.ECHO:          1,
		ssh.TTY_OP_ISPEED: 14400,
		ssh.TTY_OP_OSPEED: 14400,
	}

	if err := session.RequestPty("xterm-256color", h, w, modes); err != nil {
		return err
	}

	session.Stdout = os.Stdout
	session.Stderr = os.Stderr
	session.Stdin = os.Stdin

	if err := session.Shell(); err != nil {
		return err
	}

	return session.Wait()
}

func (c *SSHClient) Close() error {
	return c.client.Close()
}
