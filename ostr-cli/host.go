package main

import (
	"fmt"
	"log/slog"
	"os"
)

func cmdHost(args []string) {
	if len(args) < 2 {
		fmt.Println("Usage: ostr host <hostname> <ip_address>")
		os.Exit(1)
	}

	hostname := args[0]
	ip := args[1]

	runOnRemote(func(c *SSHClient) error {
		// Script to update $HOME/.hosts and rebuild /etc/hosts
		script := fmt.Sprintf(`
HOSTNAME='%s'
IP='%s'
HOSTS_FILE=$HOME/.hosts
touch "$HOSTS_FILE"

# Update or add the entry in $HOME/.hosts
# We use awk to handle the fields correctly
TMP_FILE=$(mktemp)
awk -v h="$HOSTNAME" -v ip="$IP" 'BEGIN { found=0 } { if ($2 == h) { print ip " " h; found=1 } else { print $0 } } END { if (!found) print ip " " h }' "$HOSTS_FILE" > "$TMP_FILE"
mv "$TMP_FILE" "$HOSTS_FILE"

# Rebuild /etc/hosts
if [ ! -f /etc/hosts.sdk.bak ]; then
    sudo cp /etc/hosts /etc/hosts.sdk.bak
fi

sudo cp /etc/hosts.sdk.bak /etc/hosts
for hf in /home/*/.hosts; do
    if [ -f "$hf" ]; then
        cat "$hf" | sudo tee -a /etc/hosts > /dev/null
    fi
done
`, hostname, ip)

		slog.Info(fmt.Sprintf("Adding host entry: %s -> %s", hostname, ip))
		if err := c.Run(script); err != nil {
			return fmt.Errorf("failed to add host entry: %v", err)
		}

		slog.Info("Host entry added successfully.")
		return nil
	})
}
