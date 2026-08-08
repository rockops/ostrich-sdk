package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"golang.org/x/term"
)

type CustomHandler struct {
	level slog.Leveler
	w     io.Writer
}

func (h *CustomHandler) Enabled(_ context.Context, level slog.Level) bool {
	return level >= h.level.Level()
}

func (h *CustomHandler) Handle(_ context.Context, r slog.Record) error {
	level := r.Level.String()
	fmt.Fprintf(h.w, "%s[ostd] - %s\n", level, r.Message)
	return nil
}

func (h *CustomHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return h
}

func (h *CustomHandler) WithGroup(name string) slog.Handler {
	return h
}

var (
	DefaultImage = "ghcr.io/rockops/ostrich-sdk"
	DefaultTag   = "latest"
)

func usage() {
	fmt.Println("Usage: ostd [options] [command]")
	fmt.Println()
	fmt.Println("Options:")
	fmt.Printf("  --image <image>  The Docker image to use (default: %s)\n", DefaultImage)
	fmt.Printf("  --tag <tag>      The Docker tag to use (default: %s)\n", DefaultTag)
	fmt.Println("  -e <variable=value> Set an environment variable")
	fmt.Println("  -d               Enable debug logging")
	fmt.Println("  -h, --help       Show this help")
	fmt.Println()
	fmt.Println("Commands:")
	fmt.Println("  sh                                Open a shell in the container")
	fmt.Println("  image <image[:tag]>               Set default image (e.g. ostd image ghcr.io/rockops/ostrich-sdk:0.2.1)")
	fmt.Println("  image show                        Print the Docker image that will be used")
	fmt.Println("  image --rm                        Remove the custom image setting")
	fmt.Println("  <ost command>                     Any valid ost command")
}

func toUnixPath(path string) string {
	if runtime.GOOS != "windows" {
		return path
	}
	// Normalize path
	abspath, err := filepath.Abs(path)
	if err != nil {
		abspath = path
	}
	// C:\Path -> /c/path
	vol := filepath.VolumeName(abspath)
	if vol == "" {
		return filepath.ToSlash(abspath)
	}
	drive := strings.ToLower(string(vol[0]))
	rest := abspath[len(vol):]
	return "/" + drive + filepath.ToSlash(rest)
}

type mapping struct {
	host      string
	container string
}

func addMapping(mappings *[]mapping, host, container string) {
	*mappings = append(*mappings, mapping{host: host, container: container})
}

func mountVolume(dockerRunArgs *[]string, mappings *[]mapping, host, container string, options ...string) {
	val := fmt.Sprintf("%s:%s", host, container)
	if len(options) > 0 {
		val += ":" + strings.Join(options, ",")
	}
	*dockerRunArgs = append(*dockerRunArgs, "-v", val)
	addMapping(mappings, host, container)
}

