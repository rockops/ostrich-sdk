# ostd.ps1
# Wrapper script to execute ost from a Docker image on Windows (PowerShell)
# Use:
#   .\ostd.ps1 => same arguments as ost

$IMAGE = "ghcr.io/rockops/docker/ostrich-sdk"
$TAG = "latest"

function Show-Usage {
    Write-Host "Usage: .\ostd.ps1 [options] [command]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  --image <image>  The Docker image to use (default: $IMAGE)"
    Write-Host "  --tag <tag>      The Docker tag to use (default: $TAG)"
    Write-Host "  -h, --help       Show this help"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  sh               Open a shell in the container"
    Write-Host "  <ost command>    Any valid ost command"
}

$remainingArgs = @()
$envVars = @()
$i = 0
while ($i -lt $args.Length) {
    switch ($args[$i]) {
        "--image" {
            $IMAGE = $args[++$i]
        }
        "--tag" {
            $TAG = $args[++$i]
        }
        "-e" {
            $envVars += "-e"
            $envVars += $args[++$i]
        }
        "-h" { Show-Usage; exit 0 }
        "--help" { Show-Usage; exit 0 }
        default {
            $remainingArgs += $args[$i]
        }
    }
    $i++
}

# Handle image and tag override
if ($IMAGE -like "*:*") {
    if ($TAG -ne "latest") {
        $IMAGE = "$($IMAGE.Split(':')[0]):$TAG"
    }
}
else {
    $IMAGE = "$($IMAGE):$TAG"
}

$entrypoint = "/sdk/ost"
$workdir = "/" + $PWD.Path.Replace('\', '/').Replace(':', '')
$workdir = $workdir.ToLower()
$dataVolume = @("-v", "$($PWD.Path):$($workdir)")

if ($remainingArgs.Count -gt 0 -and $remainingArgs[0] -eq "sh") {
    $entrypoint = "bash"
    $workdir = "/sdk"
    $dataVolume = $null
    $remainingArgs = $remainingArgs | Select-Object -Skip 1
}

# Initialize local folders (PowerShell style)
$ostrichRoot = Join-Path $HOME ".ostrich"
$dockerRoot = Join-Path $ostrichRoot "docker"
$folders = "templates", "test-templates", "config", "helm", "sdk-config"

foreach ($f in $folders) {
    $path = Join-Path $dockerRoot $f
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

# Refresh test-templates and templates from image
$testTemplatesPath = Join-Path $dockerRoot "test-templates"
Remove-Item -Path $testTemplatesPath -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $testTemplatesPath -Force | Out-Null

Write-Host ">> Initializing test-templates and templates from image $IMAGE..."
# PowerShell handles binary redirection poorly (stdout corruption).
# We use a helper container to perform the extraction safely.
$dockerRootUnix = $dockerRoot.Replace('\', '/').Replace(':', '')
if ($dockerRootUnix -notmatch "^/") { $dockerRootUnix = "/" + $dockerRootUnix }
$dockerRootUnix = $dockerRootUnix.ToLower()

docker run --rm --entrypoint=tar $IMAGE -C /sdk -cf - test-templates templates | docker run --rm -i -v "${dockerRoot}:/out" busybox tar -C /out -xf -

# TTY Detection
$interactive = @()
if (-not [Console]::IsInputRedirected) {
    if (-not [Console]::IsOutputRedirected) {
        $interactive = @("-it")
    }
    else {
        $interactive = @("-i")
    }
}

$topDir = Split-Path $PSCommandPath
# Normalize paths for the Linux container (use forward slashes for translation logic)
$topDirUnix = $topDir.Replace('\', '/')
$homeUnix = $HOME.Replace('\', '/')
$dockerRootUnix = $dockerRoot.Replace('\', '/')

$dockerArgs = @("run", "--rm")
if ($interactive) { $dockerArgs += $interactive }

$dockerArgs += @("-v", "/var/run/docker.sock:/var/run/docker.sock")

if ($dataVolume) { $dockerArgs += $dataVolume }

if ($envVars) { $dockerArgs += $envVars }

$dockerArgs += @(
    "-w", $workdir,
    "-v", "$HOME/.kube/config:/kubeconfig",
    "-e", "KUBECONFIG=/kubeconfig",
    "-e", "HOME=/sdk",
    "-e", "OST_WORKSPACE=$workdir",
    "-e", "OST_SDK_HOST_PATH=$topDirUnix",
    "-e", "OST_HOME_HOST_PATH=$homeUnix",
    "-v", "${dockerRootUnix}/templates:/sdk/.ostrich/templates",
    "-v", "${dockerRootUnix}/test-templates:/sdk/test-templates",
    "-v", "${dockerRootUnix}/config:/sdk/.ostrich/config",
    "-v", "${dockerRootUnix}/helm:/sdk/.ostrich/helm",
    "-v", "${dockerRootUnix}/sdk-config:/sdk/.ostrich/sdk-config",
    "--network", "host",
    "--entrypoint", $entrypoint,
    $IMAGE
)

if ($remainingArgs) { $dockerArgs += $remainingArgs }

# Execute docker
& docker $dockerArgs
