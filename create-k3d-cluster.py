#!/usr/bin/env python3
"""
Create k3d cluster using Docker Python SDK (bypass Go binary threading issues)
"""
import docker
import base64
import os
import time

def create_k3d_cluster():
    client = docker.from_env()

    cluster_name = "crossplane-lab"
    api_port = 6550

    print(f"Creating k3d cluster '{cluster_name}'...")

    # Create k3d network
    try:
        network = client.networks.create(
            f"k3d-{cluster_name}",
            driver="bridge",
            labels={"app": "k3d", "cluster": cluster_name}
        )
        print(f"✓ Created network: k3d-{cluster_name}")
    except docker.errors.APIError as e:
        if "already exists" in str(e):
            print(f"ℹ Network k3d-{cluster_name} already exists")
            network = client.networks.get(f"k3d-{cluster_name}")
        else:
            raise

    # Run k3s server container
    container_name = f"k3d-{cluster_name}-server-0"

    try:
        container = client.containers.run(
            image="rancher/k3s:v1.30.4-k3s1",
            name=container_name,
            detach=True,
            privileged=True,
            network=network.name,
            ports={
                "6443/tcp": api_port,
                "80/tcp": 8080,
                "443/tcp": 8443
            },
            environment={
                "K3S_TOKEN": "crossplane-lab-token",
                "K3S_KUBECONFIG_OUTPUT": "/output/kubeconfig.yaml",
                "K3S_KUBECONFIG_MODE": "666"
            },
            command="server --disable traefik --disable servicelb --https-listen-port=6443",
            volumes={
                "/run": {"bind": "/run", "mode": "rw"},
                "/var/run": {"bind": "/var/run", "mode": "rw"}
            },
            labels={
                "app": "k3d",
                "cluster": cluster_name,
                "component": "server",
                "role": "server"
            },
            tmpfs={
                "/run": "",
                "/var/run": ""
            }
        )
        print(f"✓ Created container: {container_name}")

        # Wait for k3s to be ready
        print("Waiting for k3s to start (30 seconds)...")
        time.sleep(30)

        # Get kubeconfig
        print("Extracting kubeconfig...")
        exit_code, output = container.exec_run("cat /etc/rancher/k3s/k3s.yaml")

        if exit_code == 0:
            kubeconfig = output.decode('utf-8')
            # Replace localhost with 0.0.0.0
            kubeconfig = kubeconfig.replace("127.0.0.1:6443", f"0.0.0.0:{api_port}")
            kubeconfig = kubeconfig.replace("default", f"k3d-{cluster_name}")

            # Write kubeconfig
            kubeconfig_path = os.path.expanduser("~/.kube/config")
            os.makedirs(os.path.dirname(kubeconfig_path), exist_ok=True)

            with open(kubeconfig_path, 'w') as f:
                f.write(kubeconfig)

            print(f"✓ Kubeconfig written to {kubeconfig_path}")
            print(f"\n✅ Cluster '{cluster_name}' created successfully!")
            print(f"\nCluster endpoint: https://0.0.0.0:{api_port}")
            print(f"Container: {container_name}")
            print(f"\nTest with: docker exec {container_name} kubectl get nodes")
            return True
        else:
            print(f"❌ Failed to get kubeconfig: {output.decode('utf-8')}")
            return False

    except docker.errors.APIError as e:
        if "already exists" in str(e):
            print(f"ℹ Container {container_name} already exists")
            container = client.containers.get(container_name)
            if container.status != "running":
                print("Starting existing container...")
                container.start()
            return True
        else:
            raise

if __name__ == "__main__":
    create_k3d_cluster()