func main() {
	home, _ := os.UserHomeDir()
	var err error
	imageFile := filepath.Join(home, ".ostrich", "image")

	if data, err := os.ReadFile(imageFile); err == nil {
		if val := strings.TrimSpace(string(data)); val != "" {
			DefaultImage = val
		}
	}

	image := DefaultImage
	tag := DefaultTag
	var envVars []string
	var ostArgs []string
	debug := false
	showImage := false
	showHelp := false

	// First pass to detect debug and help
	tempArgs := os.Args[1:]
	if len(tempArgs) == 0 {
		showHelp = true
	}
	for _, arg := range tempArgs {
		if arg == "-d" || arg == "--debug" {
			debug = true
		}
		if arg == "-h" || arg == "--help" || arg == "help" {
			showHelp = true
		}
	}

	level := slog.LevelInfo
	if debug {
		level = slog.LevelDebug
	}
	handler := &CustomHandler{
		level: level,
		w:     os.Stderr,
	}
	logger := slog.New(handler)
	slog.SetDefault(logger)

	args := os.Args[1:]
	for i := 0; i < len(args); i++ {
		arg := args[i]
		switch arg {
		case "-d", "--debug":
			// already handled
		case "--image":
			if i+1 < len(args) {
				val := args[i+1]
				if val == "show" {
					showImage = true
				} else {
					image = val
				}
				i++
			} else {
				slog.Error("Argument for --image is missing")
				usage()
				os.Exit(1)
			}
		case "--tag":
			if i+1 < len(args) {
				tag = args[i+1]
				i++
			} else {
				slog.Error("Argument for --tag is missing")
				usage()
				os.Exit(1)
			}
		case "-e":
			if i+1 < len(args) {
				envVars = append(envVars, "-e", args[i+1])
				i++
			} else {
				slog.Error("Argument for -e is missing")
				usage()
				os.Exit(1)
			}
		case "-h", "--help":
			showHelp = true
		default:
			if arg == "help" {
				showHelp = true
			}
			ostArgs = append(ostArgs, arg)
		}
	}

	// Image and Tag logic
	if strings.Contains(image, ":") {
		if tag != "latest" {
			image = strings.SplitN(image, ":", 2)[0] + ":" + tag
		}
	} else {
		image = image + ":" + tag
	}
	slog.Debug(fmt.Sprintf("Final docker image: %s", image))

	if showImage {
		fmt.Println(image)
		os.Exit(0)
	}

	var mappings []mapping

	pwd, _ := os.Getwd()
	unixPwd := toUnixPath(pwd)

	entrypoint := "/sdk/ost"
	workdir := unixPwd

	addMapping(&mappings, pwd, unixPwd)

	// Handle Windows-style output paths for -o option
	if runtime.GOOS == "windows" {
		for i := 0; i < len(ostArgs); i++ {
			if ostArgs[i] == "-o" && i+1 < len(ostArgs) {
				outputPath := ostArgs[i+1]
				// Check if it's a Windows-style path (contains drive letter or backslashes)
				if filepath.VolumeName(outputPath) != "" || strings.Contains(outputPath, "\\") {
					absPath, err := filepath.Abs(outputPath)
					if err == nil {
						wslPath := toUnixPath(absPath)
						addMapping(&mappings, absPath, wslPath)
						ostArgs[i+1] = wslPath
						slog.Debug(fmt.Sprintf("Windows output path detected: %s -> %s (mounted)", outputPath, wslPath))
					}
				}
			}
		}
	}

	slog.Debug(fmt.Sprintf("Paths initialized: pwd=%s, unixPwd=%s", pwd, unixPwd))

	if len(ostArgs) > 0 && ostArgs[0] == "image" {
		if len(ostArgs) < 2 {
			slog.Error("Argument for image command is missing")
			usage()
			os.Exit(1)
		}
		newImage := ostArgs[1]
		if newImage == "show" {
			fmt.Println(image)
			os.Exit(0)
		}
		if newImage == "--rm" {
			err := os.Remove(imageFile)
			if err != nil && !os.IsNotExist(err) {
				slog.Error(fmt.Sprintf("Error removing image config: %v", err))
				os.Exit(1)
			}
			slog.Info(fmt.Sprintf("Custom image config removed. Reverting to default: %s:%s", DefaultImage, DefaultTag))
			os.Exit(0)
		}
		err := os.MkdirAll(filepath.Dir(imageFile), 0755)
		if err != nil {
			slog.Error(fmt.Sprintf("Error creating config directory: %v", err))
			os.Exit(1)
		}
		err = os.WriteFile(imageFile, []byte(newImage), 0644)
		if err != nil {
			slog.Error(fmt.Sprintf("Error saving image: %v", err))
			os.Exit(1)
		}
		slog.Info(fmt.Sprintf("Default image updated to: %s", newImage))
		os.Exit(0)
	}

	if showHelp {
		usage()
		fmt.Println()
		fmt.Println("--------------------------------------------------------------------------------")
		fmt.Println("ostd executes any ost command inside a Docker container.")
		fmt.Println("The underlying ost engine operations are listed below:")
		fmt.Println("--------------------------------------------------------------------------------")
		fmt.Println()
		if len(ostArgs) == 0 {
			ostArgs = []string{"help"}
		} else {
			hasHelp := false
			for _, a := range ostArgs {
				if a == "help" || a == "-h" || a == "--help" {
					hasHelp = true
					break
				}
			}
			if !hasHelp {
				ostArgs = append(ostArgs, "help")
			}
		}
	}

	if len(ostArgs) > 0 && ostArgs[0] == "sh" {
		entrypoint = "bash"
		ostArgs = ostArgs[1:]
		workdir = "/sdk"
		mappings = nil
	}
	ostrichDockerDir := filepath.Join(home, ".ostrich", "docker")

	// Ensure directory exists
	os.MkdirAll(ostrichDockerDir, 0755)
	folders := []string{"config", "helm", "sdk-config", "cache"}
	for _, f := range folders {
		os.MkdirAll(filepath.Join(ostrichDockerDir, f), 0755)
	}

	// TTY & Stdin Pipe detection
	var interactive []string
	if term.IsTerminal(int(os.Stdin.Fd())) {
		if term.IsTerminal(int(os.Stdout.Fd())) {
			interactive = []string{"-it"}
		}
	} else if fi, err := os.Stdin.Stat(); err == nil {
		if (fi.Mode()&os.ModeNamedPipe) != 0 || fi.Mode().IsRegular() {
			interactive = []string{"-i"}
		}
	}

	unixHome := toUnixPath(home)


	dockerRunArgs := []string{"run", "--rm"}
	dockerRunArgs = append(dockerRunArgs, interactive...)
	addMapping(&mappings, "/var/run/docker.sock", "/var/run/docker.sock")

	for _, m := range mappings {
		dockerRunArgs = append(dockerRunArgs, "-v", fmt.Sprintf("%s:%s", m.host, m.container))
	}

	dockerRunArgs = append(dockerRunArgs, envVars...)
	dockerRunArgs = append(dockerRunArgs, "-w", workdir)

	mountVolume(&dockerRunArgs, &mappings, filepath.Join(home, ".kube", "config"), "/kubeconfig")
	mountVolume(&dockerRunArgs, &mappings, filepath.Join(ostrichDockerDir, "config"), "/home/sdk/.config")
	mountVolume(&dockerRunArgs, &mappings, filepath.Join(ostrichDockerDir, "cache"), "/home/sdk/.cache")
	mountVolume(&dockerRunArgs, &mappings, ostrichDockerDir, "/home/sdk/.ostrich")
	mountVolume(&dockerRunArgs, &mappings, os.TempDir(), os.TempDir())


	dockerRunArgs = append(dockerRunArgs,
		"-e", "KUBECONFIG=/kubeconfig",
		"-e", "HOME=/home/sdk",
		"-e", "XDG_CONFIG_HOME=/home/sdk/.config",
		"-e", "XDG_CACHE_HOME=/home/sdk/.cache",
		"-e", "OST_WORKSPACE="+unixPwd,
		"-e", "OST_HOME_HOST_PATH="+unixHome,
	)




	// Pass docker config if it exists
	dockerConfig := filepath.Join(home, ".docker", "config.json")
	if _, err := os.Stat(dockerConfig); err == nil {
		mountVolume(&dockerRunArgs, &mappings, dockerConfig, "/home/sdk/.docker/config.json", "ro")
	}


	// Mount SSL certificates for certificate verification
	if _, err := os.Stat("/etc/ssl/certs"); err == nil {
		mountVolume(&dockerRunArgs, &mappings, "/etc/ssl/certs", "/etc/ssl/certs", "ro")
	}

	// Write volumes.yaml
	volumesFile := filepath.Join(ostrichDockerDir, "volumes.yaml")
	var b strings.Builder
	for _, m := range mappings {
		fmt.Fprintf(&b, "- host: %q\n  container: %q\n", m.host, m.container)
	}
	err = os.WriteFile(volumesFile, []byte(b.String()), 0644)
	if err != nil {
		slog.Error(fmt.Sprintf("Error writing volumes.yaml: %v", err))
	} else {
		dockerRunArgs = append(dockerRunArgs, "-v", fmt.Sprintf("%s:/ostrich-volumes.yaml", volumesFile))
	}

	// Linux specific UID/GID
	if runtime.GOOS == "linux" {
		uid := os.Getuid()
		gid := os.Getgid()
		dockerRunArgs = append(dockerRunArgs, "-u", fmt.Sprintf("%d:%d", uid, gid))

		// Try to get docker group id
		cmd := exec.Command("getent", "group", "docker")
		out, err := cmd.Output()
		if err == nil {
			parts := strings.Split(strings.TrimSpace(string(out)), ":")
			if len(parts) >= 3 {
				dockerRunArgs = append(dockerRunArgs, "--group-add", parts[2])
			}
		}
	}

	dockerRunArgs = append(dockerRunArgs, "--network", "host")
	dockerRunArgs = append(dockerRunArgs, "--entrypoint", entrypoint)
	dockerRunArgs = append(dockerRunArgs, image)

	if debug && entrypoint == "/sdk/ost" {
		dockerRunArgs = append(dockerRunArgs, "-d")
	}

	dockerRunArgs = append(dockerRunArgs, ostArgs...)

	slog.Debug(fmt.Sprintf("Docker command prepared: docker %s", strings.Join(dockerRunArgs, " ")))

	runCmd := exec.Command("docker", dockerRunArgs...)
	runCmd.Stdin = os.Stdin
	runCmd.Stdout = os.Stdout
	runCmd.Stderr = os.Stderr

	err = runCmd.Run()
	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			os.Exit(exitErr.ExitCode())
		}
		slog.Error(fmt.Sprintf("Error running docker: %v", err))
		os.Exit(1)
	}
}
