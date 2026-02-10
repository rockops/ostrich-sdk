package main

import (
	"fmt"
	"log/slog"
	"os"
	"strings"
)

var VERSION = "0.0.0-dev-go"

func main() {
	if len(os.Args) < 2 {
		help()
		return
	}

	verbs := map[string]bool{
		"init": true, "endpoint": true, "ep": true, "ssh": true,
		"put": true, "docker": true, "kubectl": true, "version": true,
		"run": true, "help": true,
	}

	var command string
	var args []string
	var foundVerb bool
	var debug bool

	for i := 1; i < len(os.Args); i++ {
		arg := os.Args[i]
		if arg == "-d" || arg == "--debug" {
			debug = true
		}
		if !foundVerb {
			if verbs[arg] {
				command = arg
				foundVerb = true
				continue
			}
			if !strings.HasPrefix(arg, "-") {
				// First non-flag that is not a known verb is our command (remote command)
				command = arg
				foundVerb = true
				continue
			}
		}
		args = append(args, arg)
	}

	initLogger(debug)

	if command == "" && len(os.Args) > 1 {
		// Only flags were provided, show help
		help()
		return
	}

	switch command {
	case "init":
		cmdInit()
	case "endpoint", "ep":
		cmdEndpoint(args)
	case "ssh":
		runOnRemote(func(c *SSHClient) error {
			return c.Shell()
		})
	case "put":
		runOnRemote(func(c *SSHClient) error {
			return c.DoSync()
		})
	case "docker":
		runOnRemote(func(c *SSHClient) error {
			return c.RunInteractive(". /etc/profile.d/sdk.sh && docker " + strings.Join(args, " "))
		})
	case "kubectl":
		runOnRemote(func(c *SSHClient) error {
			return c.RunInteractive(". /etc/profile.d/sdk.sh && kubectl " + strings.Join(args, " "))
		})
	case "version":
		slog.Info(fmt.Sprintf("ostr %s (Go version)", VERSION))
		runOnRemote(func(c *SSHClient) error {
			slog.Debug("Requesting remote version")
			return c.Run(". /etc/profile.d/sdk.sh && ost --version")
		})
	case "run":
		cmdRun(args)
	case "help", "-h", "--help":
		help()
	default:
		// Try to run as a remote command if not a built-in
		runOnRemote(func(c *SSHClient) error {
			return c.RunInteractive(". /etc/profile.d/sdk.sh && ost " + strings.Join(append([]string{command}, args...), " "))
		})
	}
}

func runOnRemote(fn func(*SSHClient) error) {
	curr, err := getCurrentEndpoint()
	if err != nil {
		slog.Error("No endpoint selected. Run 'ostr init'")
		os.Exit(1)
	}

	conf, err := readConfig(curr)
	if err != nil {
		slog.Error(fmt.Sprintf("Error reading config: %v", err))
		os.Exit(1)
	}

	client, err := newSSHClient(conf)
	if err != nil {
		slog.Error(fmt.Sprintf("Error connecting to SDK: %v", err))
		os.Exit(1)
	}
	defer client.Close()

	if err := fn(client); err != nil {
		slog.Error(fmt.Sprintf("Error: %v", err))
		os.Exit(1)
	}
}

func help() {
	slog.Info("Ostrich SDK remote commands (Go version):")
	fmt.Println()
	fmt.Println("Usage: ostr <command> [arguments]")
	fmt.Println()
	fmt.Println("Standard commands:")
	fmt.Println("  init        : setup connection")
	fmt.Println("  endpoint|ep : manage endpoints")
	fmt.Println("  ssh         : open shell")
	fmt.Println("  put         : upload files")
	fmt.Println("  docker      : run docker command")
	fmt.Println("  kubectl     : run kubectl command")
	fmt.Println("  run [-f config] <task>  : sync input folder and run task remotely")
	fmt.Println("  version                 : show version")
}
