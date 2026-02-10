export PATH=/python-sdk/bin:/sdk:$PATH

export LANGUAGE=en_US.UTF-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

[[ $- == *i* ]] && {
echo '                              _              
     ____   ___  _____  ___  |_| ___  __   _  
    / __ \ / __||_   _||   ) | |/ __||  |_| | 
    |(oO)| \__ \  | |  |   \ | |\__ \)   _  | 
    \_\/_/ |___/  |_|  |_|\_\|_||___/|__| |_|_  _
      ||                            ___   __| || | __
      ||                           / __| / _` || |/ /
                                   \__ \| (_| ||   < 
                                   |___/ \__,_||_|\_\
'
}

export IDENT=$(cat /sdk/id/ident)

# Auto-configure kubectl for in-cluster use if in Kubernetes and no config exists
if [ -f /var/run/secrets/kubernetes.io/serviceaccount/token ] && [ ! -f "$HOME/.kube/config" ]; then
    if command -v kubectl >/dev/null 2>&1; then
        K8S_SERVER="https://${KUBERNETES_SERVICE_HOST:-kubernetes.default.svc}:${KUBERNETES_SERVICE_PORT:-443}"
        K8S_NS=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace 2>/dev/null || echo "default")
        
        mkdir -p "$HOME/.kube"
        cat <<EOF > "$HOME/.kube/config"
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    server: $K8S_SERVER
  name: in-cluster
contexts:
- context:
    cluster: in-cluster
    namespace: $K8S_NS
    user: service-account
  name: in-cluster
current-context: in-cluster
users:
- name: service-account
  user:
    tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
EOF
        chmod 600 "$HOME/.kube/config"
    fi
fi